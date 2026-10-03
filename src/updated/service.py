from __future__ import annotations

from dbus_next.service import ServiceInterface, method, signal
from dbus_next.message import Message

from .core import UpdateCore
from .polkit import check_auth


class UpdateManagerInterface(ServiceInterface):
    def __init__(self, core: UpdateCore):
        super().__init__("com.github.ht7813.UpdateManager")
        self.core = core
        self._caller_sender: str | None = None
        core.on_change(self._on_core_change)

    def _on_core_change(self, kind: str, payload):
        if kind == "updates":
            self.UpdatesChanged(payload)
        elif kind == "status":
            self.StatusChanged(payload)
        elif kind == "progress":
            pkg_id, pct, phase = payload
            self.Progress(pkg_id, pct, phase)
        elif kind == "finished":
            self.Finished(payload["success"], payload.get("message", ""))

    # ---- 方法 ----
    @method()
    async def Install(self, ids: 'as') -> 'b':
        sender = self._caller_sender
        if sender is None:
            raise Exception("Cannot determine caller")

        ok = await check_auth(
            self._bus, sender,
            "com.github.ht7813.UpdateManager.install",
        )
        if not ok:
            raise PermissionError("Not authorized to install packages")

        return await self.core.install(ids)

    @method()
    async def InstallAll(self, severity_min: 'u') -> 'b':
        sender = self._caller_sender
        if sender is None:
            raise Exception("Cannot determine caller")

        action = (
            "com.github.ht7813.UpdateManager.install-security"
            if severity_min >= 3
            else "com.github.ht7813.UpdateManager.install"
        )
        ok = await check_auth(self._bus, sender, action)
        if not ok:
            raise PermissionError("Not authorized to install packages")

        # 过滤出 >= severity_min 的更新
        ids = [
            u.id for u in self.core.updates
            if int(u.severity) >= severity_min
        ]
        if not ids:
            return True
        return await self.core.install(ids)

    # ---- 方法 ----
    @method()
    async def Refresh(self) -> 'b':
        await self.core.check(force=True)
        return True

    @method()
    async def CheckUpdates(self, force: 'b') -> 'a(ssssus)':
        return await self.core.check(force)
    
    @method()
    async def CheckUpdatesQuiet(self) -> 'b':
        """timer 调用：检查更新，不返回列表，由信号通知 GUI。"""
        try:
            await self.core.check(force=True)
        except Exception:
            log.exception("scheduled check failed")
            return False
        return True

    @method()
    async def GetUpdates(self) -> 'a(ssssus)':
        return self.core.snapshot()

    @method()
    async def GetStatus(self) -> 's':
        return self.core.status.value

    @method()
    async def GetLastCheck(self) -> 't':
        return self.core.last_check

    @method()
    async def GetPlugins(self) -> 'as':
        return [p.name for p in self.core.plugins]

    # ---- 信号 ----
    @signal()
    def UpdatesChanged(self, updates: 'a(ssssus)') -> 'a(ssssus)':
        return updates

    @signal()
    def StatusChanged(self, status: 's') -> 's':
        return status

    @signal()
    def Progress(self, pkg_id: 's', percent: 'u', phase: 's') -> 'sus':
        return [pkg_id, percent, phase]

    @signal()
    def Finished(self, success: 'b', message: 's') -> 'bs':
        return [success, message]