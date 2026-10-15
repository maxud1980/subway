from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from app import media
from app import theme as T
from app.subtitles import formats
from app.subtitles.srt import _parse_timestamp, _timestamp, read_srt
from app.subtitles.types import Subtitle
from app.i18n import translate_start_time


class EditorWindow(ctk.CTkToplevel):
    """A simple subtitle editor: fix text and timing, listen to a line."""

    def __init__(self, app, job):
        super().__init__(app)
        self.app = app
        self.t = app.t
        self.job = job
        self.title(f"{self.t('Edit subtitles')} — {job.path.name}")
        self.geometry("1000x720")
        self.minsize(760, 560)
        self.configure(fg_color=T.BG)
        self.after(150, self.lift)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.files: dict[str, Path] = {}
        if job.main_srt:
            self.files[self.t("Original")] = job.main_srt
        for label, path in job.outputs.items():
            if path.suffix.lower() == ".srt" and path != job.main_srt:
                self.files[label] = path
        self.media_path: Path | None = job.media_path if job.media_path else (None if job.is_srt else job.path)
        self.path: Path = next(iter(self.files.values()))
        self.subs: list[Subtitle] = []
        self.current: int | None = None
        self.dirty = False
        self._loading = False

        self._style()
        self._build()
        self._load(self.path)
        self.bind("<Control-s>", lambda _e: self.save())

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Subway.Treeview", background=T.SURFACE, fieldbackground=T.SURFACE, foreground=T.TEXT,
                        rowheight=28, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Subway.Treeview.Heading", background=T.RAISED, foreground=T.MUTED, relief="flat",
                        font=("Segoe UI", 10, "bold"))
        style.map("Subway.Treeview", background=[("selected", T.ACCENT)], foreground=[("selected", "#FFFFFF")])
        style.map("Subway.Treeview.Heading", background=[("active", T.LINE)])
        style.layout("Subway.Treeview", [("Subway.Treeview.treearea", {"sticky": "nswe"})])

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        self.file_menu = ctk.CTkOptionMenu(top, values=list(self.files), command=self._switch_file, width=220,
                                           fg_color=T.RAISED, button_color=T.LINE, button_hover_color=T.ACCENT)
        self.file_menu.grid(row=0, column=0)
        self.state_label = ctk.CTkLabel(top, text="", text_color=T.MUTED)
        self.state_label.grid(row=0, column=1, padx=12, sticky="w")
        self.save_button = ctk.CTkButton(top, text=self.t("Save"), width=110, command=self.save,
                                         fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER)
        self.save_button.grid(row=0, column=2)

        table = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.LINE)
        table.grid(row=1, column=0, padx=16, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("n", "start", "end", "text"), show="headings",
                                 style="Subway.Treeview", selectmode="browse")
        for column, title, width, stretch in (("n", "#", 50, False), ("start", translate_start_time(self.app.settings.ui_language), 110, False),
                                              ("end", self.t("End"), 110, False), ("text", self.t("Text"), 600, True)):
            self.tree.heading(column, text=title, anchor="w")
            self.tree.column(column, width=width, stretch=stretch, anchor="w")
        self.tree.grid(row=0, column=0, padx=(8, 0), pady=8, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(table, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, padx=(0, 4), pady=8, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        panel = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.LINE)
        panel.grid(row=2, column=0, padx=16, pady=(10, 16), sticky="ew")
        panel.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(panel, text=translate_start_time(self.app.settings.ui_language), text_color=T.MUTED).grid(row=0, column=0, padx=(14, 6), pady=(12, 4), sticky="w")
        self.start_entry = ctk.CTkEntry(panel, width=120)
        self.start_entry.grid(row=0, column=1, pady=(12, 4))
        ctk.CTkLabel(panel, text=self.t("End"), text_color=T.MUTED).grid(row=0, column=2, padx=(14, 6), pady=(12, 4), sticky="w")
        self.end_entry = ctk.CTkEntry(panel, width=120)
        self.end_entry.grid(row=0, column=3, pady=(12, 4), sticky="w")
        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=0, column=4, padx=14, pady=(12, 4), sticky="e")
        self.play_button = ctk.CTkButton(buttons, text="▶ " + self.t("Listen"), width=100, fg_color=T.RAISED,
                                         hover_color=T.LINE, command=self.play)
        self.play_button.pack(side="left", padx=3)
        ctk.CTkButton(buttons, text=self.t("Add after"), width=100, fg_color=T.RAISED, hover_color=T.LINE,
                      command=self.add_after).pack(side="left", padx=3)
        ctk.CTkButton(buttons, text=self.t("Delete"), width=90, fg_color=T.RAISED, hover_color=T.DANGER,
                      command=self.delete).pack(side="left", padx=3)
        self.text_box = ctk.CTkTextbox(panel, height=86, fg_color=T.BG, border_width=1, border_color=T.LINE,
                                       font=ctk.CTkFont(size=15))
        self.text_box.grid(row=1, column=0, columnspan=5, padx=14, pady=(4, 6), sticky="ew")
        self.info = ctk.CTkLabel(panel, text="", text_color=T.MUTED, font=ctk.CTkFont(size=12))
        self.info.grid(row=2, column=0, columnspan=5, padx=14, pady=(0, 10), sticky="w")
        for widget in (self.start_entry, self.end_entry):
            widget.bind("<KeyRelease>", lambda _e: self._apply())
        self.text_box.bind("<KeyRelease>", lambda _e: self._apply())
        if self.media_path is None:
            self.play_button.configure(state="disabled")

    # -- data -----------------------------------------------------------------
    def _load(self, path: Path) -> None:
        self.path = path
        self.subs = read_srt(path)
        self.current = None
        self.dirty = False
        self._fill()
        self._status()
        if self.subs:
            self._select(0)

    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, sub in enumerate(self.subs):
            self.tree.insert("", "end", iid=str(index), values=self._row(index, sub))

    @staticmethod
    def _row(index: int, sub: Subtitle) -> tuple:
        return (index + 1, _timestamp(sub.start), _timestamp(sub.end), sub.text.replace("\n", "  ⏎  "))

    def _status(self) -> None:
        name = self.path.name
        self.state_label.configure(text=f"{name} — {self.t('unsaved changes')}" if self.dirty else name,
                                   text_color=T.WARNING if self.dirty else T.MUTED)

    def _select(self, index: int) -> None:
        self.tree.selection_set(str(index))
        self.tree.see(str(index))

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.current = int(selection[0])
        sub = self.subs[self.current]
        self._loading = True
        for entry, value in ((self.start_entry, sub.start), (self.end_entry, sub.end)):
            entry.delete(0, "end")
            entry.insert(0, _timestamp(value))
            entry.configure(border_color=T.LINE)
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", sub.text)
        self._loading = False
        self._info(sub)

    def _info(self, sub: Subtitle) -> None:
        duration = max(sub.end - sub.start, 0.001)
        chars = len(sub.text.replace("\n", ""))
        longest = max((len(line) for line in sub.text.splitlines()), default=0)
        cps = chars / duration
        s = self.app.settings
        warn = cps > s.max_cps or longest > s.max_chars_per_line
        self.info.configure(
            text=f"{duration:.2f} s · {chars} {self.t('characters')} · {cps:.0f} {self.t('characters per second')}",
            text_color=T.WARNING if warn else T.MUTED)

    def _apply(self) -> None:
        if self._loading or self.current is None:
            return
        sub = self.subs[self.current]
        text = "\n".join(line.strip() for line in self.text_box.get("1.0", "end").strip().splitlines() if line.strip())
        start, end = sub.start, sub.end
        for entry, name in ((self.start_entry, "start"), (self.end_entry, "end")):
            try:
                value = _parse_timestamp(entry.get())
                entry.configure(border_color=T.LINE)
                if name == "start":
                    start = value
                else:
                    end = value
            except ValueError:
                entry.configure(border_color=T.DANGER)
        if end <= start:
            self.end_entry.configure(border_color=T.DANGER)
            end = sub.end if sub.end > start else start + 0.5
        if (text, start, end) != (sub.text, sub.start, sub.end):
            sub.text, sub.start, sub.end = text, start, end
            self.tree.item(str(self.current), values=self._row(self.current, sub))
            self.dirty = True
            self._status()
            self._info(sub)

    def add_after(self) -> None:
        index = self.current if self.current is not None else len(self.subs) - 1
        base_end = self.subs[index].end if self.subs else 0.0
        next_start = self.subs[index + 1].start if index + 1 < len(self.subs) else base_end + 2.0
        start = base_end + 0.05
        end = max(start + 0.5, min(start + 2.0, next_start - 0.05))
        self.subs.insert(index + 1, Subtitle(start, end, "…"))
        self.dirty = True
        self._fill()
        self._status()
        self._select(index + 1)
        self.text_box.focus_set()

    def delete(self) -> None:
        if self.current is None or not self.subs:
            return
        index = self.current
        del self.subs[index]
        self.dirty = True
        self.current = None
        self._fill()
        self._status()
        if self.subs:
            self._select(min(index, len(self.subs) - 1))

    def play(self) -> None:
        if self.current is None or self.media_path is None:
            return
        sub = self.subs[self.current]
        self.play_button.configure(state="disabled")

        def worker():
            error = None
            try:
                ffmpeg = media.find_ffmpeg(self.app.model_manager.runtime_dir)
                clip = Path(tempfile.gettempdir()) / "Subway" / "preview.wav"
                clip.parent.mkdir(parents=True, exist_ok=True)
                media.stop_playback()
                media.extract_clip(ffmpeg, self.media_path, sub.start - 0.3, sub.end + 0.3, clip)
                if not media.play_wav(clip):
                    error = self.t("Audio preview is available on Windows only.")
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            self.after(0, self._played, error)

        threading.Thread(target=worker, daemon=True).start()

    def _played(self, error: str | None) -> None:
        if self.winfo_exists():
            self.play_button.configure(state="normal")
            if error:
                messagebox.showwarning("Subway", error, parent=self)

    def save(self) -> bool:
        self._apply()
        self.subs.sort(key=lambda s: s.start)
        try:
            formats.write(self.subs, self.path, "srt")
            for fmt in ("vtt", "ass", "txt"):  # Keep the other formats in sync.
                sibling = self.path.with_suffix("." + fmt)
                if sibling.exists():
                    formats.write(self.subs, sibling, fmt)
        except OSError as exc:
            messagebox.showerror("Subway", str(exc), parent=self)
            return False
        self.dirty = False
        self._fill()
        self._status()
        self.app.log(f"Saved: {self.path}")
        return True

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Subway", self.t("Save changes?"), parent=self)
        if answer is None:
            return False
        return self.save() if answer else True

    def _switch_file(self, label: str) -> None:
        target = self.files[label]
        if target == self.path:
            return
        if not self._confirm_discard():
            current_label = next(k for k, v in self.files.items() if v == self.path)
            self.file_menu.set(current_label)
            return
        self._load(target)

    def close(self) -> None:
        if self._confirm_discard():
            media.stop_playback()
            self.destroy()
