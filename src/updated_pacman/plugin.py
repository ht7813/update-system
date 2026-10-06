from __future__ import annotations

import logging
from typing import Iterable

import pyalpm
import pycman.config

from updated.plugin.base import (
    PackageManagerPlugin, Update, Severity, ProgressCallback,
)

from updated.config import load_config

log = logging.getLogger(__name__)

# 简单的"重要包"启发式；后续可由 severity.py 接管
_IMPORTANT_PREFIXES = (
    "linux", "glibc", "openssl", "systemd", "sudo",
    "pacman", "nvidia-open", "mesa", "xorg-server",
)
_SECURITY_HINTS = ("security", "cve")


class PacmanPlugin(PackageManagerPlugin):
    name = "pacman"
    priority = 10

    def __init__(self):
        self._handle: pyalpm.Handle | None = None
        self.cfg = load_config().plugins.pacman
        self._config_path = self.cfg.config_path or "/etc/pacman.conf"
        self._extra_important = list(self.cfg.important_prefixes)
        self._extra_security = list(self.cfg.security_keywords)

    def _get_handle(self) -> pyalpm.Handle:
        if self._handle is None:
            self._handle = pycman.config.init_with_config(self._config_path)
        return self._handle

    # ---- 生命周期 ----
    def is_available(self) -> bool:
        try:
            import pyalpm  # noqa: F401
        except ImportError:
            return False
        return True

    def close(self) -> None:
        self._handle = None

    # ---- 操作 ----
    def refresh_db(self) -> None:
        h = self._get_handle()
        for db in h.get_syncdbs():
            db.update(force=False)

    def list_updates(self) -> list[Update]:
        h = self._get_handle()
        local = h.get_localdb()
        result: list[Update] = []

        for syncdb in h.get_syncdbs():
            for pkg in syncdb.pkgcache:
                lpkg = local.get_pkg(pkg.name)
                if lpkg is None:
                    continue
                if pyalpm.vercmp(pkg.version, lpkg.version) <= 0:
                    continue
                result.append(self._make_update(pkg, lpkg))
        return result

    @staticmethod
    def _find_sync_pkg(handle, name):
        for db in handle.get_syncdbs():
            pkg = db.get_pkg(name)
            if pkg is not None:
                return pkg
        return None
    
    def _wire_callbacks(self, handle, progress: ProgressCallback) -> None:
        """把 pyalpm 的 libalpm 回调映射到插件的 progress(pkg_id, percent, phase)。"""

        _last: dict[tuple[str, str], int] = {}

        def dlcb(filename, xfered, total):
            pct = int(xfered * 100 / total) if total else 0
            key = (filename, "download")
            prev = _last.get(key)
            # 同一包同一动作，进度没变且不是 100% 就跳过
            if prev is not None and pct == prev and pct < 100:
                return
            _last[key] = pct
            progress(filename, pct, "download")

        def progresscb(target, percent, _n, _i):
            key = (target or "", "install")
            prev = _last.get(key)
            if prev is not None and percent == prev and percent < 100:
                return
            _last[key] = percent
            progress(target or "", percent, "install")

        def eventcb(event, *args):
            # 事件很多，第一版只记 debug，避免刷屏
            log.debug("pacman event: %s args=%s", event, args)

        def questioncb(*args):
            # 第一版一律按默认回答（通常 libalpm 会选安全项）
            # 返回 None 表示"用默认答案"
            return None

        handle.dlcb = dlcb
        handle.progresscb = progresscb
        handle.eventcb = eventcb
        handle.questioncb = questioncb

    def install(self, ids, progress):
        handle = self._get_handle()
        self._wire_callbacks(handle, progress)

        names = {i.split(":", 1)[1] for i in ids}
        all_updates = {u.name for u in self.list_updates()}

        t = handle.init_transaction()
        try:
            try:
                if names >= all_updates and all_updates:
                    t.sysupgrade(False)
                else:
                    for name in names:
                        pkg = self._find_sync_pkg(handle, name)
                        if pkg is not None:
                            t.add_pkg(pkg)

                if not t.to_add and not t.to_remove:
                    return True
                t.prepare()
                t.commit()
                return True
            except pyalpm.error:
                return False
            finally:
                t.release()
        finally:
            self.close()

    # ---- 内部 ----
    def _make_update(self, pkg, lpkg) -> Update:
        sev = self._classify(pkg.name, pkg.desc or "")
        return Update(
            id=f"pacman:{pkg.name}",
            name=pkg.name,
            current_version=lpkg.version,
            new_version=pkg.version,
            severity=sev,
            description=pkg.desc or "",
            source=self.name,
        )

    def _classify(self, name: str, desc: str) -> Severity:
        important = _IMPORTANT_PREFIXES + tuple(self._extra_important)
        security = _SECURITY_HINTS + tuple(self._extra_security)
        lname = name.lower()
        ldesc = desc.lower()
        if any(h in ldesc for h in security):
            return Severity.SECURITY
        if any(lname.startswith(p) for p in important):
            return Severity.IMPORTANT
        return Severity.NORMAL
