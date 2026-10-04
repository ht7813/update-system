from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_PATH = Path("/etc/updated/config.toml")

SEVERITY_NAMES = {
    "low": 0,
    "normal": 1,
    "important": 2,
    "security": 3,
    "critical": 4,
}


# ---------- 各节 ----------
@dataclass
class DaemonConfig:
    default_severity: str = "normal"
    log_level: str = "info"


@dataclass
class NotifyConfig:
    enabled: bool = True
    min_severity: str = "normal"
    timeout: int = 10000


@dataclass
class InstallConfig:
    refresh_before_install: bool = True


@dataclass
class PacmanPluginConfig:
    config_path: str = "/etc/pacman.conf"
    important_prefixes: list[str] = field(default_factory=list)
    security_keywords: list[str] = field(default_factory=list)


@dataclass
class PluginsConfig:
    enabled: list[str] | None = None
    pacman: PacmanPluginConfig = field(default_factory=PacmanPluginConfig)


@dataclass
class SeverityRule:
    pattern: str
    level: str


@dataclass
class SeverityConfig:
    rules: list[SeverityRule] = field(default_factory=list)


@dataclass
class GuiConfig:
    check_on_start: bool = True
    close_to_tray: bool = True


# ---------- 顶层 ----------
@dataclass
class Config:
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    install: InstallConfig = field(default_factory=InstallConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    severity: SeverityConfig = field(default_factory=SeverityConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)

    # 便利方法
    def severity_value(self, name: str) -> int:
        return SEVERITY_NAMES.get(name, 1)


# ---------- 加载 ----------
def _get(d: dict, key: str, default):
    return d.get(key, default)


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        log.warning("config %s not found, using defaults", path)
        return Config()

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        log.error("config %s is invalid TOML: %s", path, e)
        return Config()
    except OSError as e:
        log.error("cannot read config %s: %s", path, e)
        return Config()

    cfg = Config()

    # [daemon]
    if sec := data.get("daemon"):
        cfg.daemon = DaemonConfig(
            default_severity=_get(sec, "default_severity", "normal"),
            log_level=_get(sec, "log_level", "info"),
        )

    # [notify]
    if sec := data.get("notify"):
        cfg.notify = NotifyConfig(
            enabled=_get(sec, "enabled", True),
            min_severity=_get(sec, "min_severity", "normal"),
            timeout=_get(sec, "timeout", 10000),
        )

    # [install]
    if sec := data.get("install"):
        cfg.install = InstallConfig(
            refresh_before_install=_get(sec, "refresh_before_install", True),
        )

    # [plugins]
    if sec := data.get("plugins"):
        pacman_sec = sec.get("pacman", {})
        cfg.plugins = PluginsConfig(
            enabled=_get(sec, "enabled", None),
            pacman=PacmanPluginConfig(
                config_path=_get(pacman_sec, "config_path", "/etc/pacman.conf"),
                important_prefixes=_get(pacman_sec, "important_prefixes", []),
                security_keywords=_get(pacman_sec, "security_keywords", []),
            ),
        )

    # [severity]
    if sec := data.get("severity"):
        rules = []
        for r in sec.get("rules", []):
            if "pattern" in r and "level" in r:
                rules.append(SeverityRule(r["pattern"], r["level"]))
        cfg.severity = SeverityConfig(rules=rules)

    # [gui]
    if sec := data.get("gui"):
        cfg.gui = GuiConfig(
            check_on_start=_get(sec, "check_on_start", True),
            close_to_tray=_get(sec, "close_to_tray", True),
        )

    return cfg
