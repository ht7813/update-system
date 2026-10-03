from __future__ import annotations

import logging

import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify, GdkPixbuf

log = logging.getLogger(__name__)

# 与 core.Severity 对齐
SEV_LOW = 0
SEV_NORMAL = 1
SEV_IMPORTANT = 2
SEV_SECURITY = 3
SEV_CRITICAL = 4

ICON_IMPORTANT = "software-update-urgent"
ICON_NORMAL = "software-update-available"


def init(app_name: str = "Update Manager") -> None:
    if not Notify.is_initted():
        Notify.init(app_name)


def notify_updates(updates: list, on_click=None) -> None:
    """弹一条汇总通知。updates 为 D-Bus 返回的 tuple 列表。"""
    if not updates:
        return

    max_sev = max(u[4] for u in updates)
    important = max_sev >= SEV_IMPORTANT
    word = "重要" if important else ""
    title = "系统更新可用"
    body = f"你的电脑缺少{word}更新（共 {len(updates)} 项）"

    n = Notify.Notification.new(title, body, ICON_IMPORTANT if important else ICON_NORMAL)
    n.set_urgency(Notify.Urgency.CRITICAL if important else Notify.Urgency.NORMAL)
    n.set_timeout(10000)  # 毫秒

    if on_click:
        # 点击通知触发回调
        n.add_action("default", "打开", lambda *_: on_click(), None)

    try:
        n.show()
    except Exception:
        log.exception("failed to show notification")