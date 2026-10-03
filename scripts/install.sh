#!/usr/bin/env bash
# Install script for updated / upmctl / upmgui
set -euo pipefail

PREFIX="${PREFIX:-/usr}"
SYSCONFDIR="${SYSCONFDIR:-/etc}"
UNITDIR="${UNITDIR:-/usr/lib/systemd/system}"
DBUSDIR="${DBUSDIR:-/usr/share/dbus-1/system.d}"
POLKITDIR="${POLKITDIR:-/usr/share/polkit-1/actions}"
POLKITRULESDIR="${POLKITRULESDIR:-/usr/share/polkit-1/rules.d}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$SRC_DIR/data"

BUS_NAME="com.github.ht7813.UpdateManager"
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --uninstall) UNINSTALL=1 ;;
        -h|--help)
            echo "Usage: $0 [--uninstall]"
            exit 0
            ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This script must be run as root." >&2
        exit 1
    fi
}

install_files() {
    require_root

    echo ">> Installing python package"
    python -m pip install --no-deps --root-user-action=ignore "$SRC_DIR"

    echo ">> Installing systemd units"
    install -Dm644 "$DATA_DIR/updated.service"       "$UNITDIR/updated.service"
    install -Dm644 "$DATA_DIR/updated-check.service" "$UNITDIR/updated-check.service"
    install -Dm644 "$DATA_DIR/updated-check.timer"   "$UNITDIR/updated-check.timer"

    echo ">> Installing D-Bus policy"
    install -Dm644 "$DATA_DIR/${BUS_NAME}.conf" \
        "$DBUSDIR/${BUS_NAME}.conf"

    echo ">> Installing polkit action"
    install -Dm644 "$DATA_DIR/${BUS_NAME}.policy" \
        "$POLKITDIR/${BUS_NAME}.policy"

    if [[ -f "$DATA_DIR/49-${BUS_NAME}.rules" ]]; then
        install -Dm644 "$DATA_DIR/49-${BUS_NAME}.rules" \
            "$POLKITRULESDIR/49-${BUS_NAME}.rules"
    fi

    echo ">> Installing default config (if absent)"
    install -d "$SYSCONFDIR/updated"
    if [[ ! -f "$SYSCONFDIR/updated/config.toml" ]]; then
        install -Dm644 "$DATA_DIR/config.toml.example" \
            "$SYSCONFDIR/updated/config.toml"
    else
        echo "   $SYSCONFDIR/updated/config.toml exists, skipped"
    fi

    echo ">> Reloading systemd and dbus"
    systemctl daemon-reload
    systemctl reload dbus 2>/dev/null || true

    echo ">> Enabling services"
    systemctl enable --now updated.service
    systemctl enable --now updated-check.timer

    echo
    echo "Installed. Check status with:"
    echo "   systemctl status updated"
    echo "   systemctl list-timers updated-check.timer"
}

uninstall_files() {
    require_root

    echo ">> Stopping services"
    systemctl disable --now updated-check.timer 2>/dev/null || true
    systemctl disable --now updated.service     2>/dev/null || true

    echo ">> Removing systemd units"
    rm -f "$UNITDIR/updated.service" \
          "$UNITDIR/updated-check.service" \
          "$UNITDIR/updated-check.timer"

    echo ">> Removing D-Bus and polkit files"
    rm -f "$DBUSDIR/${BUS_NAME}.conf"
    rm -f "$POLKITDIR/${BUS_NAME}.policy"
    rm -f "$POLKITRULESDIR/49-${BUS_NAME}.rules"

    echo ">> Removing python package"
    python -m pip uninstall -y updated || true

    systemctl daemon-reload
    systemctl reload dbus 2>/dev/null || true

    echo
    echo "Uninstalled. Config at $SYSCONFDIR/updated/config.toml left in place."
}

if [[ $UNINSTALL -eq 1 ]]; then
    uninstall_files
else
    install_files
fi