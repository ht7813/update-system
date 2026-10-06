from __future__ import annotations

import asyncio
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from dataclasses import replace

from .plugin.base import PackageManagerPlugin, Update, ProgressCallback, Severity
from .config import Config, SEVERITY_NAMES

log = logging.getLogger(__name__)


class Status(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    INSTALLING = "installing"


class UpdateCore:
    def __init__(self, plugins: list[PackageManagerPlugin], config: Config):
        self.plugins = plugins
        self.status = Status.IDLE
        self.updates: list[Update] = []
        self.last_check: int = 0
        self._executor = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix="pkgmgr")
        self._listeners: list = []   # 状态/更新变化回调
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int | None = None
        log.setLevel(config.daemon.log_level.upper())

    # ---- 事件订阅 ----
    def on_change(self, cb):
        self._listeners.append(cb)

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._loop_thread_id = threading.get_ident()

    def _emit(self, kind, payload=None):
        if self._loop is None:
            return self._emit_sync(kind, payload)
        # 判断是否在 loop 线程
        if threading.get_ident() == self._loop_thread_id:
            self._emit_sync(kind, payload)
        else:
            self._loop.call_soon_threadsafe(self._emit_sync, kind, payload)

    def _emit_sync(self, kind, payload=None):
        for cb in list(self._listeners):   # list() 快照，避免迭代时被改
            try:
                cb(kind, payload)
            except Exception:
                log.exception("listener error")

    # ---- 查询 ----
    def snapshot(self) -> list[tuple]:
        return [u.to_dbus_list() for u in self.updates]

    # ---- 检查 ----
    async def check(self, force: bool = False) -> list[tuple]:
        if self.status == Status.CHECKING:
            return self.snapshot()
        self.status = Status.CHECKING
        self._emit("status", self.status.value)

        loop = asyncio.get_running_loop()
        try:
            updates = await loop.run_in_executor(
                self._executor, self._check_blocking, force
            )
            self.updates = updates
            self.last_check = int(time.time())
            self._emit("updates", self.snapshot())
            return self.snapshot()
        finally:
            self.status = Status.IDLE
            self._emit("status", self.status.value)

    @staticmethod
    def _apply_severity_rules(updates: list[Update], rules: list[SeverityRule]) -> list[Update]:
        import fnmatch
        out = []
        for u in updates:
            for r in rules:
                if fnmatch.fnmatch(u.name, r.pattern):
                    lvl = SEVERITY_NAMES.get(r.level, int(u.severity))
                    u = replace(u, severity=Severity(lvl))
                    break
            out.append(u)
        return out

    def _check_blocking(self, force: bool) -> list[Update]:
        all_updates: list[Update] = []
        for p in self.plugins:
            try:
                if force:
                    p.refresh_db()
                all_updates.extend(p.list_updates())
            except Exception:
                log.exception("plugin %s failed during check", p.name)
        # 按重要性降序、名称升序
        if self.config.severity.rules:
            all_updates = self._apply_severity_rules(all_updates, self.config.severity.rules)
        all_updates.sort(key=lambda u: (-int(u.severity), u.name))
        return all_updates

    # ---- 安装（桩）----
    async def install(self, ids: list[str]) -> bool:
        if self.status != Status.IDLE:
            return False
        if self.config.install.refresh_before_install:
            await self.check(True)
        self.status = Status.INSTALLING
        self._emit("status", self.status.value)
        loop = asyncio.get_running_loop()
        _last_sent: dict[tuple[str, str], float] = {}
        MIN_INTERVAL = 0.2

        def progress(pkg_id, pct, phase):
            key = (pkg_id, phase)
            now = time.monotonic()
            last = _last_sent.get(key, 0)
            if pct < 100 and now - last < MIN_INTERVAL:
                return
            _last_sent[key] = now
            self._emit("progress", (pkg_id, pct, phase))

        try:
            # 按插件分组
            grouped: dict[str, list[str]] = {}
            for i in ids:
                src, _ = i.split(":", 1)
                grouped.setdefault(src, []).append(i)

            ok = True
            for name, group in grouped.items():
                plugin = next((p for p in self.plugins if p.name == name), None)
                if plugin is None:
                    ok = False
                    continue
                res = await loop.run_in_executor(
                    self._executor, plugin.install, group, progress
                )
                ok = ok and res

            # 装完后重新检查
            await self.check(force=False)
            self._emit("finished", {"success": ok})
            return ok
        finally:
            self.status = Status.IDLE
            self._emit("status", self.status.value)
