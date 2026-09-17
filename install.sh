#!/usr/bin/env bash
# Usage: sudo ./install.sh [--dll /path/to/GoodixEngineAdapter.dll]
set -euo pipefail
if [[ $# == 2 && $1 == --dll && -n $2 ]]; then
    DLL="$2"
elif [[ $# == 0 ]]; then
    DLL="${GOODIX_ENGINE_DLL_PATH:-}"
else
    echo "Usage: sudo ./install.sh [--dll /path/to/GoodixEngineAdapter.dll]" >&2; exit 1
fi
if [[ $(uname -m) != x86_64 ]]; then
    echo "ERROR: the Windows PE loader requires x86_64 (x86-64 only)." >&2; exit 1
fi
if [[ $EUID != 0 ]]; then
    echo "ERROR: run with sudo: sudo ./install.sh [--dll /path/to/GoodixEngineAdapter.dll]" >&2; exit 1
fi
[[ -n "$DLL" || ! -f ./windows_driver/GoodixEngineAdapter.dll ]] || DLL=./windows_driver/GoodixEngineAdapter.dll
[[ -n "$DLL" || ! -f /var/lib/fprint/GoodixEngineAdapter.dll ]] || DLL=/var/lib/fprint/GoodixEngineAdapter.dll
if [[ -z "$DLL" || ! -r "$DLL" || ! -f "$DLL" ]]; then
    echo 'ERROR: GoodixEngineAdapter.dll not found. Use --dll /path/to/GoodixEngineAdapter.dll' >&2
    echo 'or GOODIX_ENGINE_DLL_PATH. Copy it from Windows dual-boot, e.g.' >&2
    echo 'C:\Windows\System32\WinDriver\ or the vendor driver directory,' >&2
    echo 'or extract it from the vendor Windows driver installer.' >&2; exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# Stage before changing directories; also handles an already-installed DLL.
cp "$DLL" "$tmp/GoodixEngineAdapter.dll"
DLL="$tmp/GoodixEngineAdapter.dll"

if command -v apt-get >/dev/null; then
    apt-get update
    apt-get install -y git meson ninja-build pkg-config gcc libglib2.0-dev libusb-1.0-0-dev \
        libgusb-dev libpixman-1-dev libssl-dev libnss3-dev libnspr4-dev libgirepository1.0-dev
elif command -v dnf >/dev/null; then
    dnf install -y git meson ninja-build pkgconf-pkg-config gcc glib2-devel libusb1-devel \
        libgusb-devel pixman-devel openssl-devel nss-devel nspr-devel gobject-introspection-devel
elif command -v pacman >/dev/null; then
    pacman -S --needed --noconfirm git meson ninja pkgconf gcc glib2 libusb libgusb \
        pixman openssl nss nspr gobject-introspection
elif command -v zypper >/dev/null; then
    zypper --non-interactive install git meson ninja pkg-config gcc glib2-devel libusb-1_0-devel \
        libgusb-devel pixman-devel openssl-devel mozilla-nss-devel mozilla-nspr-devel gobject-introspection-devel
else
    echo "ERROR: no supported package manager found (apt/dnf/pacman/zypper)." >&2; exit 1
fi
missing=()
for pc in glib-2.0 gusb libusb-1.0 pixman-1 nss nspr openssl gobject-introspection-1.0; do
    pkg-config --exists "$pc" || missing+=("$pc")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: pkg-config cannot find: ${missing[*]}. Install their development packages." >&2; exit 1
fi

# Pin the fork to the revision this patch targets; try a shallow fetch first.
rev=c343b6934e40dcd40a5f9e3095810d98f1175a4d
url=https://github.com/goodix-fp-linux-dev/libfprint
git init "$tmp/libfprint"
git -C "$tmp/libfprint" remote add origin "$url"
if ! git -C "$tmp/libfprint" fetch --depth 1 origin "$rev"; then
    rm -rf "$tmp/libfprint"
    git clone "$url" "$tmp/libfprint"
fi
cd "$tmp/libfprint"
git checkout "$rev"
git apply "$SCRIPT_DIR/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch"
if ! grep -q "1.94.9" meson.build; then
    sed -i "s/1.94.5/1.94.9/" meson.build
fi
if ! grep -q "FP_DEVICE_RETRY_TOO_FAST" libfprint/fp-device.h; then
    sed -i "s/FP_DEVICE_RETRY_REMOVE_FINGER,/FP_DEVICE_RETRY_REMOVE_FINGER,\n  FP_DEVICE_RETRY_TOO_FAST,/" libfprint/fp-device.h
fi
udev_rules_dir="$tmp/udev"
# Fix libdir so the ldconfig fallback also works on lib64/multiarch distros.
meson setup build -Ddrivers=goodixtls5e0a -Dgtk-examples=false -Ddoc=false \
    -Dudev_rules=enabled -Dudev_rules_dir="$udev_rules_dir" -Dudev_hwdb=disabled --prefix=/usr/local --libdir=lib
ninja -C build
ninja -C build install
install -D -m 0644 -o root -g root "$DLL" /var/lib/fprint/GoodixEngineAdapter.dll
install -d -m 0755 /etc/udev/rules.d
for rule in "$udev_rules_dir"/*.rules; do
    [[ -f "$rule" ]] || continue
    dest="/etc/udev/rules.d/$(basename "$rule")"
    cmp -s "$rule" "$dest" || install -m 0644 "$rule" "$dest"
done
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5e0a", MODE="0666", TAG+="uaccess"' > /etc/udev/rules.d/99-goodix-5e0a.rules
udevadm control --reload || true
udevadm trigger || true

# Some distros omit /usr/local/lib from the dynamic linker's search path.
ldconfig
resolved="$(ldconfig -p | awk '$1 == "libfprint-2.so.2" {if (!found++) print $NF}')"
if [[ "$resolved" != /usr/local/* ]]; then
    echo /usr/local/lib > /etc/ld.so.conf.d/goodix-libfprint.conf
    ldconfig
    resolved="$(ldconfig -p | awk '$1 == "libfprint-2.so.2" {if (!found++) print $NF}')"
fi
echo "libfprint fprintd will load from the linker cache: ${resolved:-NOT FOUND}"
if [[ "$resolved" != /usr/local/* ]]; then
    echo "ERROR: linker still prefers another libfprint. Check /etc/ld.so.conf.d/." >&2; exit 1
fi
echo 'Installed libfprint to /usr/local, DLL to /var/lib/fprint/GoodixEngineAdapter.dll,'
echo 'and udev rules to /etc/udev/rules.d/.'
echo 'restart fprintd: sudo systemctl restart fprintd'
echo "PAM needs pam_fprintd, shipped by most distros' fprintd package. Run fprintd-enroll."
