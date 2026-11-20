"""Darwin physical footprint includes compressed memory and Metal allocations hidden from RSS."""

import ctypes
import os
from functools import lru_cache


class RusageInfoV4(ctypes.Structure):
    # Layout from the Darwin SDK's <sys/resource.h>, through ri_runnable_time.
    _fields_ = [
        ("uuid", ctypes.c_uint8 * 16),
        ("usage_through_resident_size", ctypes.c_uint64 * 7),
        ("phys_footprint", ctypes.c_uint64),
        ("timing_io_and_energy", ctypes.c_uint64 * 20),
        ("lifetime_max_phys_footprint", ctypes.c_uint64),
        ("remaining_counters", ctypes.c_uint64 * 6),
    ]


@lru_cache(maxsize=1)
def _pid_rusage():
    function = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pid_rusage
    function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(RusageInfoV4)]
    function.restype = ctypes.c_int
    return function


def macos_footprint(pid):
    usage = RusageInfoV4()
    if _pid_rusage()(pid, 4, ctypes.byref(usage)) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return usage.phys_footprint, usage.lifetime_max_phys_footprint
