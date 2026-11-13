"""Windows owned process tree, with a launch gate before child creation.

Reference: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
No breakaway flags; the non-inherited job handle is held only by the controller.
"""
import ctypes as C
import subprocess


class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64),
        ('flags', C.c_uint32), ('min_working', C.c_size_t), ('max_working', C.c_size_t),
        ('active_limit', C.c_uint32), ('affinity', C.c_size_t),
        ('priority', C.c_uint32), ('scheduling', C.c_uint32)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops',
                                              'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', C.c_size_t),
        ('job_memory', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


class OwnedJob:
    def __init__(self, api=None):
        if api is None:
            api = C.WinDLL('kernel32', use_last_error=True)
            api.CreateJobObjectW.argtypes = [C.c_void_p, C.c_wchar_p]
            api.CreateJobObjectW.restype = C.c_void_p
            api.SetInformationJobObject.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_uint32]
            api.SetInformationJobObject.restype = C.c_int
            api.AssignProcessToJobObject.argtypes = [C.c_void_p, C.c_void_p]
            api.AssignProcessToJobObject.restype = C.c_int
            api.CloseHandle.argtypes = [C.c_void_p]
            api.CloseHandle.restype = C.c_int
        self.api, self.handle = api, api.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError('owned job creation failed')
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            self.close()
            raise OSError('owned job configuration failed')

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError('owned process assignment failed')

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise OSError('owned job close failed')
            self.handle = None


BOOTSTRAP = """import pathlib,runpy,sys,time
gate=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+60
while not gate.exists():
    if time.monotonic()>deadline: raise SystemExit(2)
    time.sleep(.02)
sys.argv=sys.argv[2:]
sys.path.insert(0,str(pathlib.Path(sys.argv[0]).resolve().parent))
runpy.run_path(sys.argv[0],run_name='__main__')
"""


def spawn_owned(executable, arguments, gate, cwd, env, log):
    if gate.exists():
        raise ValueError('launch gate must be new')
    job, process = OwnedJob(), None
    try:
        process = subprocess.Popen([executable, '-c', BOOTSTRAP, str(gate), *arguments],
            cwd=cwd, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        job.assign(process)
        # Bootstrap cannot load bench code or spawn children before assignment.
        gate.write_text('start', encoding='utf-8')
        return process, job
    except BaseException:
        try:
            job.close()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()  # Assignment failure: still a bootstrap leaf.
                process.wait(timeout=10)
        raise
