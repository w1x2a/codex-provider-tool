#!/usr/bin/env python3
"""Dark provider-card desktop UI for the Codex provider tool."""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from codex_provider_tool import (
    Provider,
    ToolError,
    atomic_write,
    backup_file,
    find_provider,
    get_providers,
    load_auth_key,
    normalize_base_url,
    probe_provider,
    read_config,
    resolve_codex_home,
    safe_url,
    set_top_level_value,
    toml_string,
    upsert_provider,
)


BG = "#111827"
SURFACE = "#192336"
CARD = "#182235"
CARD_CURRENT = "#223a58"
BORDER = "#2b3a50"
BORDER_CURRENT = "#3c8cf5"
TEXT = "#f4f7fb"
MUTED = "#8f9bb0"
BLUE = "#55a8ff"
BLUE_DARK = "#2a72d5"
GREEN = "#50d6a1"
GREEN_DARK = "#183e3d"
PURPLE = "#7162f5"
RED = "#f2788b"


class ProviderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Codex Provider Tool")
        self.root.configure(bg=BG)
        self.root.geometry("1180x760")
        self.root.minsize(940, 620)

        self.home_var = tk.StringVar(value=str(resolve_codex_home(None)))
        self.current_banner_var = tk.StringVar(value="正在读取 Codex 配置...")
        self.status_var = tk.StringVar(value="就绪")
        self.providers: dict[str, Any] = {}
        self.probe_state: dict[str, tuple[str, str]] = {}
        self.card_canvas: tk.Canvas
        self.card_inner: tk.Frame

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Dark.TCombobox", fieldbackground="#1c293d", background="#1c293d", foreground=TEXT)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", "#1c293d")], foreground=[("readonly", TEXT)])
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        page = tk.Frame(self.root, bg=BG, padx=34, pady=28)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        header = tk.Frame(page, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        copy = tk.Frame(header, bg=BG)
        copy.grid(row=0, column=0, sticky="w")
        tk.Label(copy, text="PROVIDER", bg=BG, fg="#86c7ff", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(copy, text="供应商列表", bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 27, "bold")).pack(anchor="w", pady=(4, 2))
        tk.Label(
            copy,
            text="像 cc-switch 一样管理 Codex 第三方 API，当前使用的中转站会高亮显示。",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 11),
        ).pack(anchor="w")

        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=1, sticky="e", padx=(18, 0), pady=(4, 0))
        self._button(actions, "刷新", self.refresh, BLUE_DARK, "#3b8cf0").pack(side="left", padx=(0, 10))
        self._button(actions, "+  添加供应商", self.open_provider_dialog, PURPLE, "#8274ff", width=16).pack(side="left")

        banner = tk.Frame(page, bg="#15253a", highlightthickness=1, highlightbackground="#274d73")
        banner.grid(row=1, column=0, sticky="ew", pady=(22, 14))
        tk.Label(banner, textvariable=self.current_banner_var, bg="#15253a", fg="#c9e5ff", font=("Microsoft YaHei UI", 11), padx=16, pady=11).pack(anchor="w")

        settings = tk.Frame(page, bg=BG)
        settings.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        settings.columnconfigure(1, weight=1)
        tk.Label(settings, text="Codex Home", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(settings, textvariable=self.home_var, bg=BG, fg="#718198", font=("Consolas", 9), anchor="w").grid(row=0, column=1, padx=10, sticky="ew")
        self._button(settings, "选择目录", self.choose_home, "#263449", "#334661", width=10).grid(row=0, column=2, sticky="e")
        tk.Label(settings, textvariable=self.status_var, bg=BG, fg=GREEN, font=("Segoe UI", 9)).grid(row=0, column=3, padx=(18, 0), sticky="e")

        list_frame = tk.Frame(page, bg=BG)
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.card_canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0, bd=0)
        self.card_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.card_canvas.yview, bg=BG, troughcolor=BG, activebackground="#34445d", relief="flat", bd=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.card_canvas.configure(yscrollcommand=scrollbar.set)
        self.card_inner = tk.Frame(self.card_canvas, bg=BG)
        self.card_window = self.card_canvas.create_window((0, 0), window=self.card_inner, anchor="nw")
        self.card_inner.bind("<Configure>", lambda _event: self.card_canvas.configure(scrollregion=self.card_canvas.bbox("all")))
        self.card_canvas.bind("<Configure>", lambda event: self.card_canvas.itemconfigure(self.card_window, width=event.width))
        self.card_canvas.bind("<MouseWheel>", self._scroll_cards)

    def _button(self, parent: tk.Widget, text: str, command: Any, color: str, hover: str, width: int | None = None) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=TEXT,
            activebackground=hover,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=14,
            pady=8,
        )
        if width:
            button.configure(width=width)
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=color))
        return button

    def _scroll_cards(self, event: tk.Event) -> None:
        self.card_canvas.yview_scroll(int(-event.delta / 120), "units")

    def home_path(self) -> Path:
        value = self.home_var.get().strip()
        return Path(value).expanduser() if value else resolve_codex_home(None)

    def choose_home(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.home_path(), title="选择 Codex Home")
        if selected:
            self.home_var.set(selected)
            self.refresh()

    def refresh(self) -> None:
        try:
            home = self.home_path()
            _, data = read_config(home / "config.toml")
            providers = get_providers(data)
            self.providers = {provider.provider_id: provider for provider in providers}
            current_id = str(data.get("model_provider") or "")
            current = self.providers.get(current_id)
            key, source = load_auth_key(home)
            if current:
                base = safe_url(current.base_url) or "无 Base URL"
                self.current_banner_var.set(f"当前使用：{current.name}   ·   {data.get('model') or '未设置模型'}   ·   {base}")
            else:
                self.current_banner_var.set("当前使用：尚未配置有效 Provider")
            self.status_var.set(f"已加载 {len(providers)} 个 Provider" + (" · API Key 已配置" if key else " · API Key 未配置"))
            self.render_cards()
            self._log_status(f"已检查 {home} · key={source if key else 'missing'}")
        except Exception as exc:
            self.show_error(exc)

    def render_cards(self) -> None:
        for child in self.card_inner.winfo_children():
            child.destroy()
        if not self.providers:
            empty = tk.Frame(self.card_inner, bg=SURFACE, padx=24, pady=30, highlightthickness=1, highlightbackground=BORDER)
            empty.pack(fill="x", pady=8)
            tk.Label(empty, text="还没有 Provider", bg=SURFACE, fg=TEXT, font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
            tk.Label(empty, text="点击右上角“添加供应商”接入第三方中转站。", bg=SURFACE, fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(8, 0))
            return
        for provider in self.providers.values():
            self._render_card(provider)

    def _render_card(self, provider: Any) -> None:
        is_current = provider.current
        card = tk.Frame(
            self.card_inner,
            bg=CARD_CURRENT if is_current else CARD,
            padx=16,
            pady=15,
            highlightthickness=2 if is_current else 1,
            highlightbackground=BORDER_CURRENT if is_current else BORDER,
        )
        card.pack(fill="x", pady=8)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=0)

        icon = tk.Canvas(card, width=54, height=54, bg=card.cget("bg"), highlightthickness=0)
        icon.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")
        icon.create_oval(4, 4, 50, 50, fill="#eef4ff" if is_current else "#e8edf5", outline="#8dbbff" if is_current else "#c8d2e0", width=2)
        initial = (provider.name or provider.provider_id or "P")[0].upper()
        icon.create_text(27, 27, text=initial, fill=BLUE_DARK if is_current else "#49566b", font=("Segoe UI", 19, "bold"))

        info = tk.Frame(card, bg=card.cget("bg"))
        info.grid(row=0, column=1, rowspan=2, sticky="nsew")
        tk.Label(info, text=provider.name, bg=card.cget("bg"), fg=TEXT, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        tk.Label(info, text=safe_url(provider.base_url) or "无 Base URL", bg=card.cget("bg"), fg=BLUE, font=("Consolas", 10), cursor="hand2").pack(anchor="w", pady=(5, 0))
        meta = tk.Frame(info, bg=card.cget("bg"))
        meta.pack(anchor="w", pady=(10, 0))
        self._badge(meta, provider.category, "#2b405b", "#b9d8ff").pack(side="left", padx=(0, 7))
        self._badge(meta, provider.wire_api, "#253a3b", "#9be6c7").pack(side="left")

        details = tk.Frame(card, bg=card.cget("bg"), padx=16)
        details.grid(row=0, column=2, rowspan=2, sticky="e")
        source_text = "当前配置" if is_current else "TOML 配置"
        tk.Label(details, text=source_text, bg=card.cget("bg"), fg=MUTED, font=("Microsoft YaHei UI", 9)).pack(anchor="e")
        tk.Label(details, text=(self._current_model() if is_current else "切换后使用当前模型"), bg=card.cget("bg"), fg=TEXT, font=("Consolas", 10)).pack(anchor="e", pady=(5, 0))
        probe_text, probe_bg, probe_fg = self._probe_badge(provider.provider_id)
        self._badge(details, probe_text, probe_bg, probe_fg).pack(anchor="e", pady=(8, 0))

        actions = tk.Frame(card, bg=card.cget("bg"), padx=16)
        actions.grid(row=0, column=3, rowspan=2, sticky="e")
        if is_current:
            self._badge(actions, "当前", GREEN_DARK, GREEN).pack(fill="x", pady=(0, 7))
        else:
            self._button(actions, "切换", lambda p=provider: self.activate_provider(p.provider_id), BLUE_DARK, "#3b8cf0", width=7).pack(fill="x", pady=(0, 7))
        self._button(actions, "检测", lambda p=provider: self.probe_provider_id(p.provider_id), "#263449", "#334661", width=7).pack(fill="x", pady=(0, 7))
        self._button(actions, "编辑", lambda p=provider: self.open_provider_dialog(p), "#263449", "#334661", width=7).pack(fill="x")

    def _badge(self, parent: tk.Widget, text: str, bg: str, fg: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=("Microsoft YaHei UI", 9, "bold"), padx=9, pady=3)

    def _probe_badge(self, provider_id: str) -> tuple[str, str, str]:
        state, message = self.probe_state.get(provider_id, ("idle", "未检测"))
        if state == "ok":
            return message, GREEN_DARK, GREEN
        if state == "running":
            return "检测中...", "#30405b", "#b9d8ff"
        if state == "error":
            return "检测失败", "#4b2938", RED
        return "未检测", "#293348", MUTED

    def _current_model(self) -> str:
        try:
            _, data = read_config(self.home_path() / "config.toml")
            return str(data.get("model") or "未设置模型")
        except Exception:
            return "未设置模型"

    def _log_status(self, text: str) -> None:
        self.status_var.set(text)

    def show_error(self, error: Exception) -> None:
        self.status_var.set("操作失败")
        messagebox.showerror("Codex Provider Tool", str(error), parent=self.root)

    def activate_provider(self, provider_id: str) -> None:
        try:
            config_path = self.home_path() / "config.toml"
            text, data = read_config(config_path)
            find_provider(data, provider_id)
            updated = set_top_level_value(text, "model_provider", toml_string(provider_id))
            backup = backup_file(config_path, "provider-tool")
            atomic_write(config_path, updated)
            self._log_status(f"已切换到 {provider_id} · 备份已生成")
            self.refresh()
            if backup:
                self._log_status(f"已切换到 {provider_id} · 备份: {backup.name}")
        except Exception as exc:
            self.show_error(exc)

    def probe_provider_id(self, provider_id: str) -> None:
        try:
            _, data = read_config(self.home_path() / "config.toml")
            provider = find_provider(data, provider_id)
            key, source = load_auth_key(self.home_path())
        except Exception as exc:
            self.show_error(exc)
            return
        self.probe_state[provider_id] = ("running", "检测中...")
        self.render_cards()
        self._log_status(f"正在检测 {provider.name}...")

        def worker() -> None:
            try:
                result = probe_provider(provider, key, 10)
                self.root.after(0, lambda result=result, source=source: self.probe_finished(provider_id, result, source))
            except Exception as exc:
                self.root.after(0, lambda error=exc: self.show_error(error))

        threading.Thread(target=worker, daemon=True).start()

    def probe_finished(self, provider_id: str, result: Any, source: str) -> None:
        if result.ok:
            self.probe_state[provider_id] = ("ok", f"在线 · {len(result.models)} 个模型")
            self._log_status(f"检测成功 · {provider_id} · {len(result.models)} 个模型 · {result.elapsed_ms} ms")
        else:
            self.probe_state[provider_id] = ("error", "检测失败")
            self._log_status(f"检测失败 · {provider_id} · {result.message}")
        self.render_cards()

    def open_provider_dialog(self, provider: Any | None = None) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑供应商" if provider else "添加供应商")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        body = tk.Frame(dialog, bg=BG, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=("编辑供应商" if provider else "添加供应商"), bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 20, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(body, text="配置保存前会自动备份 config.toml。", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, columnspan=2, pady=(5, 15), sticky="w")
        body.columnconfigure(1, weight=1)

        provider_id = tk.StringVar(value=provider.provider_id if provider else "")
        label = tk.StringVar(value=provider.name if provider else "")
        base_url = tk.StringVar(value=provider.base_url if provider else "")
        model = tk.StringVar(value=self._current_model() if provider else "")
        wire_api = tk.StringVar(value=provider.wire_api if provider else "responses")
        requires_auth = tk.BooleanVar(value=provider.requires_openai_auth if provider else True)
        activate = tk.BooleanVar(value=provider.current if provider else True)
        api_key = tk.StringVar()
        write_auth = tk.BooleanVar(value=False)
        model_status = tk.StringVar(value="输入 Base URL 后会自动获取模型")
        fetch_generation = {"value": 0}
        fetch_job = {"id": None}
        normalizing_url = {"active": False}
        model_results: queue.Queue[tuple[str, int, Any, str | None]] = queue.Queue()

        def finish_model_fetch(generation: int, result: Any, source: str) -> None:
            if generation != fetch_generation["value"]:
                return
            try:
                if not dialog.winfo_exists():
                    return
            except tk.TclError:
                return
            fetch_button.configure(state="normal")
            if not result.ok:
                model_status.set(f"获取失败：{result.message}")
                return
            models = sorted(set(result.models), key=str.casefold)
            if not models:
                model_status.set("接口可访问，但 /models 没有返回模型")
                return
            model_combo.configure(values=models)
            current = model.get().strip()
            if not current:
                model.set(models[0])
            elif current not in models:
                model_combo.configure(values=[current, *models])
            model_status.set(f"已获取 {len(models)} 个模型 · Key 来源：{source}")

        def fail_model_fetch(generation: int, error: Exception) -> None:
            if generation != fetch_generation["value"]:
                return
            try:
                if not dialog.winfo_exists():
                    return
                fetch_button.configure(state="normal")
                model_status.set(f"获取失败：{error}")
            except tk.TclError:
                return

        def poll_model_results() -> None:
            try:
                while True:
                    kind, generation, payload, source = model_results.get_nowait()
                    if kind == "result":
                        finish_model_fetch(generation, payload, source or "missing")
                    else:
                        fail_model_fetch(generation, payload)
            except queue.Empty:
                pass
            try:
                if dialog.winfo_exists():
                    dialog.after(50, poll_model_results)
            except tk.TclError:
                return

        def fetch_models(auto: bool = False) -> None:
            try:
                url = normalize_base_url(base_url.get())
            except ToolError as exc:
                if not auto:
                    model_status.set(str(exc))
                return
            if base_url.get().strip() != url:
                normalizing_url["active"] = True
                base_url.set(url)
                normalizing_url["active"] = False
            try:
                key, source = load_auth_key(self.home_path(), api_key.get().strip() or None)
            except Exception as exc:
                model_status.set(f"读取 API Key 失败：{exc}")
                return
            fetch_generation["value"] += 1
            generation = fetch_generation["value"]
            fetch_button.configure(state="disabled")
            model_status.set("正在请求 /models ...")
            temporary = Provider(
                provider_id=provider_id.get().strip() or "preview",
                name=label.get().strip() or "Provider",
                base_url=url,
                wire_api=wire_api.get() or "responses",
                requires_openai_auth=requires_auth.get(),
            )

            def worker() -> None:
                try:
                    result = probe_provider(temporary, key, 10)
                    model_results.put(("result", generation, result, source))
                except Exception as exc:
                    model_results.put(("error", generation, exc, None))

            threading.Thread(target=worker, daemon=True).start()

        def schedule_model_fetch(*_args: object) -> None:
            if normalizing_url["active"]:
                return
            if fetch_job["id"] is not None:
                try:
                    dialog.after_cancel(fetch_job["id"])
                except tk.TclError:
                    pass
            if base_url.get().strip().startswith(("http://", "https://")):
                fetch_job["id"] = dialog.after(800, lambda: fetch_models(True))

        fields = (
            ("Provider ID", provider_id, "relay_a"),
            ("显示名称", label, "我的中转站"),
            ("Base URL", base_url, "https://relay.example/v1"),
        )
        for row, (name, variable, hint) in enumerate(fields, start=2):
            tk.Label(body, text=name, bg=BG, fg="#c5cfde", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0, padx=(0, 14), pady=7, sticky="w")
            entry = tk.Entry(body, textvariable=variable, bg="#1c293d", fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, font=("Segoe UI", 10), width=44)
            entry.grid(row=row, column=1, pady=7, ipady=7, sticky="ew")
            if not variable.get():
                entry.insert(0, "")

        row = 5
        tk.Label(body, text="Model", bg=BG, fg="#c5cfde", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0, padx=(0, 14), pady=7, sticky="w")
        model_row = tk.Frame(body, bg=BG)
        model_row.grid(row=row, column=1, pady=7, sticky="ew")
        model_row.columnconfigure(0, weight=1)
        model_combo = ttk.Combobox(model_row, textvariable=model, values=(), state="normal", width=31, style="Dark.TCombobox")
        model_combo.grid(row=0, column=0, sticky="ew")
        fetch_button = self._button(model_row, "获取模型", lambda: fetch_models(False), BLUE_DARK, "#3b8cf0", width=9)
        fetch_button.grid(row=0, column=1, padx=(8, 0))
        row += 1
        tk.Label(body, textvariable=model_status, bg=BG, fg="#79baff", font=("Microsoft YaHei UI", 9), anchor="w").grid(row=row, column=1, pady=(0, 5), sticky="ew")
        row += 1
        tk.Label(body, text="Wire API", bg=BG, fg="#c5cfde", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0, padx=(0, 14), pady=7, sticky="w")
        combo = ttk.Combobox(body, textvariable=wire_api, values=("responses", "chat"), state="readonly", width=41, style="Dark.TCombobox")
        combo.grid(row=row, column=1, pady=7, sticky="ew")
        row += 1
        options = tk.Frame(body, bg=BG)
        options.grid(row=row, column=1, pady=7, sticky="w")
        tk.Checkbutton(options, text="需要 OpenAI auth", variable=requires_auth, bg=BG, fg="#c5cfde", activebackground=BG, activeforeground=TEXT, selectcolor="#1c293d").pack(side="left")
        tk.Checkbutton(options, text="保存后立即启用", variable=activate, bg=BG, fg="#c5cfde", activebackground=BG, activeforeground=TEXT, selectcolor="#1c293d").pack(side="left", padx=(14, 0))
        row += 1
        tk.Label(body, text="API Key", bg=BG, fg="#c5cfde", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0, padx=(0, 14), pady=7, sticky="w")
        key_entry = tk.Entry(body, textvariable=api_key, show="*", bg="#1c293d", fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, font=("Segoe UI", 10), width=44)
        key_entry.grid(row=row, column=1, pady=7, ipady=7, sticky="ew")
        row += 1
        tk.Checkbutton(body, text="将 API Key 写入 auth.json", variable=write_auth, bg=BG, fg="#c5cfde", activebackground=BG, activeforeground=TEXT, selectcolor="#1c293d").grid(row=row, column=1, pady=(5, 14), sticky="w")

        buttons = tk.Frame(body, bg=BG)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e")
        self._button(buttons, "取消", dialog.destroy, "#263449", "#334661", width=8).pack(side="right")

        def save() -> None:
            args = argparse.Namespace(
                provider_id=provider_id.get().strip(),
                label=label.get().strip() or provider_id.get().strip(),
                base_url=base_url.get().strip(),
                model=model.get().strip(),
                wire_api=wire_api.get() or "responses",
                requires_openai_auth=requires_auth.get(),
                activate=activate.get(),
                api_key=api_key.get().strip() or None,
                write_auth=write_auth.get(),
            )
            if not args.provider_id or not args.base_url or not args.model:
                messagebox.showwarning("Codex Provider Tool", "Provider ID、Base URL 和 Model 不能为空。", parent=dialog)
                return
            try:
                config_path, backups = upsert_provider(self.home_path(), args)
                dialog.destroy()
                self.refresh()
                self._log_status(f"已保存 {args.provider_id} · {config_path.name}")
                if backups:
                    self._log_status(f"已保存 {args.provider_id} · 已生成 {len(backups)} 个备份")
            except Exception as exc:
                messagebox.showerror("Codex Provider Tool", str(exc), parent=dialog)

        self._button(buttons, "保存供应商", save, PURPLE, "#8274ff", width=12).pack(side="right", padx=(0, 8))
        dialog.after(50, poll_model_results)
        base_url.trace_add("write", schedule_model_fetch)
        api_key.trace_add("write", schedule_model_fetch)
        if base_url.get().strip().startswith(("http://", "https://")):
            dialog.after(350, lambda: fetch_models(True))
        dialog.update_idletasks()
        dialog.geometry(f"{max(dialog.winfo_reqwidth(), 560)}x{dialog.winfo_reqheight()}")

    def open_home(self) -> None:
        home = self.home_path()
        home.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(home))
        except OSError as exc:
            self.show_error(exc)


def run_gui() -> int:
    try:
        root = tk.Tk()
        ProviderApp(root)
        root.mainloop()
        return 0
    except Exception as exc:
        try:
            messagebox.showerror("Codex Provider Tool", str(exc))
        except Exception:
            print(f"GUI error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "--gui":
        raw_args = raw_args[1:]
    if not raw_args:
        return run_gui()
    from codex_provider_tool import main as cli_main

    return cli_main(raw_args)


if __name__ == "__main__":
    raise SystemExit(main())
