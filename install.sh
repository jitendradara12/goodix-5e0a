#!/usr/bin/env bash
# Build as your normal user. Only dependencies and the file transaction use sudo.
set -euo pipefail

fail() { echo "ERROR: $*" >&2; return 1; }

# These transactions also run unprivileged against temporary paths in the tests.
# Production calls below use fixed paths, never a caller-supplied install root.
install_files() (
    set -euo pipefail
    local stage=$1 prefix=$2 dropdir=$3 made_prefix=false made_dropdir=false committed=false
    local marker='goodix-5e0a private install v1'
    [[ ! -e "$prefix" && ! -L "$prefix" ]] || { fail "Destination exists: $prefix"; exit 1; }
    [[ ! -e "$dropdir" && ! -L "$dropdir" ]] || { fail "Drop-in directory exists: $dropdir (preserving it)"; exit 1; }
    # shellcheck disable=SC2329 # Invoked by the EXIT trap.
    cleanup_install() {
        if [[ $committed == false ]]; then
            if [[ $made_dropdir == true ]]; then
                rm -f -- "$dropdir/90-goodix.conf"
                rmdir -- "$dropdir" || true
            fi
            if [[ $made_prefix == true ]]; then rm -rf -- "$prefix"; fi
            systemctl daemon-reload || true
        fi
    }
    trap cleanup_install EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    mkdir -m 0755 -- "$prefix"
    made_prefix=true
    mkdir -m 0755 -- "$dropdir"
    made_dropdir=true
    cp -R --no-preserve=ownership -- "$stage/." "$prefix/"
    chmod -R go-w -- "$prefix"
    printf '%s\n' "$marker" > "$prefix/.goodix-install"
    printf '# %s\n[Service]\nEnvironment=LD_LIBRARY_PATH=%s/lib\nEnvironment=GOODIX_ENGINE_DLL_PATH=%s/GoodixEngineAdapter.dll\n' \
        "$marker" "$prefix" "$prefix" > "$dropdir/90-goodix.conf"
    systemctl daemon-reload
    committed=true
)

uninstall_files() (
    set -euo pipefail
    local prefix=$1 dropdir=$2 marker='goodix-5e0a private install v1'
    # Validate both ownership records before removing anything. Never remove prints.
    [[ -d "$prefix" && ! -L "$prefix" && ! -L "$prefix/.goodix-install" ]] || { fail "Not an owned installation: $prefix"; exit 1; }
    [[ -d "$dropdir" && ! -L "$dropdir" && ! -L "$dropdir/90-goodix.conf" ]] || { fail "Not an owned drop-in: $dropdir"; exit 1; }
    printf '%s\n' "$marker" | cmp -s - "$prefix/.goodix-install" || { fail 'Installation marker differs; leaving files alone'; exit 1; }
    printf '# %s\n[Service]\nEnvironment=LD_LIBRARY_PATH=%s/lib\nEnvironment=GOODIX_ENGINE_DLL_PATH=%s/GoodixEngineAdapter.dll\n' \
        "$marker" "$prefix" "$prefix" | cmp -s - "$dropdir/90-goodix.conf" || { fail 'Drop-in differs; leaving files alone'; exit 1; }
    rm -- "$dropdir/90-goodix.conf"
    rmdir -- "$dropdir" 2>/dev/null || true # Preserve any drop-ins added afterwards.
    rm -rf -- "$prefix"
    systemctl daemon-reload
)

