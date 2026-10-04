from __future__ import annotations

import asyncio
import logging
import signal as os_signal

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

from .config import load_config
from .core import UpdateCore
from .plugin.loader import load_plugins
from .service import UpdateManagerInterface

BUS_NAME = "com.github.ht7813.UpdateManager"
OBJ_PATH = "/com/github/ht7813/UpdateManager"

log = logging.getLogger("updated")


async def run() -> None:
    cfg = load_config()
    log.setLevel(cfg.daemon.log_level.upper())
    plugins = load_plugins(cfg.plugins.enabled)
    log.info("loaded %d plugins: %s",
             len(plugins), [p.name for p in plugins])

    core = UpdateCore(plugins, cfg)
    core.bind_loop(asyncio.get_running_loop())
    iface = UpdateManagerInterface(core)

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    iface._bus = bus
    def _on_message(msg: Message) -> bool:
        if msg.sender and msg.path == OBJ_PATH:
            iface._caller_sender = msg.sender
        return False  # 返回 False 表示继续正常分发

    bus.add_message_handler(_on_message)
    bus.export(OBJ_PATH, iface)
    await bus.request_name(BUS_NAME)
    log.info("registered %s on system bus", BUS_NAME)

    # 启动时异步做一次非强制检查
    asyncio.create_task(core.check(force=False))

    # 优雅退出
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("shutting down")
    for p in plugins:
        p.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
