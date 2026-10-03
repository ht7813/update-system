from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterable


class Severity(IntEnum):
    LOW = 0
    NORMAL = 1
    IMPORTANT = 2
    SECURITY = 3
    CRITICAL = 4


@dataclass(frozen=True)
class Update:
    id: str                 # "pacman:firefox"
    name: str               # "firefox"
    current_version: str
    new_version: str
    severity: Severity
    description: str
    source: str             # 插件名 "pacman"

    def to_dbus_list(self) -> list:
        # (id, name, cur_ver, new_ver, severity, source)
        return [
            self.id,
            self.name,
            self.current_version,
            self.new_version,
            int(self.severity),
            self.source,
        ]


ProgressCallback = Callable[[str, int, str], None]  # (pkg_id, percent, phase)


class PackageManagerPlugin(ABC):
    """所有包管理器插件的基类。"""

    name: str = "unnamed"
    priority: int = 100

    @abstractmethod
    def is_available(self) -> bool:
        """本系统上是否可用（如可执行文件/库存在）。"""

    @abstractmethod
    def refresh_db(self) -> None:
        """刷新仓库元数据（可能需要 root）。"""

    @abstractmethod
    def list_updates(self) -> list[Update]:
        """返回可更新的包列表（同步阻塞）。"""

    @abstractmethod
    def install(self, ids: Iterable[str], progress: ProgressCallback) -> bool:
        """安装指定包（同步阻塞）。"""

    def close(self) -> None:
        """释放资源，默认无操作。"""