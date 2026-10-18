"""Offline x86-64 Milan probe for ARM and x86 hosts; never accesses USB.

Uses the real DLL instructions with a small, fail-on-unknown import shim.
See README.md for the validation boundary and reproducible invocation.
"""

import struct

import pefile
from images import ImageOperations
from unicorn import (
    UC_ARCH_X86,
    UC_HOOK_CODE,
    UC_HOOK_MEM_INVALID,
    UC_MODE_64,
    Uc,
)
from unicorn.x86_const import (
    UC_X86_REG_GS_BASE,
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RAX,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RIP,
    UC_X86_REG_RSP,
)


# This emulator runs the algorithm, not a Windows process. DllMain is not called.
# The two bypasses below are diagnostics/security-cookie verification only.
# Unsupported imports fail explicitly. Free records ownership but keeps guest
# memory mapped, so this is not a general memory-safety checker.
class Engine(ImageOperations):
    def __init__(self, path="windows_driver/GoodixEngineAdapter.dll"):
        self.pe = pefile.PE(path)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.u = Uc(UC_ARCH_X86, UC_MODE_64)
        u = self.u
        u.mem_map(self.base, (self.pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        u.mem_write(self.base, self.pe.get_memory_mapped_image())
        self.stack = 0x300000000
        u.mem_map(self.stack, 0x800000)
        self.heap = 0x200000000
        u.mem_map(self.heap, 0x10000000)
        self.next = self.heap
        self.stop = 0x500000000
        u.mem_map(self.stop, 0x1000)
        u.mem_write(self.stop, b"\xcc")
        self.stub = 0x600000000
        u.mem_map(self.stub, 0x10000)
        self.shims = {}
        self.seen = {}
        self.freed = set()
        self.exports = {
            s.name.decode(): self.base + s.address
            for s in self.pe.DIRECTORY_ENTRY_EXPORT.symbols
            if s.name
        }
        for d in self.pe.DIRECTORY_ENTRY_IMPORT:
            for i in d.imports:
                a = self.stub + len(self.shims) * 16
                self.shims[a] = i.name.decode() if i.name else "#" + str(i.ordinal)
                u.mem_write(a, b"\xc3")
                u.mem_write(i.address, struct.pack("<Q", a))
        # Bypass only diagnostics/cookie checks, not algorithm code.
        self.bypass = {self.base + 0x4A8E0: "logger", self.base + 0x727B0: "cookie"}
        for a in self.bypass:
            u.mem_write(a, b"\xc3")
        self.teb = 0x400000000
        u.mem_map(self.teb, 0x10000)
        u.reg_write(UC_X86_REG_GS_BASE, self.teb)
        u.mem_write(self.teb + 0x30, struct.pack("<Q", self.teb))
        u.mem_write(self.teb + 0x58, struct.pack("<Q", self.teb + 0x2000))
        u.mem_write(self.teb + 0x60, struct.pack("<Q", self.teb + 0x4000))
        u.mem_write(self.teb + 0x2000, struct.pack("<Q", self.teb + 0x3000))
        u.hook_add(UC_HOOK_CODE, self.hook, begin=self.stub, end=self.stub + 0xFFFF)
        u.hook_add(UC_HOOK_MEM_INVALID, self.invalid)

    def invalid(self, u, access, a, size, value, data):
        print(
            "INVALID", hex(a), size, "RIP", hex(u.reg_read(UC_X86_REG_RIP)), flush=True
        )
        return False

    def alloc(self, n):
        a = self.next
        self.next += (max(n, 1) + 15) & ~15
        if self.next > self.heap + 0x10000000:
            raise RuntimeError("heap exhausted")
        return a

    def put(self, b):
        a = self.alloc(len(b))
        self.u.mem_write(a, b)
        return a

    def args(self, n):
        u = self.u
        v = [
            u.reg_read(r)
            for r in [UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9]
        ]
        sp = u.reg_read(UC_X86_REG_RSP)
        return (
            v
            + [
                struct.unpack("<Q", u.mem_read(sp + 0x28 + i * 8, 8))[0]
                for i in range(max(0, n - 4))
            ]
        )[:n]

    def hook(self, u, a, size, data):
        n = self.shims[a]
        self.seen[n] = self.seen.get(n, 0) + 1
        x = self.args(6)
        r = 0
        if n in ["malloc", "_malloc_base"]:
            r = self.alloc(x[0])
        elif n in ["calloc", "_calloc_base"]:
            r = self.alloc(x[0] * x[1])
        elif n in ["free", "_free_base"]:
            self.freed.add(x[0])
        elif n == "memset":
            u.mem_write(x[0], bytes([x[1] & 255]) * x[2])
            r = x[0]
        else:
            raise RuntimeError("Unsupported import " + n + " " + str(x))
        u.reg_write(UC_X86_REG_RAX, r & 0xFFFFFFFFFFFFFFFF)

    def call(self, name, args=(), count=200000000):
        u = self.u
        address = self.exports[name] if isinstance(name, str) else name
        sp = self.stack + 0x7FF000 - 8
        u.mem_write(sp, struct.pack("<Q", self.stop))
        u.mem_write(sp + 8, b"\0" * 256)
        for r, v in zip(
            [UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9], args[:4]
        ):
            u.reg_write(r, v)
        for i, v in enumerate(args[4:]):
            u.mem_write(sp + 0x28 + i * 8, struct.pack("<Q", v))
        u.reg_write(UC_X86_REG_RSP, sp)
        u.emu_start(address, self.stop, count=count)
        if u.reg_read(UC_X86_REG_RIP) != self.stop:
            raise RuntimeError(
                "Instruction limit "
                + str(name)
                + " rip="
                + hex(u.reg_read(UC_X86_REG_RIP))
            )
        return u.reg_read(UC_X86_REG_RAX)