build_stage() (
    set -euo pipefail
    local tmp=$1 script_dir=$2 dll=$3
    local rev=c343b6934e40dcd40a5f9e3095810d98f1175a4d
    local url=https://github.com/goodix-fp-linux-dev/libfprint
    # Pin the fork to the revision this patch targets; try a shallow fetch first.
    git init "$tmp/libfprint"
    git -C "$tmp/libfprint" remote add origin "$url"
    if ! git -C "$tmp/libfprint" fetch --depth 1 origin "$rev"; then
        rm -rf -- "$tmp/libfprint"
        git clone "$url" "$tmp/libfprint"
    fi
    cd "$tmp/libfprint"
    git checkout "$rev"
    git apply "$script_dir/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch"
    if ! grep -q '1.94.9' meson.build; then
        sed -i 's/1.94.5/1.94.9/' meson.build
    fi
    if ! grep -q FP_DEVICE_RETRY_TOO_FAST libfprint/fp-device.h; then
        sed -i 's/FP_DEVICE_RETRY_REMOVE_FINGER,/FP_DEVICE_RETRY_REMOVE_FINGER,\n  FP_DEVICE_RETRY_TOO_FAST,/' libfprint/fp-device.h
    fi
    # fprintd runs as root; no world-writable USB rule or global linker changes.
    meson setup build -Ddrivers=goodixtls5e0a -Dgtk-examples=false -Ddoc=false \
        -Dudev_rules=disabled -Dudev_hwdb=disabled --prefix=/opt/goodix-libfprint --libdir=lib
    ninja -C build
    DESTDIR="$tmp/stage" ninja -C build install
    install -m 0644 -- "$dll" "$tmp/stage/opt/goodix-libfprint/GoodixEngineAdapter.dll"
    test -f "$tmp/stage/opt/goodix-libfprint/lib/libfprint-2.so.2"
)

