"""Actual pymodbus Windows polling with memory serial handles, not physical USB."""
import asyncio
import gc

import pytest
import serial
from pymodbus.transport.serialtransport import SerialTransport

from delta_device import simulator
from test_rtu import crc


class MemoryUsb:
    def __init__(self, state):
        self.state = state
        self.is_open = True
        self.pending = b""
        self.responses = []

    @property
    def in_waiting(self):
        if self.state['absent'] and self.state['failure'] == 'in_waiting':
            raise serial.SerialException('USB removed')
        return len(self.pending)

    def read(self, size):
        if self.state['absent'] and self.state['failure'] == 'read':
            raise serial.SerialException('USB removed during read')
        data, self.pending = self.pending[:size], self.pending[size:]
        return data

    def write(self, data):
        if self.state['absent'] and self.state['failure'] == 'write':
            raise serial.SerialException('USB removed during write')
        self.responses.append(data)
        return len(data)

    def close(self):
        self.is_open = False


async def until(predicate, message):
    async def wait():
        while not predicate():
            await asyncio.sleep(.002)
    try:
        await asyncio.wait_for(wait(), 1)
    except asyncio.TimeoutError:
        pytest.fail(message)


def install_usb(monkeypatch, failure='in_waiting'):
    state = dict(absent=False, handles=[], failed_opens=0, failure=failure)

    def open_serial(port, **kwargs):
        assert port == 'COM3', f'unexpected serial endpoint {port}'
        if state['absent']:
            state['failed_opens'] += 1
            raise serial.SerialException('USB absent')
        handle = MemoryUsb(state)
        state['handles'].append(handle)
        return handle

    monkeypatch.setattr('pymodbus.transport.serialtransport.serial.serial_for_url', open_serial)
    monkeypatch.setattr(SerialTransport, 'force_poll', True)
    monkeypatch.setenv('DELTA_SIM_RTU_HEALTH_SECONDS', '.01')
    monkeypatch.setenv('DELTA_SIM_RTU_RECONNECT_SECONDS', '.01')
    return state


async def raw_voltage(handle):
    body = bytes.fromhex('0104c0000001')  # IR49153 base-1 -> PDU49152.
    handle.pending = body + crc(body)
    await until(lambda: handle.responses, 'simulator did not answer FC04')
    expected = bytes.fromhex('01040208fc')
    assert handle.responses.pop(0) == expected + crc(expected), 'wrong raw voltage reply'


@pytest.mark.parametrize('failure', ['in_waiting', 'read', 'write'])
def test_windows_usb_removed_reinserted_reopens_and_answers_without_restart(monkeypatch, failure):
    state = install_usb(monkeypatch, failure)
    contexts = []
    factory = simulator.simulator_context

    def capture(*args):
        context = factory(*args)
        contexts.append(context)
        return context

    monkeypatch.setattr(simulator, 'simulator_context', capture)

    async def exercise():
        loop_errors = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: loop_errors.append(context))
        task = asyncio.create_task(simulator.serve_rtu('COM3'))
        try:
            await until(lambda: state['handles'], 'initial port did not open')
            await raw_voltage(state['handles'][-1])
            for cycle in range(2):
                old = state['handles'][-1]
                state['absent'] = True
                body = bytes.fromhex('0104c0000001')
                old.pending = body + crc(body)
                await until(lambda: not old.is_open, 'removed USB handle was not closed')
                await until(lambda: state['failed_opens'] > cycle,
                            'server did not attempt reopening the absent port')
                state['absent'] = False
                await until(lambda: len(state['handles']) == cycle + 2,
                            'reinserted USB did not reopen')
                await raw_voltage(state['handles'][-1])
            assert len(contexts) == 1, 'reconnect reset simulated energy/scenario context'
            assert not task.done(), 'server stopped after USB recovery'
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0)
        assert all(not h.is_open for h in state['handles']), 'serial handle leaked'
        assert not [t for t in asyncio.all_tasks()
                    if t is not asyncio.current_task() and not t.done()], 'background task leaked'
        gc.collect()
        assert not loop_errors, f'unhandled background errors: {loop_errors}'

    asyncio.run(exercise())


def test_unexpected_polling_error_closes_listener_and_propagates(monkeypatch):
    state = install_usb(monkeypatch)

    def broken(_self):
        raise RuntimeError('unexpected bug')

    monkeypatch.setattr(MemoryUsb, 'in_waiting', property(broken))

    async def exercise():
        with pytest.raises(RuntimeError, match='unexpected bug'):
            await simulator.serve_rtu('COM3')
        assert len(state['handles']) == 1, 'unknown programming error was retried'
        assert not state['handles'][0].is_open, 'unknown error leaked serial handle'

    asyncio.run(exercise())


def test_cancel_during_usb_absence_stops_reopening_and_cleans_tasks(monkeypatch):
    state = install_usb(monkeypatch)

    async def exercise():
        task = asyncio.create_task(simulator.serve_rtu('COM3'))
        try:
            await until(lambda: state['handles'], 'port did not open')
            await raw_voltage(state['handles'][-1])
            state['absent'] = True
            await until(lambda: state['failed_opens'], 'reopen did not start')
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        opens = state['failed_opens']
        await asyncio.sleep(.03)
        assert state['failed_opens'] == opens, 'reopen continued after cancellation'
        assert all(not h.is_open for h in state['handles']), 'cancel leaked serial handle'
        assert not [t for t in asyncio.all_tasks()
                    if t is not asyncio.current_task() and not t.done()], 'cancel leaked task'

    asyncio.run(exercise())


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', '61', 'bad'])
@pytest.mark.parametrize('name', ['DELTA_SIM_RTU_HEALTH_SECONDS',
                                  'DELTA_SIM_RTU_RECONNECT_SECONDS'])
def test_invalid_recovery_delay_rejected_before_open(monkeypatch, name, value):
    state = install_usb(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        asyncio.run(simulator.serve_rtu('COM3'))
    assert not state['handles'], 'invalid delay opened a serial port'


def test_idle_bus_does_not_restart_healthy_listener(monkeypatch):
    state = install_usb(monkeypatch)

    async def exercise():
        task = asyncio.create_task(simulator.serve_rtu('COM3'))
        try:
            await until(lambda: state['handles'], 'port did not open')
            await asyncio.sleep(.05)
            assert len(state['handles']) == 1, 'quiet bus triggered reopen'
            await raw_voltage(state['handles'][0])
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(exercise())
