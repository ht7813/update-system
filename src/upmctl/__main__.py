from __future__ import annotations

import argparse
import asyncio
import sys

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

BUS_NAME = "com.github.ht7813.UpdateManager"
OBJ_PATH = "/com/github/ht7813/UpdateManager"
IFACE = "com.github.ht7813.UpdateManager"

SEV_NAME = {0: "low", 1: "normal", 2: "important", 3: "security", 4: "critical"}


async def get_proxy():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    intro = await bus.introspect(BUS_NAME, OBJ_PATH)
    obj = bus.get_proxy_object(BUS_NAME, OBJ_PATH, intro)
    return bus, obj.get_interface(IFACE)


def print_updates(rows):
    if not rows:
        print("No updates available.")
        return
    print(f"{'NAME':<30} {'CURRENT':<20} {'NEW':<20} {'SEVERITY':<10} SOURCE")
    for _id, name, cur, new, sev, src in rows:
        print(f"{name:<30} {cur:<20} {new:<20} {SEV_NAME.get(sev, '?'):<10} {src}")


async def cmd_status(_):
    _, iface = await get_proxy()
    status = await iface.call_get_status()
    last = await iface.call_get_last_check()
    plugins = await iface.call_get_plugins()
    print(f"Status: {status}")
    print(f"Last check: {last}")
    print(f"Plugins: {', '.join(plugins)}")


async def cmd_check(args):
    _, iface = await get_proxy()
    rows = await iface.call_check_updates(args.force)
    print_updates(rows)


async def cmd_list(_):
    _, iface = await get_proxy()
    rows = await iface.call_get_updates()
    print_updates(rows)


SEV_NAME = {0: "low", 1: "normal", 2: "important", 3: "security", 4: "critical"}
SEV_VALUE = {v: k for k, v in SEV_NAME.items()}

async def cmd_install_all(args):
    _, iface = await get_proxy()

    # --security 快捷方式
    if args.security:
        min_sev = SEV_VALUE["security"]
    else:
        min_sev = SEV_VALUE.get(args.severity, 1)

    ok = await iface.call_install_all(min_sev)
    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)

def _validate_ids(ids: list[str]) -> None:
    for i in ids:
        if ":" not in i or i.startswith(":") or i.endswith(":"):
            print(f"Invalid id: {i!r}", file=sys.stderr)
            print("Format: <source>:<name>   e.g. pacman:linux", file=sys.stderr)
            sys.exit(1)

async def cmd_install(args):
    _validate_ids(args.ids)
    _, iface = await get_proxy()
    ok = await iface.call_install(args.ids)
    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


def build_parser():
    p = argparse.ArgumentParser(prog="upmctl")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("check")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("list")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("install")
    sp.add_argument("ids", nargs="+")
    sp.set_defaults(func=cmd_install)

    sp = sub.add_parser("install-all", help="Install all available updates")
    sp.add_argument(
        "--severity", default="normal",
        choices=["low", "normal", "important", "security", "critical"],
        help="Minimum severity to install (default: normal)",
    )
    sp.add_argument(
        "--security", action="store_true",
        help="Shorthand for --severity security",
    )
    sp.set_defaults(func=cmd_install_all)

    return p


def main():
    args = build_parser().parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()