main() (
    set -euo pipefail
    umask 022
    local mode=install DLL=${GOODIX_ENGINE_DLL_PATH:-} script_dir tmp tool pc
    case "$#:${1:-}" in
        0:) ;;
        1:--help)
            echo 'Usage: ./install.sh [--dll /path/to/GoodixEngineAdapter.dll] | --uninstall | --help'
            echo 'Run as your normal user, not sudo. Private /opt install; sudo is used for dependencies and installation.'
            echo 'Requires systemd and root-run fprintd. No automatic restart, PAM changes, or --no-timeout override.'
            echo 'Uninstall preserves enrolled prints and installed distro packages.'
            return ;;
        1:--uninstall) mode=uninstall ;;
        2:--dll) [[ -n $2 && $2 != --* ]] || { fail '--dll requires a file'; exit 1; }; DLL=$2 ;;
        *) fail 'Usage: ./install.sh [--dll /path/to/GoodixEngineAdapter.dll] | --uninstall | --help'; exit 1 ;;
    esac
    # os-release is supplied by the OS; sourcing handles single/double quoted IDs.
    local ID='' ID_LIKE=''
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ $ID == nixos ]]; then
        fail "NixOS detected. Import nixos-module.nix or nixosModules.default and rebuild your configuration."
        exit 1
    fi
    [[ $(uname -m) == x86_64 ]] || { fail 'The Windows PE loader requires x86_64'; exit 1; }
    [[ $EUID != 0 ]] || { fail 'Run ./install.sh as your normal user, without sudo'; exit 1; }
    local manager=''
    case " $ID $ID_LIKE " in
        *' debian '*|*' ubuntu '*) manager=apt-get ;;
        *' fedora '*|*' rhel '*) manager=dnf ;;
        *' arch '*) manager=pacman ;;
        *' suse '*|*' opensuse '*|*' opensuse-tumbleweed '*|*' opensuse-leap '*) manager=zypper ;;
        *) fail "Unsupported OS: $ID. Use the NixOS module on NixOS; other installation paths are unverified."; exit 1 ;;
    esac
    for tool in "$manager" sudo systemctl; do
        command -v "$tool" >/dev/null || { fail "Required command missing: $tool"; exit 1; }
    done
    [[ -d /run/systemd/system ]] || { fail 'This installer requires a running systemd system'; exit 1; }
    local prefix=/opt/goodix-libfprint dropdir=/etc/systemd/system/fprintd.service.d
    if [[ $mode == uninstall ]]; then
        sudo bash -c "$(declare -f fail uninstall_files); uninstall_files \"\$@\"" bash "$prefix" "$dropdir"
        echo 'Removed private driver and owned drop-in. Enrolled prints and distro packages were preserved.'
        echo 'Restart when ready: sudo systemctl restart fprintd'
        return
    fi
    [[ ! -e $prefix && ! -L $prefix && ! -e $dropdir && ! -L $dropdir ]] || {
        fail "Refusing existing $prefix or $dropdir. No files overwritten; uninstall an owned installation first."; exit 1;
    }
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ -n $DLL || ! -f $script_dir/windows_driver/GoodixEngineAdapter.dll ]] || DLL="$script_dir/windows_driver/GoodixEngineAdapter.dll"
    [[ -n $DLL || ! -f /var/lib/fprint/GoodixEngineAdapter.dll ]] || DLL=/var/lib/fprint/GoodixEngineAdapter.dll
    if [[ -z $DLL || ! -r $DLL || ! -f $DLL ]]; then
        fail 'GoodixEngineAdapter.dll not found. Use --dll /path/to/GoodixEngineAdapter.dll or GOODIX_ENGINE_DLL_PATH.'
        echo 'Copy from Windows dual-boot, e.g. C:\Windows\System32\WinDriver\ or the vendor driver directory, or extract the vendor Windows driver installer.' >&2
        exit 1
    fi
    tmp="$(mktemp -d)"
    trap 'rm -rf -- "$tmp"' EXIT
    cp -- "$DLL" "$tmp/GoodixEngineAdapter.dll"
    case $manager in
        apt-get)
            sudo apt-get update
            sudo apt-get install -y git meson ninja-build pkg-config gcc g++ fprintd libglib2.0-dev libusb-1.0-0-dev \
                libgusb-dev libpixman-1-dev libssl-dev libnss3-dev libnspr4-dev libgirepository1.0-dev ;;
        dnf)
            sudo dnf install -y git meson ninja-build pkgconf-pkg-config gcc gcc-c++ fprintd glib2-devel libusb1-devel \
                libgusb-devel pixman-devel openssl-devel nss-devel nspr-devel gobject-introspection-devel ;;
        pacman)
            sudo pacman -S --needed --noconfirm git meson ninja pkgconf gcc fprintd glib2 libusb libgusb \
                pixman openssl nss nspr gobject-introspection ;;
        zypper)
            sudo zypper --non-interactive install git meson ninja pkg-config gcc gcc-c++ fprintd glib2-devel libusb-1_0-devel \
                libgusb-devel pixman-devel openssl-devel mozilla-nss-devel mozilla-nspr-devel gobject-introspection-devel ;;
    esac
    for tool in git meson ninja pkg-config gcc g++ fprintd-enroll; do
        command -v "$tool" >/dev/null || { fail "Required command missing after dependency installation: $tool"; exit 1; }
    done
    local missing=()
    for pc in glib-2.0 gusb libusb-1.0 pixman-1 nss nspr openssl gobject-introspection-1.0; do
        pkg-config --exists "$pc" || missing+=("$pc")
    done
    [[ ${#missing[@]} == 0 ]] || { fail "Missing development libraries: ${missing[*]}"; exit 1; }
    [[ $(systemctl show fprintd.service -p LoadState --value) == loaded ]] || { fail 'fprintd.service not available'; exit 1; }
    local daemon_user
    daemon_user=$(systemctl show fprintd.service -p User --value)
    [[ -z $daemon_user || $daemon_user == root ]] || { fail "fprintd must run as root; found User=$daemon_user. No USB permissions changed."; exit 1; }
    build_stage "$tmp" "$script_dir" "$tmp/GoodixEngineAdapter.dll"
    sudo bash -c "$(declare -f fail install_files); install_files \"\$@\"" bash "$tmp/stage/opt/goodix-libfprint" "$prefix" "$dropdir"
    echo "Installed private libfprint and DLL under $prefix; added $dropdir/90-goodix.conf."
    echo 'No global library replacement, USB permission changes, PAM changes, or automatic service restart.'
    echo 'No --no-timeout override: daemon idle-exit may discard parked TLS sessions.'
    echo 'Non-NixOS end-to-end operation is unverified. Keep password login available.'
    echo 'When ready: sudo systemctl restart fprintd; then fprintd-enroll and fprintd-verify.'
    echo 'PAM is optional: Debian/Ubuntu use libpam-fprintd; configure your distro auth stack separately.'
    printf 'Uninstall: %q --uninstall\n' "$script_dir/install.sh"
    echo 'Uninstall preserves enrolled prints and installed distro packages.'
)

# Sourcing exposes the same transactions to unprivileged fixture tests.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
