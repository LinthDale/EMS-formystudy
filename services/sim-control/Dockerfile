# Each wrapper copies only the simulator it needs; upstream repositories are unchanged.
FROM python:3.11-slim AS common
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.110,<1" "uvicorn>=0.27,<1"
COPY services/sim-control/sim_control ./sim_control
COPY services/bff/bff/simulator_control/contracts.py services/bff/bff/simulator_control/body_limit.py ./sim_control/
RUN useradd --uid 10001 --create-home simulator
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["python", "-m", "sim_control"]

FROM common AS meter
RUN pip install --no-cache-dir pymodbus==3.6.9
COPY services/simulator/src/main.py ./meter_source.py
ENV SIMULATOR_KIND=meter
USER simulator

FROM common AS plc
RUN pip install --no-cache-dir pymodbus==3.12.1
COPY external/kc_modbus_mcp/simulator.py ./plc_source.py
ENV SIMULATOR_KIND=plc
USER simulator

FROM common AS sensor
RUN pip install --no-cache-dir aiomqtt==2.4.0
ENV SIMULATOR_KIND=sensor
USER simulator

FROM common AS delta
RUN pip install --no-cache-dir pymodbus==3.6.9 pyserial==3.5 pyserial-asyncio==0.6
COPY services/delta/delta_device ./delta_device
ENV SIMULATOR_KIND=delta
USER simulator

FROM meter AS test-meter
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx
USER simulator

FROM plc AS test-plc
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx
USER simulator

FROM sensor AS test-sensor
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx
USER simulator

FROM delta AS test-delta
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx
USER simulator
