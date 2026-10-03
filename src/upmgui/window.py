from __future__ import annotations

import asyncio
import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

log = logging.getLogger(__name__)

SEV_NAME = {0: "低", 1: "普通", 2: "重要", 3: "安全", 4: "严重"}
SEV_CSS = {0: "dim-label", 1: "", 2: "warning", 3: "error", 4: "error"}


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, client, loop: asyncio.AbstractEventLoop):
        super().__init__(application=app, title="系统更新")
        self.set_default_size(720, 480)
        self.client = client
        self.loop = loop              # ← 注入 asyncio 事件循环

        # ... 头部、listbox、status_label 构建（略，同上）
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        refresh_btn = Gtk.Button(label="检查更新")
        refresh_btn.connect("clicked", self._on_refresh)
        header.pack_start(refresh_btn)

        self.install_all_btn = Gtk.Button(label="全部安装")
        self.install_all_btn.add_css_class("suggested-action")
        self.install_all_btn.connect("clicked", self._on_install_all)
        header.pack_end(self.install_all_btn)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.listbox)
        scrolled.set_vexpand(True)

        self.status_label = Gtk.Label(label="就绪")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_margin_start(12)
        self.status_label.set_margin_bottom(6)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(scrolled)
        box.append(self.status_label)
        self.set_child(box)

    # ---------- 通用桥接 ----------
    def _submit(self, coro, on_done=None):
        if self.loop is None or not self.loop.is_running():
            log.error("asyncio loop not running; dropping task")
            GLib.idle_add(self._on_task_error, "内部错误：事件循环未就绪")
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        except Exception as e:
            log.exception("failed to submit coroutine")
            GLib.idle_add(self._on_task_error, str(e))
            return None

        def _done(fut):
            try:
                result = fut.result()
            except Exception as e:
                log.exception("async task failed")
                GLib.idle_add(self._on_task_error, str(e))
                return
            if on_done:
                GLib.idle_add(on_done, result)

        future.add_done_callback(_done)
        return future

    def _on_task_error(self, msg: str):
        self.status_label.set_text(f"错误：{msg}")

    def _set_busy(self, busy: bool, text: str = ""):
        self.install_all_btn.set_sensitive(not busy)
        if text:
            self.status_label.set_text(text)

    # ---------- 检查更新 ----------
    def _on_refresh(self, _btn):
        self._set_busy(True, "正在检查更新…")
        self._submit(self.client.check(force=True),
                     on_done=self._after_check)

    def _after_check(self, updates):
        self.set_updates(updates)
        self._set_busy(False)

    # ---------- 全部安装 ----------
    def _on_install_all(self, _btn):
        self._set_busy(True, "正在安装全部更新…")
        # 只安装 normal 及以上（1）
        self._submit(self.client.install_all(1),
                     on_done=self._after_install)

    # ---------- 单个安装 ----------
    def _on_install_one(self, _btn, pkg_id: str):
        self._set_busy(True, f"正在安装 {pkg_id}…")
        self._submit(self.client.install([pkg_id]),
                     on_done=self._after_install)

    def _after_install(self, ok: bool):
        if ok:
            self.status_label.set_text("安装完成")
        else:
            self.status_label.set_text("安装失败")
        # 装完后重新拉一次列表
        self._submit(self.client.get_updates(), on_done=self.set_updates)
        self._set_busy(False)

    # ---------- 数据填充 ----------
    def set_updates(self, updates: list):
        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)

        if not updates:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label="系统已是最新")
            label.set_margin_top(40)
            label.set_margin_bottom(40)
            row.set_child(label)
            self.listbox.append(row)
            self.status_label.set_text("无可用更新")
            return

        for u in updates:
            _id, name, cur, new, sev, src = u
            self.listbox.append(self._make_row(_id, name, cur, new, sev, src))

        self.status_label.set_text(f"共 {len(updates)} 项更新")

    def _make_row(self, pkg_id, name, cur, new, sev, src) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8); box.set_margin_bottom(8)
        box.set_margin_start(12); box.set_margin_end(12)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)

        title = Gtk.Label(label=name)
        title.set_halign(Gtk.Align.START)
        title.add_css_class("heading")

        version = Gtk.Label(label=f"{cur} → {new}")
        version.set_halign(Gtk.Align.START)
        version.add_css_class("dim-label")

        info.append(title); info.append(version)
        box.append(info)

        sev_label = Gtk.Label(label=SEV_NAME.get(sev, "?"))
        if css := SEV_CSS.get(sev):
            sev_label.add_css_class(css)
        box.append(sev_label)

        install_btn = Gtk.Button(label="安装")
        install_btn.connect("clicked", self._on_install_one, pkg_id)
        box.append(install_btn)

        row.set_child(box)
        return row