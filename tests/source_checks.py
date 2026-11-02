"""Source parsing and metrics shared by tests."""

import re


def c_code_lines(source: str):
    """Count code without charging documentation against the size budget.

    Preserve quoted strings/characters while removing C comments. This keeps
    useful lifecycle explanations from encouraging compressed statements.
    """
    tokens = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|/\*.*?\*/|//[^\n]*'''
    code = re.sub(tokens, lambda m: m[0] if m[0][0] in "\"'" else "", source, flags=re.S)
    return [line for line in code.splitlines() if line.strip()]


def parse_c_array(header_content: str, array_name: str) -> bytes:
    """Extract a byte array from C header/source content."""
    pattern = rf"(?:static\s+)?const\s+guint8\s+{array_name}\s*\[\s*\d*\s*\]\s*=\s*\{{([^}}]+)\}};"
    match = re.search(pattern, header_content, re.DOTALL)
    if not match:
        raise ValueError(f"Array '{array_name}' not found in header")
    hex_bytes = re.findall(r"0x([0-9a-fA-F]{2})", match.group(1))
    return bytes(int(b, 16) for b in hex_bytes)


def parse_c_macro(header_content: str, macro_name: str) -> int:
    """Extract an integer macro value from C header/source content."""
    pattern = rf"#define\s+{macro_name}\s+\(([^)]+)\)"
    match = re.search(pattern, header_content)
    if not match:
        pattern2 = rf"#define\s+{macro_name}\s+(\S+)"
        match2 = re.search(pattern2, header_content)
        if not match2:
            raise ValueError(f"Macro '{macro_name}' not found in header")
        val_str = match2.group(1).strip()
    else:
        val_str = match.group(1).strip()
    if val_str.startswith(("0x", "0X")):
        return int(val_str, 16)
    return int(val_str)
