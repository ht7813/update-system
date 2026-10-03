from __future__ import annotations

import logging

from dbus_next.aio import MessageBus
from dbus_next import Variant

log = logging.getLogger(__name__)

POLKIT_BUS = "org.freedesktop.PolicyKit1"
POLKIT_PATH = "/org/freedesktop/PolicyKit1/Authority"
POLKIT_IFACE = "org.freedesktop.PolicyKit1.Authority"

_FLAG_ALLOW_USER_INTERACTION = 1


async def check_auth(
    bus: MessageBus,
    sender: str,
    action_id: str,
    details: dict | None = None,
) -> bool:
    if details is None:
        details = {}

    try:
        intro = await bus.introspect(POLKIT_BUS, POLKIT_PATH)
        obj = bus.get_proxy_object(POLKIT_BUS, POLKIT_PATH, intro)
        authority = obj.get_interface(POLKIT_IFACE)

        # subject 签名 (sa{sv})：
        #   - struct -> list（不是 tuple）
        #   - a{sv} -> dict[str, Variant]
        subject = [
            "system-bus-name",
            {"name": Variant("s", sender)},
        ]

        result = await authority.call_check_authorization(
            subject,
            action_id,
            details,                # a{ss} -> dict[str, str]
            _FLAG_ALLOW_USER_INTERACTION,
            "",
        )
        # result 签名 (bba{ss}) -> [is_authorized, is_challenge, details]
        return bool(result[0])
    except Exception:
        log.exception("polkit check failed for action %s", action_id)
        return False