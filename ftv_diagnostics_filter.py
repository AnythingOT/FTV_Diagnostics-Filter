"""
FTV Diagnostics Filter - by AnythingOT
Filter FactoryTalk Diagnostics Viewer XML exports with unlimited
contains / does-not-contain rules, preview the results, export to CSV.

GUI:
    python ftv_diagnostics_filter.py
    python ftv_diagnostics_filter.py export.xml            (opens with file loaded)

Command line (no window):
    python ftv_diagnostics_filter.py export.xml --contains DataLog --exclude Off
    python ftv_diagnostics_filter.py export.xml -c Tank -c Pump --any -o out.csv

Uses regex, not an XML parser, so protected/garbled sections elsewhere in
the export don't stop it - it pulls out every <Item ...> element it can read.
"""
import argparse
import csv
import html
import json
import queue
import re
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont
except ImportError:  # core logic and CLI still work without Tk
    tk = ttk = filedialog = messagebox = tkfont = None

APP_NAME = "FTV Diagnostics Filter"
APP_VERSION = "1.0.1"
BRAND = "AnythingOT"

FIELDS = ["datetime", "location", "provider", "severity", "message", "username"]
FIELD_CHOICES = ["message", "any field"] + [f for f in FIELDS if f != "message"]
OPS = ["contains", "does not contain"]
PREVIEW_LIMIT = 5000  # rows drawn in the table; export always writes all matches

# Attribute values may legally contain '>' (e.g. message="Level > 90"), so the
# tag body is matched as: non-quote chars OR a complete quoted string.
ITEM_RE = re.compile(r"""<Item\b((?:[^>"']|"[^"]*"|'[^']*')*)>""", re.IGNORECASE)
ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


