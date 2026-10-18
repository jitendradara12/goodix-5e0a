"""Native x86-64 Linux backend using the production PE loader, not emulation."""

import ctypes
import platform

from images import ImageOperations


class NativeEngine(ImageOperations):
    """Shares image/quality helpers, replaces all guest-memory/execution APIs."""

    def __init__(self, dll_path, library):
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise RuntimeError("Native backend requires x86-64 Linux")
        self.library = ctypes.CDLL(str(library))
        self.library.milan_probe_init.argtypes = [ctypes.c_char_p]
        self.library.milan_probe_init.restype = ctypes.c_int
        self.library.milan_probe_call.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint64),
        ]
        self.library.milan_probe_call.restype = ctypes.c_int
        if self.library.milan_probe_init(str(dll_path).encode()) != 0:
            raise RuntimeError("Production PE loader failed to initialize")
        self.buffers = []
        self.u = self

    def put(self, data):
        buffer = ctypes.create_string_buffer(bytes(data), max(len(data), 1))
        self.buffers.append(buffer)
        return ctypes.addressof(buffer)

    def mem_read(self, address, length):
        return ctypes.string_at(address, length)

    def mem_write(self, address, data):
        ctypes.memmove(address, bytes(data), len(data))

    def call(self, name, args=(), count=None):
        arguments = (ctypes.c_uint64 * len(args))(*args)
        result = ctypes.c_uint64()
        status = self.library.milan_probe_call(
            name.encode(), arguments, len(args), ctypes.byref(result)
        )
        if status != 0:
            raise RuntimeError(f"Cannot call vendor export {name}: {status}")
        return result.value
