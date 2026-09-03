import re
import sys

def extract_strings(filename):
    with open(filename, 'rb') as f:
        data = f.read()

    # ASCII
    ascii_re = re.compile(rb'[\x20-\x7e]{4,}')
    ascii_strs = [m.group(0).decode('latin1') for m in ascii_re.finditer(data)]

    # UTF-16LE
    utf16_re = re.compile(rb'(?:[\x20-\x7e]\x00){4,}')
    utf16_strs = [m.group(0).decode('utf-16le', errors='ignore') for m in utf16_re.finditer(data)]

    return set(ascii_strs + utf16_strs)

def main():
    dll_path = sys.argv[1]
    strs = extract_strings(dll_path)
    print(f"File: {dll_path} - Total strings: {len(strs)}")

    keywords = ['geneva', 'chicago', 'milan', '5e0a', '5e02', 'firmware', 'sensor', 'chip', 'goodix', 'psk', 'tls', 'fdt']
    for kw in keywords:
        matches = [s for s in strs if kw in s.lower()]
        print(f"\n--- Keyword '{kw}': {len(matches)} matches ---")
        for m in sorted(matches)[:15]:
            print(f"  {m}")

if __name__ == '__main__':
    main()