# =============================================================== core logic
def read_text(path: Path) -> str:
    """Decode an export, handling the UTF-16 files Rockwell tools often write."""
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw[1:2] == b"\x00":
        return raw.decode("utf-16-le", errors="replace")
    if raw[0:1] == b"\x00":
        return raw.decode("utf-16-be", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def parse_items(text: str) -> list:
    """Return one dict per <Item>, attribute names lower-cased."""
    items = []
    for m in ITEM_RE.finditer(text):
        attrs = {}
        for key, dq, sq in ATTR_RE.findall(m.group(1)):
            attrs[key.lower()] = html.unescape(dq if dq else sq)
        items.append(attrs)
    return items


def _field_value(item: dict, field: str) -> str:
    if field == "any field":
        return " | ".join(item.get(f, "") for f in FIELDS)
    return item.get(field, "")


def build_matcher(filters, include_mode="all", case_sensitive=False, use_regex=False):
    """
    filters: list of {"field", "op", "text"}; rows with blank text are ignored.
    'contains' rows combine with ALL/ANY; any matching 'does not contain' row
    rejects the item. Returns item -> bool. Raises re.error on a bad regex.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    includes, excludes = [], []

    for flt in filters:
        text = flt.get("text", "")
        if not text.strip():
            continue
        field = flt.get("field", "message")
        # default args bind the CURRENT values; a plain closure would see only
        # the last loop iteration's text/field
        if use_regex:
            rx = re.compile(text, flags)
            test = lambda it, rx=rx, f=field: bool(rx.search(_field_value(it, f)))
        elif case_sensitive:
            test = lambda it, t=text, f=field: t in _field_value(it, f)
        else:
            t_low = text.lower()
            test = lambda it, t=t_low, f=field: t in _field_value(it, f).lower()
        (excludes if flt.get("op") == "does not contain" else includes).append(test)

    combine = all if include_mode == "all" else any

    def match(item):
        if any(t(item) for t in excludes):
            return False
        return combine(t(item) for t in includes) if includes else True

    return match


def write_csv(path: Path, rows) -> int:
    """Write rows as UTF-8 CSV with BOM (so Excel shows accents correctly)."""
    n = 0
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
            n += 1
    return n


# ====================================================================== CLI
def run_cli(args) -> int:
    src = Path(args.file)
    if not src.is_file():
        print(f"File not found: {src}", file=sys.stderr)
        return 2
    filters = ([{"field": args.field, "op": "contains", "text": t} for t in args.contains]
               + [{"field": args.field, "op": "does not contain", "text": t} for t in args.exclude])
    try:
        matcher = build_matcher(filters, "any" if args.any else "all", args.case, args.regex)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        return 2
    items = parse_items(read_text(src))
    matches = [it for it in items if matcher(it)]
    out = Path(args.out) if args.out else src.with_name(src.stem + "_filtered.csv")
    write_csv(out, matches)
    print(f"Read {len(items)} items, kept {len(matches)} -> {out}")
    return 0


# ====================================================================== GUI
# palette
NAVY = "#0F1B2D"
NAVY_2 = "#1C2B42"
ACCENT = "#F28C28"
ACCENT_DARK = "#D9771A"
BG = "#F3F5F8"
CARD = "#FFFFFF"
BORDER = "#DDE2E9"
TEXT = "#1F2937"
MUTED = "#6B7280"
HEAD_MUTED = "#9FB0C8"
STRIPE = "#F8FAFC"
SELECT = "#FDE7D1"
SEV_COLORS = {"error": "#B42318", "fatal": "#B42318", "critical": "#B42318",
              "warning": "#B54708", "audit": "#1D4ED8"}


def _pick_font():
    fams = set(tkfont.families())
    for f in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Arial"):
        if f in fams:
            return f
    return "TkDefaultFont"


def _apply_theme(root):
    fam = _pick_font()
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=fam, size=10)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, font=(fam, 10),
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                focuscolor=ACCENT)
    s.configure("Card.TFrame", background=CARD)
    s.configure("Card.TLabel", background=CARD, foreground=TEXT)
    s.configure("Section.TLabel", background=CARD, foreground=MUTED,
                font=(fam, 9, "bold"))
    s.configure("Count.TLabel", background=CARD, foreground=MUTED)
    s.configure("Card.TRadiobutton", background=CARD)
    s.configure("Card.TCheckbutton", background=CARD)
    s.map("Card.TRadiobutton", background=[("active", CARD)])
    s.map("Card.TCheckbutton", background=[("active", CARD)])

    s.configure("TButton", padding=(12, 5), background="#EEF1F5", relief="flat")
    s.map("TButton", background=[("active", "#E2E7EE"), ("disabled", "#F3F4F6")])
    s.configure("Primary.TButton", background=ACCENT, foreground="white",
                font=(fam, 10, "bold"), padding=(16, 6), bordercolor=ACCENT,
                lightcolor=ACCENT, darkcolor=ACCENT)
    s.map("Primary.TButton",
          background=[("disabled", "#E5C3A1"), ("active", ACCENT_DARK)],
          bordercolor=[("active", ACCENT_DARK)])
    s.configure("Link.TButton", background=CARD, foreground=ACCENT_DARK,
                padding=(6, 4), bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    s.map("Link.TButton", background=[("active", "#FFF4EA")])
    s.configure("Remove.TButton", background=CARD, foreground=MUTED, padding=(4, 2),
                bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    s.map("Remove.TButton", foreground=[("active", "#B42318")],
          background=[("active", "#FDECEC")])

    s.configure("TEntry", fieldbackground="white", padding=4)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    s.configure("TCombobox", fieldbackground="white", padding=3, arrowcolor=MUTED)
    s.map("TCombobox", fieldbackground=[("readonly", "white")],
          bordercolor=[("focus", ACCENT)])

    s.configure("Treeview", background=CARD, fieldbackground=CARD, rowheight=26,
                bordercolor=BORDER, font=(fam, 10))
    s.configure("Treeview.Heading", background="#EEF1F5", foreground=TEXT,
                font=(fam, 10, "bold"), relief="flat", padding=(6, 5))
    s.map("Treeview.Heading", background=[("active", "#E2E7EE")])
    s.map("Treeview", background=[("selected", SELECT)],
          foreground=[("selected", TEXT)])
    s.configure("Status.Horizontal.TProgressbar", background=ACCENT,
                troughcolor="#E5E7EB", bordercolor="#E5E7EB", thickness=6)
    return fam


def _make_icon(root):
    """32x32 window icon drawn in code: navy tile with an orange 'OT' bar."""
    img = tk.PhotoImage(width=32, height=32)
    img.put(NAVY, to=(0, 0, 32, 32))
    img.put(ACCENT, to=(6, 22, 26, 26))
    img.put("white", to=(6, 8, 14, 18))
    img.put(NAVY, to=(8, 10, 12, 16))
    img.put("white", to=(16, 8, 26, 11))
    img.put("white", to=(19, 8, 23, 18))
    return img


def card(parent, **pack):
    """White panel with a 1px border."""
    outer = tk.Frame(parent, bg=CARD, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=BORDER)
    outer.pack(**pack)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=(14, 10))
    inner.pack(fill="both", expand=True)
    return inner


class ScrollFrame:
    """Vertically scrollable area so any number of filter rows fit."""

    def __init__(self, parent, height=150):
        self.outer = ttk.Frame(parent, style="Card.TFrame")
        self.canvas = tk.Canvas(self.outer, height=height, highlightthickness=0, bg=CARD)
        vsb = ttk.Scrollbar(self.outer, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.outer.bind("<Enter>", lambda e: self._wheel(True))
        self.outer.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on):
        c = self.canvas
        if on:
            c.bind_all("<MouseWheel>",
                       lambda e: c.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            c.bind_all("<Button-4>", lambda e: c.yview_scroll(-1, "units"))
            c.bind_all("<Button-5>", lambda e: c.yview_scroll(1, "units"))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                c.unbind_all(seq)


class FilterRow:
    def __init__(self, parent, on_remove, on_apply, field="message", op="contains", text=""):
        self.frame = ttk.Frame(parent, style="Card.TFrame")
        self.field = tk.StringVar(value=field)
        self.op = tk.StringVar(value=op)
        self.text = tk.StringVar(value=text)

        ttk.Combobox(self.frame, textvariable=self.field, values=FIELD_CHOICES,
                     state="readonly", width=11).pack(side="left", padx=(0, 6))
        ttk.Combobox(self.frame, textvariable=self.op, values=OPS,
                     state="readonly", width=16).pack(side="left", padx=(0, 6))
        self.entry = ttk.Entry(self.frame, textvariable=self.text)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda e: on_apply())
        ttk.Button(self.frame, text="✕", style="Remove.TButton", width=3,
                   command=lambda: on_remove(self)).pack(side="left")
        self.frame.pack(fill="x", pady=3, padx=(0, 8))

    def get(self):
        return {"field": self.field.get(), "op": self.op.get(), "text": self.text.get()}


class App:
    def __init__(self, root, preload=None):
        self.root = root
        self.items = None
        self.matches = []
        self.src = None
        self.rows = []
        self.sort_col = None
        self.sort_rev = False
        self._q = queue.Queue()

        self.font = _apply_theme(root)
        root.title(f"{APP_NAME} · {BRAND}")
        root.geometry("1200x760")
        root.minsize(900, 560)
        root.configure(bg=BG)
        self._icon = _make_icon(root)
        root.iconphoto(True, self._icon)

        self._build_header()
        body = ttk.Frame(root, padding=(14, 12, 14, 0))
        body.pack(fill="both", expand=True)
        self._build_source(body)
        self._build_filters(body)
        self._build_results(body)
        self._build_statusbar()
        self._bind_keys()

        self.add_row(text="DataLog")
        self._update_empty_state()
        if preload:
            self.path_var.set(preload)
            self.load()

    # ------------------------------------------------------------- layout
    def _build_header(self):
        f = self.font
        bar = tk.Frame(self.root, bg=NAVY, height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        mark = tk.Frame(bar, bg=NAVY)
        mark.pack(side="left", padx=(18, 0))
        tk.Label(mark, text="Anything", bg=NAVY, fg="white",
                 font=(f, 17, "bold")).pack(side="left")
        tk.Label(mark, text="OT", bg=NAVY, fg=ACCENT,
                 font=(f, 17, "bold")).pack(side="left")

        tk.Frame(bar, bg=NAVY_2, width=1).pack(side="left", fill="y", padx=16, pady=14)

        title = tk.Frame(bar, bg=NAVY)
        title.pack(side="left")
        tk.Label(title, text=APP_NAME, bg=NAVY, fg="white",
                 font=(f, 13, "bold")).pack(anchor="w")
        tk.Label(title, text="FactoryTalk Diagnostics export filter", bg=NAVY,
                 fg=HEAD_MUTED, font=(f, 9)).pack(anchor="w")

        tk.Label(bar, text=f"v{APP_VERSION}", bg=NAVY, fg=HEAD_MUTED,
                 font=(f, 9)).pack(side="right", padx=18)

    def _build_source(self, body):
        c = card(body, fill="x")
        ttk.Label(c, text="SOURCE FILE", style="Section.TLabel").pack(anchor="w")
        row = ttk.Frame(c, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.path_var = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.path_var)
        e.pack(side="left", fill="x", expand=True, padx=(0, 8))
        e.bind("<Return>", lambda ev: self.load())
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="left", padx=(0, 6))
        self.load_btn = ttk.Button(row, text="Load", style="Primary.TButton",
                                   command=self.load)
        self.load_btn.pack(side="left")

    def _build_filters(self, body):
        c = card(body, fill="x", pady=(10, 0))
        head = ttk.Frame(c, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="FILTERS", style="Section.TLabel").pack(side="left")
        ttk.Button(head, text="Load preset…", style="Link.TButton",
                   command=self.load_preset).pack(side="right")
        ttk.Button(head, text="Save preset…", style="Link.TButton",
                   command=self.save_preset).pack(side="right")

        self.scroll = ScrollFrame(c)
        self.scroll.outer.pack(fill="x", pady=(6, 4))

        ttk.Separator(c).pack(fill="x", pady=(4, 8))
        opts = ttk.Frame(c, style="Card.TFrame")
        opts.pack(fill="x")
        ttk.Button(opts, text="+  Add filter", command=self.add_row).pack(side="left")
        ttk.Button(opts, text="Reset", command=self.clear_rows).pack(side="left", padx=6)

        ttk.Label(opts, text="Contains rules must match", style="Card.TLabel").pack(
            side="left", padx=(18, 6))
        self.mode = tk.StringVar(value="all")
        ttk.Radiobutton(opts, text="All", value="all", variable=self.mode,
                        style="Card.TRadiobutton").pack(side="left")
        ttk.Radiobutton(opts, text="Any", value="any", variable=self.mode,
                        style="Card.TRadiobutton").pack(side="left", padx=(4, 0))

        self.case = tk.BooleanVar(value=False)
        self.regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Case sensitive", variable=self.case,
                        style="Card.TCheckbutton").pack(side="left", padx=(18, 0))
        ttk.Checkbutton(opts, text="Regex", variable=self.regex,
                        style="Card.TCheckbutton").pack(side="left", padx=(8, 0))

        ttk.Button(opts, text="Apply filters", style="Primary.TButton",
                   command=self.apply).pack(side="right")

    def _build_results(self, body):
        c = card(body, fill="both", expand=True, pady=(10, 12))
        head = ttk.Frame(c, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="RESULTS", style="Section.TLabel").pack(side="left")
        self.export_btn = ttk.Button(head, text="Export CSV…", style="Primary.TButton",
                                     command=self.export)
        self.export_btn.pack(side="right")
        self.count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.count_var, style="Count.TLabel").pack(
            side="right", padx=12)

        grid = ttk.Frame(c, style="Card.TFrame")
        grid.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(grid, columns=FIELDS, show="headings", selectmode="extended")
        widths = {"datetime": 155, "location": 120, "provider": 120,
                  "severity": 85, "message": 520, "username": 110}
        for col in FIELDS:
            self.tree.heading(col, text=col.capitalize(), anchor="w",
                              command=lambda c_=col: self.sort_by(c_))
            self.tree.column(col, width=widths[col], anchor="w", stretch=(col == "message"))
        self.tree.tag_configure("odd", background=STRIPE)
        for sev, color in SEV_COLORS.items():
            self.tree.tag_configure(sev, foreground=color)

        vsb = ttk.Scrollbar(grid, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(grid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)

        self.empty = tk.Label(grid, bg=CARD, fg=MUTED, font=(self.font, 11), justify="center")

        self.tree.bind("<Double-1>", self.show_detail)
        self.tree.bind("<Button-3>", self._context_menu)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Copy selected rows", command=self.copy_rows)
        self.menu.add_command(label="Show details", command=lambda: self.show_detail(None))

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg="#E9EDF2", height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self.status, bg="#E9EDF2", fg=TEXT,
                 font=(self.font, 9)).pack(side="left", padx=12)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140,
                                        style="Status.Horizontal.TProgressbar")
        tk.Label(bar, text=f"© {BRAND}  ·  {APP_NAME} v{APP_VERSION}", bg="#E9EDF2",
                 fg=MUTED, font=(self.font, 9)).pack(side="right", padx=12)

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.browse())
        r.bind("<Control-e>", lambda e: self.export())
        r.bind("<Control-n>", lambda e: self.add_row())
        r.bind("<F5>", lambda e: self.apply())
        self.tree.bind("<Control-c>", lambda e: self.copy_rows())

    # ------------------------------------------------------------- filters
    def add_row(self, field="message", op="contains", text=""):
        row = FilterRow(self.scroll.inner, self.remove_row, self.apply, field, op, text)
        self.rows.append(row)
        row.entry.focus_set()
        self.root.after(10, lambda: self.scroll.canvas.yview_moveto(1.0))

    def remove_row(self, row):
        row.frame.destroy()
        self.rows.remove(row)
        if not self.rows:
            self.add_row()

    def clear_rows(self):
        for r in list(self.rows):
            r.frame.destroy()
        self.rows.clear()
        self.add_row()

    # ------------------------------------------------------------- loading
    def browse(self):
        p = filedialog.askopenfilename(
            title="Select FactoryTalk Diagnostics export",
            filetypes=[("XML export", "*.xml"), ("All files", "*.*")])
        if p:
            self.path_var.set(p)
            self.load()

    def load(self):
        p = Path(self.path_var.get().strip().strip('"'))
        if not p.is_file():
            messagebox.showerror(APP_NAME, f"File not found:\n{p}")
            return
        self.load_btn.state(["disabled"])
        self.status.set(f"Reading {p.name}…")
        self.progress.pack(side="left", padx=8)
        self.progress.start(12)

        def work():
            try:
                self._q.put(("ok", p, parse_items(read_text(p))))
            except Exception as e:  # surface any read/parse error in the UI
                self._q.put(("err", p, e))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(100, self._poll)

    def _poll(self):
        try:
            kind, p, payload = self._q.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll)
            return
        self.progress.stop()
        self.progress.pack_forget()
        self.load_btn.state(["!disabled"])
        if kind == "err":
            self.status.set("Load failed")
            messagebox.showerror(APP_NAME, f"Could not read the file:\n{payload}")
            return
        self.src, self.items = p, payload
        self.sort_col = None
        if not payload:
            messagebox.showwarning(APP_NAME, "No <Item> elements were found in this file.")
        self.apply()

    # ------------------------------------------------------------- results
    def apply(self):
        if self.items is None:
            self.status.set("Load an export first (Ctrl+O)")
            return
        try:
            matcher = build_matcher([r.get() for r in self.rows], self.mode.get(),
                                    self.case.get(), self.regex.get())
        except re.error as e:
            messagebox.showerror(APP_NAME, f"Invalid regular expression:\n{e}")
            return
        self.matches = [it for it in self.items if matcher(it)]
        if self.sort_col:
            self._sort_matches()
        self._refresh_tree()
        self.status.set(f"Loaded {self.src.name}")

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, False
        self._sort_matches()
        self._refresh_tree()

    def _sort_matches(self):
        c = self.sort_col
        self.matches.sort(key=lambda it: it.get(c, "").lower(), reverse=self.sort_rev)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(self.matches[:PREVIEW_LIMIT]):
            tags = ["odd"] if i % 2 else []
            sev = it.get("severity", "").lower()
            if sev in SEV_COLORS:
                tags.append(sev)
            self.tree.insert("", "end", values=[it.get(f, "") for f in FIELDS], tags=tags)

        for col in FIELDS:
            arrow = (" ▼" if self.sort_rev else " ▲") if col == self.sort_col else ""
            self.tree.heading(col, text=col.capitalize() + arrow)

        total, n = len(self.items or []), len(self.matches)
        cap = f"  (showing first {PREVIEW_LIMIT:,})" if n > PREVIEW_LIMIT else ""
        self.count_var.set(f"{n:,} of {total:,} items{cap}")
        self._update_empty_state()

    def _update_empty_state(self):
        if self.items is None:
            msg = "Open a FactoryTalk Diagnostics XML export to begin\n\nBrowse…  or  Ctrl+O"
        elif not self.matches:
            msg = "No items match the current filters"
        else:
            self.empty.place_forget()
            self.export_btn.state(["!disabled"])
            return
        self.export_btn.state(["disabled"])
        self.empty.configure(text=msg)
        self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _selected_values(self):
        return [self.tree.item(i, "values") for i in self.tree.selection()]

    def copy_rows(self):
        rows = self._selected_values()
        if not rows:
            return
        text = "\n".join("\t".join(r) for r in [FIELDS] + rows)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set(f"Copied {len(rows)} row(s) - paste straight into Excel")

    def _context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        if self.tree.selection():
            self.menu.tk_popup(event.x_root, event.y_root)

    def show_detail(self, _event):
        rows = self._selected_values()
        if not rows:
            return
        win = tk.Toplevel(self.root)
        win.title("Item detail")
        win.configure(bg=CARD)
        win.transient(self.root)
        txt = tk.Text(win, wrap="word", width=90, height=12, relief="flat",
                      bg=CARD, fg=TEXT, font=(self.font, 10), padx=14, pady=12)
        txt.pack(fill="both", expand=True)
        txt.tag_configure("k", foreground=MUTED, font=(self.font, 10, "bold"))
        for f, v in zip(FIELDS, rows[0]):
            txt.insert("end", f"{f.capitalize():<10}", "k")
            txt.insert("end", f"  {v}\n")
        txt.configure(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 12))

    # ------------------------------------------------------- export/presets
    def export(self):
        if not self.matches:
            return
        default = (self.src.stem + "_filtered.csv") if self.src else "filtered.csv"
        p = filedialog.asksaveasfilename(
            title="Export matching rows", defaultextension=".csv", initialfile=default,
            initialdir=str(self.src.parent) if self.src else None,
            filetypes=[("CSV (Excel)", "*.csv")])
        if not p:
            return
        try:
            n = write_csv(Path(p), self.matches)
        except PermissionError:
            messagebox.showerror(APP_NAME, "The file is in use. Close it in Excel and try again.")
            return
        self.status.set(f"Exported {n:,} rows → {p}")

    def save_preset(self):
        p = filedialog.asksaveasfilename(title="Save filter preset", defaultextension=".json",
                                         filetypes=[("Filter preset", "*.json")])
        if not p:
            return
        data = {"app": APP_NAME, "version": APP_VERSION, "mode": self.mode.get(),
                "case_sensitive": self.case.get(), "regex": self.regex.get(),
                "filters": [r.get() for r in self.rows]}
        Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.status.set(f"Preset saved → {p}")

    def load_preset(self):
        p = filedialog.askopenfilename(title="Load filter preset",
                                       filetypes=[("Filter preset", "*.json")])
        if not p:
            return
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            messagebox.showerror(APP_NAME, f"Could not read preset:\n{e}")
            return
        for r in list(self.rows):
            r.frame.destroy()
        self.rows.clear()
        for f in data.get("filters") or [{}]:
            self.add_row(f.get("field", "message"), f.get("op", "contains"), f.get("text", ""))
        self.mode.set(data.get("mode", "all"))
        self.case.set(bool(data.get("case_sensitive", False)))
        self.regex.set(bool(data.get("regex", False)))
        self.status.set(f"Preset loaded ← {Path(p).name}")
        self.apply()


# ===================================================================== main
def _parser():
    p = argparse.ArgumentParser(
        prog="ftv_diagnostics_filter",
        description=f"{APP_NAME} v{APP_VERSION} ({BRAND}). "
                    "With no --contains/--exclude options the GUI opens.")
    p.add_argument("file", nargs="?", help="FactoryTalk Diagnostics XML export")
    p.add_argument("-c", "--contains", action="append", default=[], metavar="TEXT",
                   help="keep rows containing TEXT (repeatable)")
    p.add_argument("-x", "--exclude", action="append", default=[], metavar="TEXT",
                   help="drop rows containing TEXT (repeatable)")
    p.add_argument("--field", default="message", choices=FIELD_CHOICES,
                   help="field the CLI rules apply to (default: message)")
    p.add_argument("--any", action="store_true", help="keep rows matching ANY --contains")
    p.add_argument("--case", action="store_true", help="case-sensitive matching")
    p.add_argument("--regex", action="store_true", help="treat TEXT as regular expressions")
    p.add_argument("-o", "--out", help="output CSV (default: <file>_filtered.csv)")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.contains or args.exclude:
        if not args.file:
            _parser().error("a file is required with --contains/--exclude")
        return run_cli(args)
    if tk is None:
        print("tkinter is not available; use --contains/--exclude for CLI mode.",
              file=sys.stderr)
        return 1
    root = tk.Tk()
    App(root, preload=args.file)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
