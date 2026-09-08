import pefile, capstone, struct

wbdi_path = "/run/media/sastauser/Windows/Users/jitendra/goodix-27c6-5e0a-re/drivers/wbdi.dll"
pe = pefile.PE(wbdi_path)
image_base = pe.OPTIONAL_HEADER.ImageBase

text_sec = [s for s in pe.sections if s.Name.startswith(b".text")][0]
text_data = text_sec.get_data()
text_va = image_base + text_sec.VirtualAddress

rdata_sec = [s for s in pe.sections if s.Name.startswith(b".rdata")][0]
rdata_data = rdata_sec.get_data()
rdata_va = image_base + rdata_sec.VirtualAddress

cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
cs.detail = True

def get_string_at(target):
    if rdata_va <= target < rdata_va + rdata_sec.Misc_VirtualSize:
        off = target - rdata_va
        s = rdata_data[off:off+64].split(b"\x00")[0]
        try:
            return s.decode("utf-8", errors="ignore")
        except:
            return None
    return None

def disasm_range(start_va, end_va):
    off = start_va - text_va
    length = end_va - start_va
    chunk = text_data[off:off+length]
    for insn in cs.disasm(chunk, start_va):
        extra = ""
        for op in insn.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                target = insn.address + insn.size + op.mem.disp
                s = get_string_at(target)
                if s:
                    extra += f" ; str: \"{s}\""
                else:
                    extra += f" ; target={hex(target)}"
        print(f"{hex(insn.address)}:  {insn.mnemonic:8s} {insn.op_str:30s}{extra}")

if __name__ == "__main__":
    import sys
    start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x180039ce0
    end = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x18003a450
    disasm_range(start, end)
