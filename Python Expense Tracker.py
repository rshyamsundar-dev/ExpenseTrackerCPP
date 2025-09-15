"""
Expense Tracker – Tkinter/ttkbootstrap GUI (single-file app)
-----------------------------------------------------------
• Features: add, view, filter (date/category/keyword), edit, delete, CSV import/export,
  category management, per‑category and overall summaries, persistent SQLite storage.
• Beautiful UI: uses ttkbootstrap if available; otherwise falls back to standard ttk.
• Python stdlib only + optional ttkbootstrap. No other dependencies.

Run:  python expense_tracker.py

"""
from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

# ---------------------------
# Theming (ttkbootstrap optional)
# ---------------------------
USE_TTKBOOTSTRAP = False
try:
    import ttkbootstrap as tb  # type: ignore
    from ttkbootstrap.constants import *  # type: ignore
    from ttkbootstrap.dialogs import Querybox, Messagebox  # type: ignore
    USE_TTKBOOTSTRAP = True
except Exception:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog

    # Minimal shims to keep code unified when ttkbootstrap is missing
    class Messagebox:
        @staticmethod
        def show_info(message: str, title: str = "Info"):
            messagebox.showinfo(title, message)

        @staticmethod
        def show_error(message: str, title: str = "Error"):
            messagebox.showerror(title, message)

        @staticmethod
        def ask_yesno(message: str, title: str = "Confirm") -> bool:
            return messagebox.askyesno(title, message)

    class Querybox:
        @staticmethod
        def get_string(prompt: str, title: str = "Input", initialvalue: str = "") -> Optional[str]:
            return simpledialog.askstring(title, prompt, initialvalue=initialvalue)

# ---------------------------
# Data model
# ---------------------------
DB_FILE = os.path.join(os.path.expanduser("~"), ".expense_tracker.sqlite3")

@dataclass
class Expense:
    id: Optional[int]
    tx_date: date
    amount: float
    category: str
    description: str

