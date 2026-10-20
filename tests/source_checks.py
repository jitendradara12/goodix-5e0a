"""Small source metrics shared by architecture checks."""

import re


def c_code_lines(source):
    """Count code without charging documentation against the size budget.

    Preserve quoted strings/characters while removing C comments. This keeps
    useful lifecycle explanations from encouraging compressed statements.
    """
    tokens = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|/\*.*?\*/|//[^\n]*'''
    code = re.sub(tokens, lambda m: m[0] if m[0][0] in "\"'" else "", source, flags=re.S)
    return [line for line in code.splitlines() if line.strip()]
