from __future__ import annotations

import asyncio
import logging
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, GLib

from .dbus_client import UpdateClient
from . import notify
from .window import MainWindow
from updated.config import load_config

log = logging.getLogger("upmgui")


class UpdateApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.github.ht7813.UpdateManager.Gui")
        self.config = load_config()
        self.client = UpdateClient()
        self.window: MainWindow | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._notified_snapshot: set[str] = set()
        self._started = False

    def do_activate(self):
        if not self._started:
            self._start_async_worker()      # 先起 loop
            self._started = True

        if self.window is None:
            self.window = MainWindow(self, self.client, self.loop)
        self.window.present()

    def _start_async_worker(self):
        self.loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()

        def _run():
            asyncio.set_event_loop(self.loop)
            self.loop.call_soon(self._loop_ready.set)
            self.loop.create_task(self._async_main())
            self.loop.run_forever()

        t = threading.Thread(target=_run, daemon=True, name="asyncio-worker")
        t.start()
        self._loop_ready.wait(timeout=5)   # 等 loop 就绪

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._async_main())

    async def _async_main(self):
        log.info("asyncio worker: starting")
        try:
            await self.client.connect()
            log.info("asyncio worker: connected")
        except Exception:
            log.exception("asyncio worker: connect failed")
            return
        self.client.watch_updates(self._on_updates_from_daemon)
        try:
            updates = await self.client.get_updates()
            GLib.idle_add(self.window.set_updates, updates)
        except Exception:
            log.exception("asyncio worker: get_updates failed")

    def _on_updates_from_daemon(self, updates: list):
        GLib.idle_add(self.window.set_updates, updates)
        GLib.idle_add(self._maybe_notify, updates)

    def _maybe_notify(self, updates: list):
        if not self.config.notify.enabled:
            return
        min_sev = self.config.severity_value(self.config.notify.min_severity)
        if max(u[4] for u in updates) < min_sev:
            return
        current = {u[0] for u in updates}
        if not current:
            self._notified_snapshot = set()
            return
        if current - self._notified_snapshot:
            notify.notify_updates(updates, on_click=self._focus_window)
        self._notified_snapshot = current

    def _focus_window(self):
        if self.window:
            self.window.present()


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    notify.init("Update Manager")
    UpdateApp().run(None)


if __name__ == "__main__":
    main()