# ---------------------------
# Storage layer (SQLite)
# ---------------------------
class Store:
    def __init__(self, db_path: str = DB_FILE):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(category) REFERENCES categories(name) ON UPDATE CASCADE ON DELETE RESTRICT
            );
            """
        )
        # Seed default categories if new DB
        cur.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO categories(name) VALUES (?)", [
                ("Food",), ("Transport",), ("Utilities",), ("Rent",), ("Entertainment",),
                ("Health",), ("Education",), ("Shopping",), ("Other",)
            ])
        self.conn.commit()

    # Category ops
    def get_categories(self) -> List[str]:
        cur = self.conn.execute("SELECT name FROM categories ORDER BY name")
        return [r[0] for r in cur.fetchall()]

    def add_category(self, name: str):
        self.conn.execute("INSERT OR IGNORE INTO categories(name) VALUES (?)", (name,))
        self.conn.commit()

    def rename_category(self, old: str, new: str):
        self.conn.execute("UPDATE categories SET name=? WHERE name=?", (new, old))
        self.conn.commit()

    def delete_category(self, name: str) -> bool:
        # Prevent deletion if any expense uses it
        cur = self.conn.execute("SELECT COUNT(*) FROM expenses WHERE category=?", (name,))
        if cur.fetchone()[0] > 0:
            return False
        self.conn.execute("DELETE FROM categories WHERE name=?", (name,))
        self.conn.commit()
        return True

    # Expense ops
    def add_expense(self, e: Expense) -> int:
        cur = self.conn.execute(
            "INSERT INTO expenses(tx_date, amount, category, description) VALUES (?, ?, ?, ?)",
            (e.tx_date.isoformat(), e.amount, e.category, e.description),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_expense(self, e: Expense):
        assert e.id is not None
        self.conn.execute(
            "UPDATE expenses SET tx_date=?, amount=?, category=?, description=? WHERE id=?",
            (e.tx_date.isoformat(), e.amount, e.category, e.description, e.id),
        )
        self.conn.commit()

    def delete_expense(self, expense_id: int):
        self.conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        self.conn.commit()

    def list_expenses(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
        category: Optional[str] = None,
        keyword: str = "",
    ) -> List[Expense]:
        sql = "SELECT id, tx_date, amount, category, description FROM expenses WHERE 1=1"
        params: List[object] = []
        if start:
            sql += " AND date(tx_date) >= date(?)"
            params.append(start.isoformat())
        if end:
            sql += " AND date(tx_date) <= date(?)"
            params.append(end.isoformat())
        if category and category != "All":
            sql += " AND category=?"
            params.append(category)
        if keyword:
            sql += " AND LOWER(description) LIKE ?"
            params.append(f"%{keyword.lower()}%")
        sql += " ORDER BY date(tx_date) DESC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        out: List[Expense] = []
        for r in rows:
            out.append(
                Expense(
                    id=r[0],
                    tx_date=datetime.fromisoformat(r[1]).date(),
                    amount=float(r[2]),
                    category=r[3],
                    description=r[4],
                )
            )
        return out

    def summarize_by_category(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> List[Tuple[str, float]]:
        sql = "SELECT category, SUM(amount) FROM expenses WHERE 1=1"
        params: List[object] = []
        if start:
            sql += " AND date(tx_date) >= date(?)"
            params.append(start.isoformat())
        if end:
            sql += " AND date(tx_date) <= date(?)"
            params.append(end.isoformat())
        sql += " GROUP BY category ORDER BY SUM(amount) DESC"
        return [(row[0], float(row[1] or 0)) for row in self.conn.execute(sql, params).fetchall()]

    def total(self, start: Optional[date] = None, end: Optional[date] = None) -> float:
        sql = "SELECT SUM(amount) FROM expenses WHERE 1=1"
        params: List[object] = []
        if start:
            sql += " AND date(tx_date) >= date(?)"
            params.append(start.isoformat())
        if end:
            sql += " AND date(tx_date) <= date(?)"
            params.append(end.isoformat())
        val = self.conn.execute(sql, params).fetchone()[0]
        return float(val or 0.0)

# ---------------------------
# GUI widgets
# ---------------------------
if USE_TTKBOOTSTRAP:
    tk = tb
    from tkinter import StringVar, DoubleVar
else:
    import tkinter as tk
    from tkinter import ttk
    from tkinter import StringVar, DoubleVar

class ExpenseApp:
    def __init__(self, root: "tk.Window"):
        self.root = root
        self.store = Store()
        self.root.title("Expense Tracker")
        self.root.geometry("980x640")
        if USE_TTKBOOTSTRAP:
            self.style = tb.Style(theme="flatly")
        else:
            self.style = ttk.Style()
            if "vista" in self.style.theme_names():
                self.style.theme_use("vista")
        self._build_ui()
        self.refresh_tables()

    def _build_ui(self):
        nb = (tb.Notebook(self.root) if USE_TTKBOOTSTRAP else ttk.Notebook(self.root))
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.page_add = tk.Frame(nb)
        self.page_browse = tk.Frame(nb)
        self.page_summary = tk.Frame(nb)
        nb.add(self.page_add, text="Add / Edit")
        nb.add(self.page_browse, text="Browse & Filter")
        nb.add(self.page_summary, text="Summary")

        self._build_add_page()
        self._build_browse_page()
        self._build_summary_page()

    # ---------- Add/Edit Page ----------
    def _build_add_page(self):
        frm = tk.Frame(self.page_add)
        frm.pack(fill="x", padx=16, pady=16)

        # Inputs
        self.var_date = StringVar(value=date.today().isoformat())
        self.var_amount = DoubleVar(value=0.00)
        self.var_category = StringVar()
        self.var_desc = StringVar()
        self.editing_id: Optional[int] = None

        def row(r: int, text: str, widget):
            lab = (tb.Label(frm, text=text) if USE_TTKBOOTSTRAP else ttk.Label(frm, text=text))
            lab.grid(row=r, column=0, sticky="w", padx=(0, 12), pady=8)
            widget.grid(row=r, column=1, sticky="ew", pady=8)

        e_date = (tb.Entry(frm, textvariable=self.var_date, width=16) if USE_TTKBOOTSTRAP
                  else ttk.Entry(frm, textvariable=self.var_date, width=16))
        row(0, "Date (YYYY-MM-DD)", e_date)

        e_amt = (tb.Entry(frm, textvariable=self.var_amount) if USE_TTKBOOTSTRAP
                 else ttk.Entry(frm, textvariable=self.var_amount))
        row(1, "Amount", e_amt)

        self.cb_cat = (tb.Combobox(frm, textvariable=self.var_category, values=self._cat_values())
                       if USE_TTKBOOTSTRAP else ttk.Combobox(frm, textvariable=self.var_category, values=self._cat_values()))
        row(2, "Category", self.cb_cat)

        e_desc = (tb.Entry(frm, textvariable=self.var_desc)
                  if USE_TTKBOOTSTRAP else ttk.Entry(frm, textvariable=self.var_desc))
        row(3, "Description", e_desc)

        frm.columnconfigure(1, weight=1)

        # Buttons
        btns = tk.Frame(self.page_add)
        btns.pack(fill="x", padx=16)
        add_btn = (tb.Button(btns, text="Save Expense", bootstyle=SUCCESS, command=self.save_expense)
                   if USE_TTKBOOTSTRAP else ttk.Button(btns, text="Save Expense", command=self.save_expense))
        clear_btn = (tb.Button(btns, text="Clear", command=self.clear_form)
                     if USE_TTKBOOTSTRAP else ttk.Button(btns, text="Clear", command=self.clear_form))
        manage_btn = (tb.Button(btns, text="Manage Categories", bootstyle=INFO, command=self.manage_categories)
                      if USE_TTKBOOTSTRAP else ttk.Button(btns, text="Manage Categories", command=self.manage_categories))
        add_btn.pack(side="left")
        clear_btn.pack(side="left", padx=8)
        manage_btn.pack(side="left")

    def _cat_values(self) -> List[str]:
        return sorted(self.store.get_categories())

    def clear_form(self):
        self.editing_id = None
        self.var_date.set(date.today().isoformat())
        self.var_amount.set(0.00)
        self.var_category.set("")
        self.var_desc.set("")

    def save_expense(self):
        try:
            txd = datetime.fromisoformat(self.var_date.get()).date()
        except ValueError:
            Messagebox.show_error("Date must be in YYYY-MM-DD format.")
            return
        try:
            amt = float(self.var_amount.get())
            if amt < 0:
                raise ValueError
        except Exception:
            Messagebox.show_error("Amount must be a non-negative number.")
            return
        cat = self.var_category.get().strip() or "Other"
        desc = self.var_desc.get().strip()
        e = Expense(self.editing_id, txd, amt, cat, desc)
        if self.editing_id:
            self.store.update_expense(e)
            Messagebox.show_info("Expense updated successfully.")
        else:
            new_id = self.store.add_expense(e)
            self.editing_id = new_id
            Messagebox.show_info("Expense added successfully.")
        self.cb_cat.configure(values=self._cat_values())
        self.refresh_tables()

    def manage_categories(self):
        action = Querybox.get_string("Type: add <name>, rename <old> -> <new>, or delete <name>\nExamples: \nadd Travel\nrename Shopping -> Retail\ndelete Other", title="Manage Categories")
        if not action:
            return
        try:
            s = action.strip()
            if s.lower().startswith("add "):
                name = s[4:].strip()
                if name:
                    self.store.add_category(name)
            elif s.lower().startswith("rename ") and "->" in s:
                left, right = s[7:].split("->", 1)
                old, new = left.strip(), right.strip()
                if old and new:
                    self.store.rename_category(old, new)
            elif s.lower().startswith("delete "):
                name = s[7:].strip()
                if name:
                    if not self.store.delete_category(name):
                        Messagebox.show_error("Cannot delete a category that has expenses.")
            else:
                Messagebox.show_error("Unrecognized command.")
        except Exception as ex:
            Messagebox.show_error(f"Category action failed: {ex}")
        self.cb_cat.configure(values=self._cat_values())
        self.refresh_tables()

    # ---------- Browse Page ----------
    def _build_browse_page(self):
        filt = tk.Frame(self.page_browse)
        filt.pack(fill="x", padx=12, pady=8)

        self.var_start = StringVar()
        self.var_end = StringVar()
        self.var_fcat = StringVar(value="All")
        self.var_kw = StringVar()

        def lab(text):
            return tb.Label(filt, text=text) if USE_TTKBOOTSTRAP else ttk.Label(filt, text=text)

        def ent(var, w=14):
            return tb.Entry(filt, textvariable=var, width=w) if USE_TTKBOOTSTRAP else ttk.Entry(filt, textvariable=var, width=w)

        def combo(var, vals):
            return tb.Combobox(filt, textvariable=var, values=vals, width=18) if USE_TTKBOOTSTRAP else ttk.Combobox(filt, textvariable=var, values=vals, width=18)

        lab("Start (YYYY-MM-DD)").pack(side="left")
        ent(self.var_start).pack(side="left", padx=(6, 12))
        lab("End").pack(side="left")
        ent(self.var_end).pack(side="left", padx=(6, 12))
        lab("Category").pack(side="left")
        self.cb_fcat = combo(self.var_fcat, ["All"] + self._cat_values())
        self.cb_fcat.pack(side="left", padx=(6, 12))
        lab("Keyword").pack(side="left")
        ent(self.var_kw, 18).pack(side="left", padx=(6, 12))

        btn_apply = (tb.Button(filt, text="Apply Filters", bootstyle=PRIMARY, command=self.apply_filters)
                     if USE_TTKBOOTSTRAP else ttk.Button(filt, text="Apply Filters", command=self.apply_filters))
        btn_clear = (tb.Button(filt, text="Reset", command=self.reset_filters)
                     if USE_TTKBOOTSTRAP else ttk.Button(filt, text="Reset", command=self.reset_filters))
        btn_export = (tb.Button(filt, text="Export CSV", bootstyle=SECONDARY, command=self.export_csv)
                      if USE_TTKBOOTSTRAP else ttk.Button(filt, text="Export CSV", command=self.export_csv))
        btn_import = (tb.Button(filt, text="Import CSV", command=self.import_csv)
                      if USE_TTKBOOTSTRAP else ttk.Button(filt, text="Import CSV", command=self.import_csv))
        btn_apply.pack(side="left", padx=4)
        btn_clear.pack(side="left", padx=4)
        btn_export.pack(side="left", padx=12)
        btn_import.pack(side="left", padx=4)

        # Table
        table_frame = tk.Frame(self.page_browse)
        table_frame.pack(fill="both", expand=True, padx=12, pady=8)
        columns = ("id", "date", "amount", "category", "description")
        self.tv = (tb.Treeview(table_frame, columns=columns, show="headings", height=16)
                   if USE_TTKBOOTSTRAP else ttk.Treeview(table_frame, columns=columns, show="headings", height=16))
        for col, w in zip(columns, (60, 120, 120, 160, 480)):
            self.tv.heading(col, text=col.title())
            self.tv.column(col, width=w, anchor="w")
        self.tv.pack(fill="both", expand=True, side="left")

        vsb = (tb.Scrollbar(table_frame, orient="vertical", command=self.tv.yview)
               if USE_TTKBOOTSTRAP else ttk.Scrollbar(table_frame, orient="vertical", command=self.tv.yview))
        self.tv.configure(yscroll=vsb.set)
        vsb.pack(side="right", fill="y")

        # Row actions
        act = tk.Frame(self.page_browse)
        act.pack(fill="x", padx=12, pady=8)
        btn_edit = (tb.Button(act, text="Edit Selected", bootstyle=INFO, command=self.edit_selected)
                    if USE_TTKBOOTSTRAP else ttk.Button(act, text="Edit Selected", command=self.edit_selected))
        btn_delete = (tb.Button(act, text="Delete Selected", bootstyle=DANGER, command=self.delete_selected)
                      if USE_TTKBOOTSTRAP else ttk.Button(act, text="Delete Selected", command=self.delete_selected))
        btn_edit.pack(side="left")
        btn_delete.pack(side="left", padx=8)

        # Total bar
        self.var_total = StringVar(value="Total: $0.00")
        total_bar = (tb.Label(self.page_browse, textvariable=self.var_total, anchor="e")
                     if USE_TTKBOOTSTRAP else ttk.Label(self.page_browse, textvariable=self.var_total, anchor="e") )
        total_bar.pack(fill="x", padx=12, pady=(0, 12))

    def reset_filters(self):
        self.var_start.set("")
        self.var_end.set("")
        self.var_fcat.set("All")
        self.var_kw.set("")
        self.apply_filters()

    def _parse_date(self, s: str) -> Optional[date]:
        s = s.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            Messagebox.show_error("Dates must be in YYYY-MM-DD format.")
            return None

    def apply_filters(self):
        start = self._parse_date(self.var_start.get())
        if start is None and self.var_start.get().strip():
            return
        end = self._parse_date(self.var_end.get())
        if end is None and self.var_end.get().strip():
            return
        items = self.store.list_expenses(start, end, self.var_fcat.get(), self.var_kw.get())
        self._populate_table(items)
        self.var_total.set(f"Total: ${self.store.total(start, end):,.2f}")
        self.refresh_summary()

    def _populate_table(self, items: List[Expense]):
        for r in self.tv.get_children():
            self.tv.delete(r)
        for e in items:
            self.tv.insert("", "end", values=(e.id, e.tx_date.isoformat(), f"${e.amount:,.2f}", e.category, e.description))

    def edit_selected(self):
        sel = self.tv.selection()
        if not sel:
            Messagebox.show_error("Please select a row to edit.")
            return
        vals = self.tv.item(sel[0], "values")
        expense_id = int(vals[0])
        # fetch exact row from DB to avoid formatting issues
        rows = self.store.list_expenses()
        row = next((x for x in rows if x.id == expense_id), None)
        if not row:
            Messagebox.show_error("Could not locate expense in database.")
            return
        self.var_date.set(row.tx_date.isoformat())
        self.var_amount.set(row.amount)
        self.var_category.set(row.category)
        self.var_desc.set(row.description)
        self.editing_id = row.id
        Messagebox.show_info("Loaded into the Add/Edit form. Switch to the 'Add / Edit' tab to save changes.")

    def delete_selected(self):
        sel = self.tv.selection()
        if not sel:
            Messagebox.show_error("Please select a row to delete.")
            return
        vals = self.tv.item(sel[0], "values")
        expense_id = int(vals[0])
        if Messagebox.ask_yesno("Are you sure you want to delete the selected expense?", title="Confirm"):
            self.store.delete_expense(expense_id)
            self.apply_filters()

    def export_csv(self):
        # Simple export to a CSV file next to the DB
        out_path = os.path.join(os.path.dirname(DB_FILE), "expenses_export.csv")
        items = self.store.list_expenses(
            self._parse_date(self.var_start.get()),
            self._parse_date(self.var_end.get()),
            self.var_fcat.get(),
            self.var_kw.get(),
        )
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "date", "amount", "category", "description"])
            for e in items:
                w.writerow([e.id or "", e.tx_date.isoformat(), f"{e.amount:.2f}", e.category, e.description])
        Messagebox.show_info(f"Exported {len(items)} rows to\n{out_path}")

    def import_csv(self):
        # Import from a CSV file next to the DB
        in_path = os.path.join(os.path.dirname(DB_FILE), "expenses_import.csv")
        if not os.path.exists(in_path):
            Messagebox.show_error(f"Place a file named 'expenses_import.csv' at\n{in_path}\nwith headers: date,amount,category,description")
            return
        added = 0
        with open(in_path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    txd = datetime.fromisoformat(row["date"].strip()).date()
                    amt = float(row["amount"])  # may raise
                    cat = row.get("category", "Other").strip() or "Other"
                    desc = row.get("description", "").strip()
                    self.store.add_category(cat)
                    self.store.add_expense(Expense(None, txd, amt, cat, desc))
                    added += 1
                except Exception:
                    continue
        self.cb_cat.configure(values=self._cat_values())
        self.apply_filters()
        Messagebox.show_info(f"Imported {added} expenses from CSV.")

    # ---------- Summary Page ----------
    def _build_summary_page(self):
        filt = tk.Frame(self.page_summary)
        filt.pack(fill="x", padx=12, pady=8)
        self.var_sstart = StringVar()
        self.var_send = StringVar()
        (tb.Label(filt, text="Start (YYYY-MM-DD)") if USE_TTKBOOTSTRAP else ttk.Label(filt, text="Start (YYYY-MM-DD)")).pack(side="left")
        (tb.Entry(filt, textvariable=self.var_sstart, width=16) if USE_TTKBOOTSTRAP else ttk.Entry(filt, textvariable=self.var_sstart, width=16)).pack(side="left", padx=8)
        (tb.Label(filt, text="End") if USE_TTKBOOTSTRAP else ttk.Label(filt, text="End")).pack(side="left")
        (tb.Entry(filt, textvariable=self.var_send, width=16) if USE_TTKBOOTSTRAP else ttk.Entry(filt, textvariable=self.var_send, width=16)).pack(side="left", padx=8)
        (tb.Button(filt, text="Refresh", bootstyle=PRIMARY, command=self.refresh_summary) if USE_TTKBOOTSTRAP else ttk.Button(filt, text="Refresh", command=self.refresh_summary)).pack(side="left", padx=8)

        table_frame = tk.Frame(self.page_summary)
        table_frame.pack(fill="both", expand=True, padx=12, pady=8)
        cols = ("Category", "Total")
        self.tv_sum = (tb.Treeview(table_frame, columns=cols, show="headings", height=14)
                       if USE_TTKBOOTSTRAP else ttk.Treeview(table_frame, columns=cols, show="headings", height=14))
        for c, w in zip(cols, (400, 200)):
            self.tv_sum.heading(c, text=c)
            self.tv_sum.column(c, width=w, anchor="w")
        self.tv_sum.pack(fill="both", expand=True, side="left")
        vsb = (tb.Scrollbar(table_frame, orient="vertical", command=self.tv_sum.yview)
               if USE_TTKBOOTSTRAP else ttk.Scrollbar(table_frame, orient="vertical", command=self.tv_sum.yview))
        self.tv_sum.configure(yscroll=vsb.set)
        vsb.pack(side="right", fill="y")

        self.var_sum_total = StringVar(value="Overall Total: $0.00")
        (tb.Label(self.page_summary, textvariable=self.var_sum_total, anchor="e") if USE_TTKBOOTSTRAP else ttk.Label(self.page_summary, textvariable=self.var_sum_total, anchor="e")).pack(fill="x", padx=12, pady=(0, 12))

    def refresh_summary(self):
        st = self._parse_date(self.var_sstart.get() or self.var_start.get())
        en = self._parse_date(self.var_send.get() or self.var_end.get())
        rows = self.store.summarize_by_category(st, en)
        for r in self.tv_sum.get_children():
            self.tv_sum.delete(r)
        for cat, total in rows:
            self.tv_sum.insert("", "end", values=(cat, f"${total:,.2f}"))
        overall = self.store.total(st, en)
        self.var_sum_total.set(f"Overall Total: ${overall:,.2f}")

    # ---------- Utilities ----------
    def refresh_tables(self):
        self.cb_fcat.configure(values=["All"] + self._cat_values())
        self.apply_filters()


def main():
    if USE_TTKBOOTSTRAP:
        root = tb.Window(themename="flatly")
    else:
        root = tk.Tk()
    app = ExpenseApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

