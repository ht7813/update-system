from __future__ import annotations

import logging
from importlib.metadata import entry_points

from .base import PackageManagerPlugin

log = logging.getLogger(__name__)

ENTRYPOINT_GROUP = "updated.plugins"


def load_plugins(enabled: list[str] | None = None) -> list[PackageManagerPlugin]:
    plugins: list[PackageManagerPlugin] = []
    eps = entry_points()
    # Python 3.10+ / 3.12 兼容写法
    candidates = eps.select(group=ENTRYPOINT_GROUP) if hasattr(eps, "select") \
                 else eps.get(ENTRYPOINT_GROUP, [])

    for ep in candidates:
        if enabled is not None and ep.name not in enabled:
            continue
        try:
            plugin_cls = ep.load()
            plugin = plugin_cls()
            if not plugin.is_available():
                log.info("plugin %s not available, skip", ep.name)
                continue
            plugins.append(plugin)
            log.info("loaded plugin %s (priority=%d)", plugin.name, plugin.priority)
        except Exception:
            log.exception("failed to load plugin %s", ep.name)

    plugins.sort(key=lambda p: p.priority)
    return plugins