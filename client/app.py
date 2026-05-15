import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from . import config as client_config
from .api import ClientError, WeatherClient

KIND_FILTER_OPTIONS = (
    "all",
    "client_request",
    "client_response",
    "weather_request",
    "weather_response",
)


class TextDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, content: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x400")
        text = tk.Text(self, wrap="word")
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=4)


class AddCityDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Add city", city="", country=""):
        self._city_initial = city
        self._country_initial = country
        self.result = None
        super().__init__(parent, title=title)

    def body(self, master):
        ttk.Label(master, text="City:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.city_var = tk.StringVar(value=self._city_initial)
        self.city_entry = ttk.Entry(master, textvariable=self.city_var, width=30)
        self.city_entry.grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(master, text="Country:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.country_var = tk.StringVar(value=self._country_initial)
        ttk.Entry(master, textvariable=self.country_var, width=30).grid(row=1, column=1, padx=4, pady=4)
        return self.city_entry

    def apply(self):
        self.result = (self.city_var.get().strip(), self.country_var.get().strip())


class WeatherClientApp:
    def __init__(self) -> None:
        self.cfg = client_config.load()
        self.client: Optional[WeatherClient] = None

        self.root = tk.Tk()
        self.root.title("Weather Service Client")
        self.root.geometry("900x600")

        self._build_connection_bar()
        self._build_notebook()
        self._build_statusbar()

        self._update_admin_widgets_state()

    # ---------------------------------------------------------------- layout

    def _build_connection_bar(self) -> None:
        frame = ttk.Frame(self.root, padding=(8, 8))
        frame.pack(side="top", fill="x")

        ttk.Label(frame, text="Host:").pack(side="left")
        self.host_var = tk.StringVar(value=self.cfg["host"])
        ttk.Entry(frame, textvariable=self.host_var, width=18).pack(side="left", padx=(4, 8))

        ttk.Label(frame, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=str(self.cfg["port"]))
        ttk.Entry(frame, textvariable=self.port_var, width=8).pack(side="left", padx=(4, 8))

        ttk.Label(frame, text="Admin token:").pack(side="left")
        self.token_var = tk.StringVar(value=self.cfg["admin_token"])
        self.token_entry = ttk.Entry(frame, textvariable=self.token_var, show="*", width=24)
        self.token_entry.pack(side="left", padx=(4, 8))
        self.token_var.trace_add("write", lambda *_: self._update_admin_widgets_state())

        ttk.Button(frame, text="Connect", command=self.connect).pack(side="left")

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self._build_status_tab()
        self._build_log_tab()
        self._build_cities_tab()
        self._build_apis_tab()

    def _build_status_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Status")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=4)
        ttk.Button(top, text="Refresh", command=self.refresh_status).pack(side="left")

        self.status_text = tk.Text(frame, wrap="word")
        self.status_text.pack(fill="both", expand=True)
        self.status_text.configure(state="disabled")

    def _build_log_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Log")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=4)
        ttk.Label(top, text="Tail:").pack(side="left")
        self.tail_var = tk.StringVar(value="200")
        ttk.Entry(top, textvariable=self.tail_var, width=6).pack(side="left", padx=(4, 8))

        ttk.Label(top, text="Filter:").pack(side="left")
        self.kind_filter_var = tk.StringVar(value="all")
        ttk.Combobox(
            top,
            textvariable=self.kind_filter_var,
            values=KIND_FILTER_OPTIONS,
            state="readonly",
            width=18,
        ).pack(side="left", padx=(4, 8))

        ttk.Button(top, text="Refresh", command=self.refresh_log).pack(side="left")

        tree_container = ttk.Frame(frame)
        tree_container.pack(fill="both", expand=True)

        columns = ("id", "time", "kind", "summary")
        self.log_tree = ttk.Treeview(tree_container, columns=columns, show="headings")
        for col, width in zip(columns, (60, 200, 140, 500)):
            self.log_tree.heading(col, text=col)
            self.log_tree.column(col, width=width, anchor="w")

        log_vscroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.log_tree.yview)
        log_hscroll = ttk.Scrollbar(tree_container, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=log_vscroll.set, xscrollcommand=log_hscroll.set)

        self.log_tree.grid(row=0, column=0, sticky="nsew")
        log_vscroll.grid(row=0, column=1, sticky="ns")
        log_hscroll.grid(row=1, column=0, sticky="ew")
        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        self.log_tree.bind("<Double-1>", self._on_log_double_click)

        self._log_entries_by_id: dict[str, dict] = {}

    def _build_cities_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Cities")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=4)
        ttk.Button(top, text="Refresh", command=self.refresh_cities).pack(side="left")
        ttk.Button(top, text="Add", command=self.add_city).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Edit", command=self.edit_city).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="Delete", command=self.delete_city).pack(side="left", padx=(4, 0))

        columns = ("city", "country")
        self.cities_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col, width in zip(columns, (300, 100)):
            self.cities_tree.heading(col, text=col)
            self.cities_tree.column(col, width=width, anchor="w")
        self.cities_tree.pack(fill="both", expand=True)

    def _build_apis_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="API Keys")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=4)
        ttk.Button(top, text="Refresh", command=self.refresh_apis).pack(side="left")
        self.apis_add_btn = ttk.Button(top, text="Add", command=self.add_api)
        self.apis_add_btn.pack(side="left", padx=(8, 0))
        self.apis_edit_btn = ttk.Button(top, text="Edit", command=self.edit_api)
        self.apis_edit_btn.pack(side="left", padx=(4, 0))
        self.apis_delete_btn = ttk.Button(top, text="Delete", command=self.delete_api)
        self.apis_delete_btn.pack(side="left", padx=(4, 0))
        self.apis_reload_btn = ttk.Button(top, text="Reload from CSV", command=self.reload_apis)
        self.apis_reload_btn.pack(side="left", padx=(8, 0))

        self.apis_revealed_label = ttk.Label(top, text="")
        self.apis_revealed_label.pack(side="right")

        columns = ("key", "used", "limit")
        self.apis_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col, width in zip(columns, (400, 80, 80)):
            self.apis_tree.heading(col, text=col)
            self.apis_tree.column(col, width=width, anchor="w")
        self.apis_tree.pack(fill="both", expand=True)
        self._apis_raw: list[dict] = []

    def _build_statusbar(self) -> None:
        self.statusbar_var = tk.StringVar(value="Not connected")
        ttk.Label(self.root, textvariable=self.statusbar_var, anchor="w", relief="sunken").pack(
            side="bottom", fill="x"
        )

    # ---------------------------------------------------------------- helpers

    def _update_admin_widgets_state(self) -> None:
        has_token = bool(self.token_var.get().strip())
        state = "normal" if has_token else "disabled"
        for btn in (self.apis_add_btn, self.apis_edit_btn, self.apis_delete_btn, self.apis_reload_btn):
            btn.configure(state=state)

    def _require_client(self) -> Optional[WeatherClient]:
        if self.client is None:
            messagebox.showerror("Not connected", "Please connect to a server first.")
            return None
        return self.client

    def _persist_config(self) -> None:
        try:
            port = int(self.port_var.get())
        except ValueError:
            port = client_config.DEFAULTS["port"]
        self.cfg = {
            "host": self.host_var.get().strip() or client_config.DEFAULTS["host"],
            "port": port,
            "admin_token": self.token_var.get(),
        }
        client_config.save(self.cfg)

    # ---------------------------------------------------------------- actions

    def connect(self) -> None:
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be an integer.")
            return
        if not host:
            messagebox.showerror("Invalid host", "Host is required.")
            return

        self._persist_config()
        client = WeatherClient(host, port, admin_token=self.token_var.get().strip())
        try:
            health = client.health()
        except ClientError as exc:
            messagebox.showerror("Connection failed", str(exc))
            self.statusbar_var.set(f"Connection failed: {exc}")
            return

        self.client = client
        self.statusbar_var.set(f"Connected to {host}:{port}")
        self._render_status(health)
        self.refresh_cities()
        self.refresh_apis()
        self.refresh_log()

    def refresh_status(self) -> None:
        client = self._require_client()
        if client is None:
            return
        try:
            health = client.health()
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self._render_status(health)

    def _render_status(self, payload: dict) -> None:
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))
        self.status_text.configure(state="disabled")

    def refresh_log(self) -> None:
        client = self._require_client()
        if client is None:
            return
        try:
            limit = int(self.tail_var.get())
        except ValueError:
            limit = 0
        try:
            data = client.log(limit=limit)
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return

        entries = data.get("entries", [])
        kind_filter = self.kind_filter_var.get()

        self.log_tree.delete(*self.log_tree.get_children())
        self._log_entries_by_id.clear()

        for entry in entries:
            if kind_filter != "all" and entry.get("kind") != kind_filter:
                continue
            summary = self._summarize_log_entry(entry)
            iid = str(entry.get("id", ""))
            self.log_tree.insert(
                "",
                "end",
                iid=iid,
                values=(entry.get("id"), entry.get("time", ""), entry.get("kind", ""), summary),
            )
            self._log_entries_by_id[iid] = entry

        total = data.get("total", len(entries))
        cap = data.get("capacity", "?")
        self.statusbar_var.set(f"Log: showing {len(self.log_tree.get_children())} of {total} (capacity {cap})")

    @staticmethod
    def _summarize_log_entry(entry: dict) -> str:
        kind = entry.get("kind")
        if kind == "client_request":
            return f"{entry.get('method', '')} {entry.get('path', '')} from {entry.get('remote', '')}"
        if kind == "client_response":
            return f"{entry.get('method', '')} {entry.get('path', '')} -> {entry.get('status', '')} ({entry.get('elapsed_ms', '?')} ms)"
        if kind == "weather_request":
            params = entry.get("params") or {}
            return f"GET {entry.get('url', '')} q={params.get('q', '')}"
        if kind == "weather_response":
            if "error" in entry:
                return f"ERROR {entry.get('query', '')}: {entry.get('error', '')}"
            return f"{entry.get('query', '')} -> {entry.get('status', '')} ({entry.get('elapsed_ms', '?')} ms)"
        return ""

    def _on_log_double_click(self, _event) -> None:
        sel = self.log_tree.selection()
        if not sel:
            return
        entry = self._log_entries_by_id.get(sel[0])
        if entry is None:
            return
        TextDialog(self.root, f"Log entry #{entry.get('id')}", json.dumps(entry, indent=2, ensure_ascii=False))

    def refresh_cities(self) -> None:
        client = self._require_client()
        if client is None:
            return
        try:
            cities = client.cities_list()
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.cities_tree.delete(*self.cities_tree.get_children())
        for entry in cities:
            self.cities_tree.insert("", "end", values=(entry.get("city", ""), entry.get("country", "")))

    def add_city(self) -> None:
        client = self._require_client()
        if client is None:
            return
        dlg = AddCityDialog(self.root, title="Add city")
        if not dlg.result:
            return
        city, country = dlg.result
        if not city:
            messagebox.showerror("Invalid input", "City is required.")
            return
        try:
            client.cities_add(city, country)
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_cities()

    def edit_city(self) -> None:
        client = self._require_client()
        if client is None:
            return
        sel = self.cities_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a city to edit.")
            return
        values = self.cities_tree.item(sel[0], "values")
        city, country = values[0], values[1]
        dlg = AddCityDialog(self.root, title=f"Edit {city}", city=city, country=country)
        if not dlg.result:
            return
        new_city, new_country = dlg.result
        if new_city != city:
            messagebox.showinfo("Note", "City name cannot be changed; only country is updated.")
        try:
            client.cities_update(city, new_country)
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_cities()

    def delete_city(self) -> None:
        client = self._require_client()
        if client is None:
            return
        sel = self.cities_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a city to delete.")
            return
        city = self.cities_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm", f"Delete city '{city}'?"):
            return
        try:
            client.cities_delete(city)
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_cities()

    def refresh_apis(self) -> None:
        client = self._require_client()
        if client is None:
            return
        try:
            data = client.apis_list()
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self._apis_raw = data.get("keys", [])
        self.apis_revealed_label.configure(
            text="Keys revealed" if data.get("revealed") else "Keys masked (token required for full view)"
        )
        self.apis_tree.delete(*self.apis_tree.get_children())
        for entry in self._apis_raw:
            self.apis_tree.insert(
                "", "end", values=(entry.get("key", ""), entry.get("used", 0), entry.get("limit", ""))
            )

    def add_api(self) -> None:
        client = self._require_client()
        if client is None:
            return
        key = simpledialog.askstring("Add API key", "New API key:", parent=self.root)
        if not key:
            return
        try:
            client.apis_add(key.strip())
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_apis()
        self.refresh_status()

    def edit_api(self) -> None:
        client = self._require_client()
        if client is None:
            return
        sel = self.apis_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a key to edit.")
            return
        old_key = self.apis_tree.item(sel[0], "values")[0]
        if "***" in old_key:
            messagebox.showerror(
                "Key is masked",
                "Cannot edit a masked key. Use Refresh after entering a valid admin token to reveal full keys.",
            )
            return
        new_key = simpledialog.askstring("Edit API key", "New value:", initialvalue=old_key, parent=self.root)
        if not new_key:
            return
        try:
            client.apis_update(old_key, new_key.strip())
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_apis()

    def delete_api(self) -> None:
        client = self._require_client()
        if client is None:
            return
        sel = self.apis_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a key to delete.")
            return
        key = self.apis_tree.item(sel[0], "values")[0]
        if "***" in key:
            messagebox.showerror(
                "Key is masked",
                "Cannot delete a masked key. Use Refresh after entering a valid admin token to reveal full keys.",
            )
            return
        if not messagebox.askyesno("Confirm", "Delete this API key?"):
            return
        try:
            client.apis_delete(key)
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_apis()
        self.refresh_status()

    def reload_apis(self) -> None:
        client = self._require_client()
        if client is None:
            return
        try:
            client.apis_reload()
        except ClientError as exc:
            messagebox.showerror("Request failed", str(exc))
            return
        self.refresh_apis()
        self.refresh_status()

    # ---------------------------------------------------------------- entry

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    WeatherClientApp().run()
