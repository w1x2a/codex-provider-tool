#!/usr/bin/env python3
"""Tkinter desktop UI for the Codex provider tool."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from codex_provider_tool import (
    ToolError,
    atomic_write,
    backup_file,
    find_provider,
    get_providers,
    load_auth_key,
    probe_provider,
    read_config,
    resolve_codex_home,
    safe_url,
    set_top_level_value,
    toml_string,
    upsert_provider,
)


class ProviderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Codex Provider Tool")
        self.root.minsize(900, 620)
        self.root.geometry("1080x720")

        self.home_var = tk.StringVar(value=str(resolve_codex_home(None)))
        self.model_var = tk.StringVar(value="-")
        self.active_var = tk.StringVar(value="-")
        self.config_var = tk.StringVar(value="-")
        self.auth_var = tk.StringVar(value="-")
        self.status_var = tk.StringVar(value="就绪")

        self.provider_id_var = tk.StringVar()
        self.provider_label_var = tk.StringVar()
        self.base_url_var = tk.StringVar()
        self.provider_model_var = tk.StringVar()
        self.wire_api_var = tk.StringVar(value="responses")
        self.requires_auth_var = tk.BooleanVar(value=True)
        self.activate_var = tk.BooleanVar(value=True)
        self.api_key_var = tk.StringVar()
        self.write_auth_var = tk.BooleanVar(value=False)

        self.providers: dict[str, Any] = {}
        self.tree: ttk.Treeview
        self.output: tk.Text
        self._build_style()
        self._build_ui()
        self.refresh()

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6b7a")
        style.configure("Status.TLabel", foreground="#176b3a")

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="Codex Provider Tool", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=2, padx=(16, 0), sticky="e")
        ttk.Label(header, text="Codex Home").grid(row=1, column=0, pady=(12, 0), sticky="w")
        ttk.Entry(header, textvariable=self.home_var).grid(row=1, column=1, pady=(12, 0), padx=10, sticky="ew")
        ttk.Button(header, text="选择目录", command=self.choose_home).grid(row=1, column=2, pady=(12, 0), sticky="e")
        ttk.Button(header, text="刷新", command=self.refresh).grid(row=1, column=3, pady=(12, 0), padx=(8, 0), sticky="e")
        ttk.Button(header, text="打开目录", command=self.open_home).grid(row=1, column=4, pady=(12, 0), padx=(8, 0), sticky="e")

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")

        check_tab = ttk.Frame(notebook, padding=14)
        relay_tab = ttk.Frame(notebook, padding=14)
        notebook.add(check_tab, text="检查与探测")
        notebook.add(relay_tab, text="接入中转站")
        self._build_check_tab(check_tab)
        self._build_relay_tab(relay_tab)

    def _build_check_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        tab.rowconfigure(4, weight=1)

        summary = ttk.LabelFrame(tab, text="当前状态", padding=12)
        summary.grid(row=0, column=0, sticky="ew")
        for column in range(4):
            summary.columnconfigure(column, weight=1)
        self._summary_item(summary, 0, "当前模型", self.model_var)
        self._summary_item(summary, 1, "当前 Provider", self.active_var)
        self._summary_item(summary, 2, "配置文件", self.config_var)
        self._summary_item(summary, 3, "API Key", self.auth_var)

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=1, column=0, pady=(12, 8), sticky="ew")
        ttk.Button(toolbar, text="探测选中 Provider", command=self.probe_selected).pack(side="left")
        ttk.Button(toolbar, text="切换到选中 Provider", command=self.activate_selected).pack(side="left", padx=8)
        ttk.Label(toolbar, text="只执行 GET /models，不发送对话请求", style="Muted.TLabel").pack(side="left", padx=8)

        provider_frame = ttk.LabelFrame(tab, text="Provider 列表", padding=8)
        provider_frame.grid(row=2, column=0, sticky="nsew")
        provider_frame.columnconfigure(0, weight=1)
        provider_frame.rowconfigure(0, weight=1)
        columns = ("id", "name", "category", "base_url", "wire_api", "current")
        self.tree = ttk.Treeview(provider_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID",
            "name": "名称",
            "category": "类型",
            "base_url": "Base URL",
            "wire_api": "Wire API",
            "current": "当前",
        }
        widths = {"id": 140, "name": 150, "category": 190, "base_url": 300, "wire_api": 90, "current": 70}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(provider_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_provider_selected)

        ttk.Label(tab, text="操作日志").grid(row=3, column=0, pady=(12, 5), sticky="w")
        output_frame = ttk.Frame(tab)
        output_frame.grid(row=4, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self.output = tk.Text(output_frame, height=7, wrap="word", state="disabled", font=("Consolas", 10))
        self.output.grid(row=0, column=0, sticky="nsew")
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        output_scroll.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=output_scroll.set)

    def _summary_item(self, parent: ttk.Frame, column: int, title: str, variable: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, padx=8, sticky="ew")
        ttk.Label(frame, text=title, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(frame, textvariable=variable).pack(anchor="w", pady=(3, 0))

    def _build_relay_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)

        form = ttk.LabelFrame(tab, text="OpenAI-compatible Provider", padding=16)
        form.grid(row=0, column=0, columnspan=2, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self._form_entry(form, 0, 0, "Provider ID", self.provider_id_var, "例如 relay_a")
        self._form_entry(form, 0, 2, "显示名称", self.provider_label_var, "例如 我的中转站")
        self._form_entry(form, 1, 0, "Base URL", self.base_url_var, "例如 https://relay.example/v1")
        self._form_entry(form, 1, 2, "Model", self.provider_model_var, "例如 gpt-5.5")

        ttk.Label(form, text="Wire API").grid(row=2, column=0, padx=(0, 8), pady=10, sticky="w")
        ttk.Combobox(form, textvariable=self.wire_api_var, values=("responses", "chat"), state="readonly", width=18).grid(row=2, column=1, pady=10, sticky="w")
        ttk.Checkbutton(form, text="需要 OpenAI auth", variable=self.requires_auth_var).grid(row=2, column=2, pady=10, sticky="w")
        ttk.Checkbutton(form, text="保存后立即启用", variable=self.activate_var).grid(row=2, column=3, pady=10, sticky="w")

        ttk.Label(form, text="API Key").grid(row=3, column=0, padx=(0, 8), pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.api_key_var, show="*", width=42).grid(row=3, column=1, pady=10, sticky="ew")
        ttk.Checkbutton(form, text="写入 auth.json", variable=self.write_auth_var).grid(row=3, column=2, pady=10, sticky="w")
        ttk.Label(form, text="默认只用于本次保存，不会写入 config.toml", style="Muted.TLabel").grid(row=3, column=3, pady=10, sticky="w")

        actions = ttk.Frame(tab)
        actions.grid(row=1, column=0, columnspan=2, pady=(14, 0), sticky="w")
        ttk.Button(actions, text="保存 Provider", command=self.save_provider).pack(side="left")
        ttk.Button(actions, text="清空表单", command=self.clear_form).pack(side="left", padx=8)
        ttk.Label(tab, text="写入或切换前会在 config.toml 同目录生成时间戳备份。", style="Muted.TLabel").grid(row=2, column=0, columnspan=2, pady=(18, 0), sticky="w")

    def _form_entry(self, parent: ttk.Frame, row: int, label_column: int, label: str, variable: tk.StringVar, hint: str) -> None:
        value_column = label_column + 1
        ttk.Label(parent, text=label).grid(row=row, column=label_column, padx=(0, 8), pady=10, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=value_column, padx=(0, 20), pady=10, sticky="ew")

    def home_path(self) -> Path:
        value = self.home_var.get().strip()
        return Path(value).expanduser() if value else resolve_codex_home(None)

    def choose_home(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.home_path(), title="选择 Codex Home")
        if selected:
            self.home_var.set(selected)
            self.refresh()

    def open_home(self) -> None:
        home = self.home_path()
        home.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(home))
        except OSError as exc:
            self.show_error(exc)

    def log(self, message: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", message.rstrip() + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def show_error(self, error: Exception) -> None:
        self.status_var.set("操作失败")
        self.log(f"错误: {error}")
        messagebox.showerror("Codex Provider Tool", str(error), parent=self.root)

    def refresh(self) -> None:
        try:
            home = self.home_path()
            _, data = read_config(home / "config.toml")
            key, source = load_auth_key(home)
            self.model_var.set(str(data.get("model") or "未设置"))
            self.active_var.set(str(data.get("model_provider") or "未设置"))
            self.config_var.set("已找到" if (home / "config.toml").is_file() else "不存在")
            self.auth_var.set(f"已配置 ({source})" if key else "未配置")
            self.providers = {provider.provider_id: provider for provider in get_providers(data)}
            for item in self.tree.get_children():
                self.tree.delete(item)
            for provider in self.providers.values():
                self.tree.insert(
                    "",
                    "end",
                    iid=provider.provider_id,
                    values=(
                        provider.provider_id,
                        provider.name,
                        provider.category,
                        safe_url(provider.base_url),
                        provider.wire_api,
                        "是" if provider.current else "",
                    ),
                )
            current_id = str(data.get("model_provider") or "")
            if current_id in self.providers:
                self.tree.selection_set(current_id)
                self.tree.focus(current_id)
                self.fill_form(self.providers[current_id])
            self.status_var.set(f"已刷新: {len(self.providers)} 个 Provider")
            self.log(f"已检查 {home}; API key: {'已配置' if key else '未配置'}")
        except Exception as exc:
            self.show_error(exc)

    def on_provider_selected(self, _event: object) -> None:
        selected = self.tree.selection()
        if selected and selected[0] in self.providers:
            self.fill_form(self.providers[selected[0]])

    def fill_form(self, provider: Any) -> None:
        self.provider_id_var.set(provider.provider_id)
        self.provider_label_var.set(provider.name)
        self.base_url_var.set(provider.base_url)
        self.provider_model_var.set(self.model_var.get() if provider.current else "")
        self.wire_api_var.set(provider.wire_api or "responses")
        self.requires_auth_var.set(provider.requires_openai_auth)
        self.activate_var.set(provider.current)

    def clear_form(self) -> None:
        self.provider_id_var.set("")
        self.provider_label_var.set("")
        self.base_url_var.set("")
        self.provider_model_var.set("")
        self.wire_api_var.set("responses")
        self.requires_auth_var.set(True)
        self.activate_var.set(True)
        self.api_key_var.set("")
        self.write_auth_var.set(False)

    def selected_provider_id(self) -> str | None:
        selected = self.tree.selection()
        return selected[0] if selected else None

    def activate_selected(self) -> None:
        provider_id = self.selected_provider_id()
        if not provider_id:
            messagebox.showinfo("Codex Provider Tool", "请先选择一个 Provider。", parent=self.root)
            return
        try:
            home = self.home_path()
            config_path = home / "config.toml"
            text, data = read_config(config_path)
            find_provider(data, provider_id)
            updated = set_top_level_value(text, "model_provider", toml_string(provider_id))
            model = self.provider_model_var.get().strip()
            if model:
                updated = set_top_level_value(updated, "model", toml_string(model))
            backup = backup_file(config_path, "provider-tool")
            atomic_write(config_path, updated)
            self.log(f"已切换到 {provider_id}; 备份: {backup or '无'}")
            self.refresh()
        except Exception as exc:
            self.show_error(exc)

    def probe_selected(self) -> None:
        provider_id = self.selected_provider_id()
        if not provider_id:
            messagebox.showinfo("Codex Provider Tool", "请先选择一个 Provider。", parent=self.root)
            return
        try:
            home = self.home_path()
            _, data = read_config(home / "config.toml")
            provider = find_provider(data, provider_id)
            key, source = load_auth_key(home, self.api_key_var.get().strip() or None)
        except Exception as exc:
            self.show_error(exc)
            return

        self.status_var.set(f"正在探测 {provider_id}...")
        self.log(f"开始探测 {provider_id} ({safe_url(provider.base_url)})")

        def worker() -> None:
            try:
                result = probe_provider(provider, key, 10)
                self.root.after(0, lambda: self.probe_finished(result, source))
            except Exception as exc:
                self.root.after(0, lambda error=exc: self.show_error(error))

        threading.Thread(target=worker, daemon=True).start()

    def probe_finished(self, result: Any, source: str) -> None:
        self.status_var.set("探测完成")
        state = "成功" if result.ok else "失败"
        self.log(f"探测{state}: {result.message}; key={source}; {result.elapsed_ms} ms")
        if result.models:
            self.log("模型: " + ", ".join(result.models))

    def save_provider(self) -> None:
        provider_id = self.provider_id_var.get().strip()
        label = self.provider_label_var.get().strip()
        base_url = self.base_url_var.get().strip()
        model = self.provider_model_var.get().strip()
        if not provider_id or not base_url or not model:
            messagebox.showwarning("Codex Provider Tool", "Provider ID、Base URL 和 Model 不能为空。", parent=self.root)
            return
        args = argparse.Namespace(
            provider_id=provider_id,
            label=label or provider_id,
            base_url=base_url,
            model=model,
            wire_api=self.wire_api_var.get() or "responses",
            requires_openai_auth=self.requires_auth_var.get(),
            activate=self.activate_var.get(),
            api_key=self.api_key_var.get().strip() or None,
            write_auth=self.write_auth_var.get(),
        )
        try:
            config_path, backups = upsert_provider(self.home_path(), args)
            self.log(f"已保存 {provider_id}: {config_path}")
            for backup in backups:
                self.log(f"备份: {backup}")
            self.status_var.set("Provider 已保存")
            self.refresh()
        except Exception as exc:
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
