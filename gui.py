#!/usr/bin/env python3
"""DeckShrink desktop shell (tkinter).
Pick Office files -> slimmed copies + re-check report."""
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck_shrink import run_deckshrink


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DeckShrink — Slim PowerPoint, Word & Excel Files, Re-Checked")
        self.geometry("700x580")
        self.paths = []
        self.maxdim = tk.StringVar(value="1920")
        self.quality = tk.StringVar(value="80")
        self.strip = tk.BooleanVar(value=True)
        tk.Label(self, text="PowerPoint / Word / Excel files (.pptx .docx .xlsx):").pack(anchor="w", padx=12, pady=(12, 2))
        row = tk.Frame(self)
        row.pack(fill="x", padx=12)
        tk.Button(row, text="Add files…", command=self.pick_files).pack(side="left")
        tk.Button(row, text="Add folder…", command=self.pick_folder).pack(side="left", padx=6)
        tk.Button(row, text="Clear", command=self.clear).pack(side="left")
        self.count_lbl = tk.Label(self, text="0 files selected")
        self.count_lbl.pack(anchor="w", padx=12, pady=(4, 0))
        tk.Label(self, text="Max picture dimension (px, longest side):").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Combobox(self, textvariable=self.maxdim, values=["1280", "1600", "1920", "2560"],
                     state="readonly").pack(fill="x", padx=12)
        tk.Label(self, text="JPEG quality:").pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Combobox(self, textvariable=self.quality, values=["70", "80", "85", "90"],
                     state="readonly").pack(fill="x", padx=12)
        tk.Checkbutton(self, text="Remove the package thumbnail (docProps/thumbnail.jpeg)",
                       variable=self.strip).pack(anchor="w", padx=12, pady=(6, 0))
        self.btn = tk.Button(self, text="Slim & Re-Check", command=self.run, height=2)
        self.btn.pack(pady=12)
        self.log = scrolledtext.ScrolledText(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.write("DeckShrink compresses the pictures embedded inside your Office files\n"
                   "and writes NEW slimmed files — originals untouched — then re-opens\n"
                   "every output and proves it still works. Everything runs locally.\n")

    def write(self, s):
        self.log.insert("end", s)
        self.log.see("end")

    def _refresh(self):
        self.count_lbl.config(text=f"{len(self.paths)} file(s)/folder(s) selected")

    def pick_files(self):
        ps = filedialog.askopenfilenames(
            filetypes=[("Office files", "*.pptx *.docx *.xlsx"), ("All files", "*.*")])
        self.paths += list(ps)
        self._refresh()

    def pick_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.paths.append(p)
        self._refresh()

    def clear(self):
        self.paths = []
        self._refresh()

    def run(self):
        if not self.paths:
            messagebox.showerror("DeckShrink", "Add at least one file or folder first.")
            return
        self.btn.config(state="disabled")
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            home = os.path.expanduser("~")
            outdir = os.path.join(home, "DeckShrink_output")
            s = run_deckshrink(self.paths, outdir, max_dim=int(self.maxdim.get()),
                               jpeg_quality=int(self.quality.get()),
                               strip_thumbnail=self.strip.get())
            saved = s["total_in"] - s["total_out"]
            pct = round(100.0 * saved / s["total_in"], 1) if s["total_in"] else 0
            self.write(f"\nDone. {len(s['files'])} file(s): {s['total_in']} -> "
                       f"{s['total_out']} bytes ({pct}% saved). Errors: {len(s['errors'])}.\n"
                       f"Re-check verdict: {'PASS' if s['verdict'] else 'CHECK REPORT'}\n"
                       f"Output folder: {outdir}\nReport: {s['report_path']}\n")
        except Exception as e:
            self.write(f"\nError: {e}\n")
        finally:
            self.btn.config(state="normal")


if __name__ == "__main__":
    App().mainloop()
