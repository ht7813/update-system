from __future__ import annotations

import asyncio
import logging
from typing import Callable

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

log = logging.getLogger(__name__)

BUS_NAME = "com.github.ht7813.UpdateManager"
OBJ_PATH = "/com/github/ht7813/UpdateManager"
IFACE = "com.github.ht7813.UpdateManager"


class UpdateClient:
    def __init__(self):
        self.bus: MessageBus | None = None
        self.iface = None
        self._ready = asyncio.Event()
        self._on_updates: Callable[[list], None] | None = None
        self._on_progress: Callable[[str, int, str], None] | None = None

    async def connect(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        intro = await self.bus.introspect(BUS_NAME, OBJ_PATH)
        obj = self.bus.get_proxy_object(BUS_NAME, OBJ_PATH, intro)
        self.iface = obj.get_interface(IFACE)
        self._ready.set()
        log.info("connected to %s", BUS_NAME)

    async def wait_ready(self):
        await self._ready.wait()

    async def get_updates(self) -> list:
        await self.wait_ready()
        return await self.iface.call_get_updates()

    async def check(self, force: bool = False) -> list:
        await self.wait_ready()
        return await self.iface.call_check_updates(force)

    async def install(self, ids: list[str]) -> bool:
        await self.wait_ready()
        return await self.iface.call_install(ids)

    async def install_all(self, severity_min: int) -> bool:
        await self.wait_ready()
        return await self.iface.call_install_all(severity_min)

    def watch_updates(self, callback: Callable[[list], None]):
        """注册 UpdatesChanged 信号回调。"""
        self._on_updates = callback
        self.iface.on_updates_changed(self._handle_updates)

    def _handle_updates(self, updates: list):
        log.info("received %d updates", len(updates))
        if self._on_updates:
            self._on_updates(updates)

    def watch_progress(self, callback: Callable[[str, int, str], None]):
        """注册 UpdatesChanged 信号回调。"""
        self._on_progress = callback
        self.iface.on_progress(self._handle_progress)

    def _handle_progress(self, package: str, progress: int, action: str):
        log.info("progress: package %s, action %s: %d", package, action, progress)
        if self._on_progress:
            self._on_progress(package, progress, action)
