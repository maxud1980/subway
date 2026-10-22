from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from app import theme as T
from app.config import AppSettings, load_settings, save_settings
from app.i18n import UI_LANGUAGES, translate as tr
from app.languages import LANGUAGES, language_code, names_for
from app.media import MEDIA_EXTENSIONS
from app.net import urlopen
from app.pipeline import CANCELLED, DONE, FAILED, QUEUED, RUNNING, Job, Pipeline
from app.process import CancelToken, Cancelled
from app.settings import load_api_key
from app.transcription import catalog
from app.transcription.models import ModelInfo, ModelManager

try:  # Drag and drop is optional: the app still works without it.
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - depends on the platform build
    DND_FILES = None
    TkinterDnD = None

APP_NAME = "Subway"
APP_VERSION = "0.2.0"
REPOSITORY_URL = "https://github.com/maxud1980/subway"
LATEST_RELEASE_URL = "https://api.github.com/repos/maxud1980/subway/releases/latest"
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
FILE_TYPES = [
    ("Video, audio and subtitles", " ".join(f"*{e}" for e in sorted(MEDIA_EXTENSIONS | {".srt"}))),
    ("All files", "*.*"),
]


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative_path


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", value)[:3]) or (0,)


def open_in_explorer(path: Path) -> None:
    try:
        if sys.platform == "win32":
            if path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
    except OSError:
        pass


_Base = (ctk.CTk, TkinterDnD.DnDWrapper) if TkinterDnD else (ctk.CTk,)


class SubwayApp(*_Base):  # type: ignore[misc]
    def __init__(self):
        super().__init__()
        self.dnd_ready = False
        if TkinterDnD:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ready = True
            except Exception:
                self.dnd_ready = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(APP_NAME)
        try:
            self.iconbitmap(str(resource_path("assets/subway.ico")))
        except Exception:
            pass
        self.geometry("1220x820")
        self.minsize(1000, 680)
        self.configure(fg_color=T.BG)

        self.settings: AppSettings = load_settings()
        if self.settings.ui_language not in UI_LANGUAGES:
            self.settings.ui_language = "English"
        self.model_manager = ModelManager()
        self._apply_catalog(catalog.load_cached(), quiet=True)
        self.jobs: list[Job] = []
        self.rows: dict[int, JobRow] = {}
        self.pipeline: Pipeline | None = None
        self.download_cancel: CancelToken | None = None
        self.log_lines: list[str] = []
        self.log_visible = False
        self.update_info: tuple[str, str] | None = None
        self.settings_window = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if sys.platform == "darwin":
            try:  # Cmd+Q and "Quit Subway" in the menu bar ask the same question as closing the window.
                self.createcommand("tk::mac::Quit", self._on_close)
            except Exception:
                pass
        self.after(1500, lambda: self.check_for_updates(silent=True))

    # ------------------------------------------------------------------ utils
    def t(self, text: str) -> str:
        return tr(text, self.settings.ui_language)

    @property
    def busy(self) -> bool:
        return self.pipeline is not None

    def save(self) -> None:
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.log(f"WARNING: settings could not be saved: {exc}")

    def log(self, text: str) -> None:
        self.log_lines.append(text)
        self.log_lines = self.log_lines[-2000:]
        if hasattr(self, "log_box") and self.log_box.winfo_exists():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    def log_threadsafe(self, text: str) -> None:
        self.after(0, self.log, text)

    def font(self, size: int = 13, weight: str = "normal") -> ctk.CTkFont:
        return ctk.CTkFont(size=size, weight=weight)

    # --------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=390)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_queue()
        self._build_options()
        self._build_log()
        self._render_rows()
        self._refresh_model_status()
        self._refresh_actions()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=24, pady=(18, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        try:
            image = Image.open(resource_path("assets/subway.ico")).convert("RGBA")
            self.logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=(44, 44))
            ctk.CTkLabel(header, text="", image=self.logo_image).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        except Exception:
            pass
        ctk.CTkLabel(header, text="Subway", font=self.font(26, "bold"), text_color=T.TEXT).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(header, text=self.t("Local subtitle generator"), font=self.font(13),
                     text_color=T.MUTED).grid(row=1, column=1, sticky="nw")
        self.update_link = ctk.CTkButton(header, text="", fg_color="transparent", hover_color=T.RAISED,
                                         text_color=T.WARNING, command=self._open_update, width=10)
        self.update_link.grid(row=0, column=2, rowspan=2, padx=8)
        self._refresh_update_link()
        ctk.CTkButton(header, text=self.t("Settings"), width=120, height=36, fg_color=T.RAISED,
                      hover_color=T.LINE, command=self.open_settings).grid(row=0, column=3, rowspan=2)

    def _card(self, parent, **grid) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.LINE)
        frame.grid(**grid)
        return frame

    def _build_queue(self) -> None:
        card = self._card(self, row=1, column=0, padx=(24, 8), pady=(4, 8), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        self.queue_card = card

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, padx=T.PAD, pady=(14, 6), sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text=self.t("Queue"), font=self.font(17, "bold"), text_color=T.TEXT).grid(row=0, column=0, sticky="w")
        self.clear_button = ctk.CTkButton(top, text=self.t("Clear finished"), width=130, height=32,
                                          fg_color="transparent", border_width=1, border_color=T.LINE,
                                          hover_color=T.RAISED, command=self.clear_finished)
        self.clear_button.grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(top, text=self.t("Add files"), width=130, height=32, command=self.add_files_dialog,
                      fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER).grid(row=0, column=2, padx=(8, 0))

        self.queue_list = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.queue_list.grid(row=1, column=0, padx=(6, 6), pady=(0, 6), sticky="nsew")
        self.queue_list.grid_columnconfigure(0, weight=1)

        hint = self.t("Drop video, audio or SRT files here") if self.dnd_ready else self.t("Add video, audio or SRT files")
        self.empty_state = ctk.CTkFrame(self.queue_list, fg_color=T.BG, corner_radius=T.RADIUS,
                                        border_width=2, border_color=T.LINE, height=220)
        ctk.CTkLabel(self.empty_state, text=hint, font=self.font(16, "bold"), text_color=T.TEXT).pack(pady=(70, 6))
        ctk.CTkLabel(self.empty_state, text=self.t("Several files can be processed one after another. Media never leaves your computer."),
                     text_color=T.MUTED, wraplength=460).pack(padx=20)

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=2, column=0, padx=T.PAD, pady=(0, 12), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        self.summary = ctk.CTkLabel(bottom, text="", text_color=T.MUTED, anchor="w")
        self.summary.grid(row=0, column=0, sticky="w")
        self.log_toggle = ctk.CTkButton(bottom, text=self.t("Show log"), width=110, height=28, fg_color="transparent",
                                        hover_color=T.RAISED, text_color=T.MUTED, command=self.toggle_log)
        self.log_toggle.grid(row=0, column=1)

        if self.dnd_ready:
            for widget in (card, self.queue_list, self.empty_state):
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass

    def _section(self, parent, row: int, title: str, hint: str | None = None) -> ctk.CTkFrame:
        ctk.CTkLabel(parent, text=title, font=self.font(15, "bold"), text_color=T.TEXT).grid(
            row=row, column=0, padx=T.PAD, pady=(14 if row else 12, 2), sticky="w")
        if hint:
            ctk.CTkLabel(parent, text=hint, text_color=T.MUTED, font=self.font(12), wraplength=330,
                         justify="left").grid(row=row + 1, column=0, padx=T.PAD, sticky="w")
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=row + 2, column=0, padx=T.PAD, pady=(6, 4), sticky="ew")
        body.grid_columnconfigure(0, weight=1)
        return body

    def _build_options(self) -> None:
        card = self._card(self, row=1, column=1, padx=(8, 24), pady=(4, 8), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        scroll.grid(row=0, column=0, padx=2, pady=(6, 0), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        s = self.settings

        # Recognition
        body = self._section(scroll, 0, self.t("Recognition"))
        models = self.model_manager.available_models()
        self.model_menu = ctk.CTkOptionMenu(body, values=[m.name for m in models], command=self._model_changed,
                                            height=34, fg_color=T.RAISED, button_color=T.LINE, button_hover_color=T.ACCENT)
        self.model_menu.set(self.model_manager.get(s.model_id).name)
        self.model_menu.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.model_status = ctk.CTkLabel(body, text="", text_color=T.MUTED, font=self.font(12), wraplength=330, justify="left")
        self.model_status.grid(row=1, column=0, columnspan=2, pady=(6, 2), sticky="w")
        self.model_progress = ctk.CTkProgressBar(body, height=6, progress_color=T.ACCENT)
        self.model_progress.set(0)
        self.download_button = ctk.CTkButton(body, text=self.t("Download model"), height=32, command=self.download_model)
        self.download_button.grid(row=3, column=0, columnspan=2, pady=(4, 2), sticky="ew")
        ctk.CTkLabel(body, text=self.t("Spoken language"), text_color=T.TEXT).grid(row=4, column=0, pady=(10, 0), sticky="w")
        self.lang_menu = ctk.CTkComboBox(body, values=[], command=self._recognition_language_changed, width=190,
                                         state="readonly")
        self.lang_menu.grid(row=4, column=1, pady=(10, 0), sticky="e")
        self.lang_hint = ctk.CTkLabel(body, text="", text_color=T.MUTED, font=self.font(12), wraplength=330, justify="left")
        self.lang_hint.grid(row=5, column=0, columnspan=2, sticky="w")
        self.lang_switch = ctk.CTkButton(body, text="", height=30, fg_color=T.RAISED, hover_color=T.LINE,
                                         command=self._switch_to_supporting_model)

        # Translation
        body = self._section(scroll, 3, self.t("Translation"), self.t("Only subtitle text is sent to Gemini."))
        self.translate_var = ctk.BooleanVar(value=s.translate)
        ctk.CTkSwitch(body, text=self.t("Translate subtitles"), variable=self.translate_var,
                      command=self._translation_toggled, progress_color=T.ACCENT).grid(row=0, column=0, columnspan=2, sticky="w")
        self.targets_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.targets_frame.grid(row=1, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        self.targets_frame.grid_columnconfigure(0, weight=1)
        add_row = ctk.CTkFrame(body, fg_color="transparent")
        add_row.grid(row=2, column=0, columnspan=2, pady=(6, 0), sticky="ew")
        add_row.grid_columnconfigure(0, weight=1)
        self.add_lang = ctk.CTkComboBox(add_row, values=list(LANGUAGES))
        self.add_lang.set("English" if "English" not in s.target_languages else "German")
        self.add_lang.grid(row=0, column=0, sticky="ew")
        self.add_lang_button = ctk.CTkButton(add_row, text=self.t("Add language"), width=120, command=self._add_target,
                                             fg_color=T.RAISED, hover_color=T.LINE)
        self.add_lang_button.grid(row=0, column=1, padx=(8, 0))
        ctk.CTkLabel(body, text=self.t("Model"), text_color=T.TEXT).grid(row=3, column=0, pady=(10, 0), sticky="w")
        self.gemini_menu = ctk.CTkComboBox(body, values=GEMINI_MODELS, command=self._gemini_changed, width=190)
        self.gemini_menu.set(s.gemini_model)
        self.gemini_menu.grid(row=3, column=1, pady=(10, 0), sticky="e")
        self.gemini_menu.bind("<FocusOut>", lambda _e: self._gemini_changed(self.gemini_menu.get()))

        # Output
        body = self._section(scroll, 6, self.t("Output"), self.t("SRT is always saved. Choose extra formats:"))
        self.format_vars: dict[str, ctk.BooleanVar] = {}
        labels = {"vtt": "WebVTT (.vtt)", "ass": "ASS (.ass)", "txt": self.t("Transcript (.txt)")}
        for index, fmt in enumerate(("vtt", "ass", "txt")):
            var = ctk.BooleanVar(value=fmt in s.formats)
            self.format_vars[fmt] = var
            ctk.CTkCheckBox(body, text=labels[fmt], variable=var, command=self._formats_changed,
                            fg_color=T.ACCENT).grid(row=index, column=0, columnspan=2, pady=2, sticky="w")
        self.burn_var = ctk.BooleanVar(value=s.burn_in)
        ctk.CTkSwitch(body, text=self.t("Burn subtitles into video"), variable=self.burn_var,
                      command=self._burn_changed, progress_color=T.ACCENT).grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="w")
        self.burn_menu = ctk.CTkOptionMenu(body, values=[self.t("Original")], command=self._burn_language_changed,
                                           fg_color=T.RAISED, button_color=T.LINE, button_hover_color=T.ACCENT)
        self.burn_menu.grid(row=4, column=0, columnspan=2, pady=(6, 0), sticky="ew")
        self.burn_hint = ctk.CTkLabel(body, text=self.t("Creates a new MP4 next to the source. The original video is not changed."),
                                      text_color=T.MUTED, font=self.font(12), wraplength=330, justify="left")
        self.burn_hint.grid(row=5, column=0, columnspan=2, sticky="w")

        # Actions
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=1, column=0, padx=T.PAD, pady=(8, 14), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        self.start_button = ctk.CTkButton(actions, text=self.t("Start"), height=44, font=self.font(15, "bold"),
                                          fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, command=self.start)
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ctk.CTkButton(actions, text=self.t("Stop"), height=44, width=96, fg_color=T.RAISED,
                                         hover_color=T.DANGER, command=self.stop)
        self.stop_button.grid(row=0, column=1, padx=(8, 0))

        self._render_targets()
        self._refresh_language_menu()
        self._translation_toggled(save=False)
        self._burn_changed(save=False)

    def _build_log(self) -> None:
        self.log_box = ctk.CTkTextbox(self, height=150, fg_color=T.SURFACE, text_color="#AFC4DE",
                                      border_width=1, border_color=T.LINE, font=ctk.CTkFont(family=T.MONO_FONT, size=12))
        self.log_box.insert("1.0", "\n".join(self.log_lines) + ("\n" if self.log_lines else ""))
        self.log_box.configure(state="disabled")
        if self.log_visible:
            self.log_box.grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="ew")
            self.log_toggle.configure(text=self.t("Hide log"))

    def toggle_log(self) -> None:
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_box.grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="ew")
            self.log_box.see("end")
        else:
            self.log_box.grid_remove()
        self.log_toggle.configure(text=self.t("Hide log") if self.log_visible else self.t("Show log"))

    # ------------------------------------------------------------- options
    def _model_changed(self, name: str) -> None:
        model = next(m for m in self.model_manager.available_models() if m.name == name)
        self.settings.model_id = model.id
        self.save()
        self._refresh_model_status()
        self._refresh_language_menu()

    def _refresh_language_menu(self) -> None:
        # Every language is listed, so a language the model does not know can be caught before recognition.
        auto = self.t("Detect automatically")
        self.lang_menu.configure(values=[auto] + sorted(LANGUAGES))
        current = self.settings.recognition_language
        self.lang_menu.set(current if current in LANGUAGES else auto)
        self._refresh_language_hint()

    def _recognition_language_changed(self, value: str) -> None:
        self.settings.recognition_language = value if value in LANGUAGES else "auto"
        self.save()
        self._refresh_language_hint()

    def _unsupported_language_text(self, model: ModelInfo, language: str) -> str:
        return self.t("{model} does not recognize {language}. The subtitles would be meaningless.").format(
            model=model.name, language=language)

    def _model_for_language(self, language: str) -> ModelInfo | None:
        """A model that recognizes the language, preferring one that is already downloaded."""
        code = language_code(language)
        models = [m for m in self.model_manager.available_models() if m.recognizes_language(code)]
        return next((m for m in models if self.model_manager.installed(m.id)), models[0] if models else None)

    def _refresh_language_hint(self) -> None:
        if not hasattr(self, "lang_hint"):
            return
        model = self.model_manager.get(self.settings.model_id)
        language = self.settings.recognition_language
        self.lang_switch.grid_remove()
        if language not in LANGUAGES:
            known = ", ".join(names_for(model.recognized_languages))
            text = f"{self.t('This model recognizes only')}: {known}. {self.t('Choose the spoken language so Subway can check it.')}"
            color = T.MUTED
        elif model.recognizes_language(language_code(language)):
            text = "✓ " + (self.t("Choosing the language improves accuracy.") if model.supports_language
                           else self.t("Supported. This model detects the language by itself."))
            color = T.SUCCESS
        else:
            text = "✕ " + self._unsupported_language_text(model, language)
            alternative = self._model_for_language(language)
            if alternative:
                self.lang_switch.configure(text=self.t("Switch to {model}").format(model=alternative.name))
                self.lang_switch.grid(row=6, column=0, columnspan=2, pady=(4, 0), sticky="ew")
            else:
                text += " " + self.t("No available model recognizes this language.")
            color = T.DANGER
        self.lang_hint.configure(text=text, text_color=color)

    def _switch_to_supporting_model(self) -> None:
        model = self._model_for_language(self.settings.recognition_language)
        if model is None or self.busy or self.download_cancel is not None:
            return
        self.model_menu.set(model.name)
        self._model_changed(model.name)

    def _translation_toggled(self, save: bool = True) -> None:
        self.settings.translate = bool(self.translate_var.get())
        state = "normal" if self.settings.translate else "disabled"
        for widget in (self.add_lang, self.add_lang_button, self.gemini_menu):
            widget.configure(state=state)
        self._render_targets()
        self._refresh_burn_menu()
        if save:
            self.save()

    def _render_targets(self) -> None:
        for child in self.targets_frame.winfo_children():
            child.destroy()
        enabled = self.settings.translate
        if not self.settings.target_languages:
            ctk.CTkLabel(self.targets_frame, text=self.t("No target languages yet."), text_color=T.MUTED).grid(row=0, column=0, sticky="w")
        for index, name in enumerate(self.settings.target_languages):
            row = ctk.CTkFrame(self.targets_frame, fg_color=T.RAISED if enabled else T.BG, corner_radius=8)
            row.grid(row=index, column=0, pady=2, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=name, text_color=T.TEXT if enabled else T.MUTED).grid(row=0, column=0, padx=10, pady=4, sticky="w")
            ctk.CTkButton(row, text="✕", width=28, height=24, fg_color="transparent", hover_color=T.DANGER,
                          text_color=T.MUTED, state="normal" if enabled else "disabled",
                          command=lambda n=name: self._remove_target(n)).grid(row=0, column=1, padx=4)

    def _add_target(self) -> None:
        name = self.add_lang.get().strip()
        match = next((n for n in LANGUAGES if n.lower() == name.lower()), None)
        if not match:
            messagebox.showwarning(APP_NAME, self.t("Choose a language from the list."), parent=self)
            return
        if match not in self.settings.target_languages:
            self.settings.target_languages.append(match)
            self.save()
            self._render_targets()
            self._refresh_burn_menu()

    def _remove_target(self, name: str) -> None:
        if name in self.settings.target_languages:
            self.settings.target_languages.remove(name)
            if self.settings.burn_in_language == name:
                self.settings.burn_in_language = ""
            self.save()
            self._render_targets()
            self._refresh_burn_menu()

    def _gemini_changed(self, value: str) -> None:
        value = value.strip()
        if value and value != self.settings.gemini_model:
            self.settings.gemini_model = value
            self.save()

    def _formats_changed(self) -> None:
        self.settings.formats = ["srt"] + [f for f, var in self.format_vars.items() if var.get()]
        self.save()

    def _refresh_burn_menu(self) -> None:
        if not hasattr(self, "burn_menu"):
            return
        original = self.t("Original")
        values = [original] + (list(self.settings.target_languages) if self.settings.translate else [])
        self.burn_menu.configure(values=values)
        current = self.settings.burn_in_language
        self.burn_menu.set(current if current in values else original)

    def _burn_changed(self, save: bool = True) -> None:
        self.settings.burn_in = bool(self.burn_var.get())
        self.burn_menu.configure(state="normal" if self.settings.burn_in else "disabled")
        self._refresh_burn_menu()
        if save:
            self.save()

    def _burn_language_changed(self, value: str) -> None:
        self.settings.burn_in_language = "" if value == self.t("Original") else value
        self.save()

    # --------------------------------------------------------------- models
    def _refresh_model_status(self) -> None:
        model = self.model_manager.get(self.settings.model_id)
        downloading = self.download_cancel is not None
        if downloading:
            return
        self.model_progress.grid_remove()
        installed = self.model_manager.installed(model.id)
        if installed == model:
            self.model_status.configure(text=f"✓ {self.t('Model ready')} · {model.size_mb} MB · {self.t(model.languages)}", text_color=T.SUCCESS)
            self.download_button.grid_remove()
        elif installed is not None:
            version = f" ({model.version})" if model.version else ""
            notes = f"\n{model.notes}" if model.notes else ""
            self.model_status.configure(text=f"✓ {self.t('Model ready')} · {self.t('a newer version is available')}{version}{notes}",
                                        text_color=T.WARNING)
            self.download_button.configure(text=f"{self.t('Update model')} · {model.size_mb} MB", state="normal", fg_color=T.ACCENT)
            self.download_button.grid()
        else:
            self.model_status.configure(text=f"{self.t('Not downloaded')} · {model.size_mb} MB · {self.t(model.languages)}", text_color=T.MUTED)
            self.download_button.configure(text=self.t("Download model"), state="normal", fg_color=T.ACCENT)
            self.download_button.grid()

    def download_model(self) -> None:
        if self.download_cancel is not None:
            self.download_cancel.cancel()
            self.download_button.configure(state="disabled")
            return
        model = self.model_manager.get(self.settings.model_id)
        self.download_cancel = CancelToken()
        self.model_menu.configure(state="disabled")
        self.download_button.configure(text=self.t("Cancel download"), fg_color=T.RAISED)
        self.model_progress.set(0)
        self.model_progress.grid(row=2, column=0, columnspan=2, pady=(2, 2), sticky="ew")
        self.log(f"Downloading {model.name}…")
        token = self.download_cancel

        def worker():
            try:
                path = self.model_manager.download(
                    model, progress=lambda got, total: self.after(0, self._download_progress, got, total), cancel=token)
                self.after(0, self._download_finished, None, path, model)
            except Cancelled:
                self.after(0, self._download_finished, "cancelled", None, model)
            except Exception as exc:  # noqa: BLE001
                self.after(0, self._download_finished, str(exc), None, model)

        threading.Thread(target=worker, daemon=True).start()

    def _download_progress(self, received: int, total: int) -> None:
        if total:
            self.model_progress.set(min(received / total, 1))
            self.model_status.configure(text=f"{self.t('Downloading…')} {received / 1048576:.0f} / {total / 1048576:.0f} MB",
                                        text_color=T.MUTED)

    def _download_finished(self, error: str | None, path: Path | None, model: ModelInfo) -> None:
        self.download_cancel = None
        self.model_menu.configure(state="normal")
        if path:
            self.log(f"Model saved: {path}")
            older = self.model_manager.older_size(model.id)
            question = self.t("The new version is ready. Delete the previous version to free {size} MB?").format(
                size=round(older / 1048576))
            if older and messagebox.askyesno(APP_NAME, question, parent=self):
                self.model_manager.remove_older(model.id)
            self._refresh_update_link()
        elif error == "cancelled":
            self.log("Model download cancelled. It will resume next time.")
        elif error:
            self.log(f"ERROR: model download failed: {error}")
            messagebox.showerror(APP_NAME, f"{self.t('Model download failed.')}\n\n{error}", parent=self)
        self._refresh_model_status()
        self._refresh_actions()

    # ---------------------------------------------------------------- queue
    def _on_drop(self, event) -> None:
        self.add_paths([Path(p) for p in self.tk.splitlist(event.data)])

    def add_files_dialog(self) -> None:
        names = filedialog.askopenfilenames(title=self.t("Add files"), filetypes=FILE_TYPES, parent=self)
        if names:
            self.add_paths([Path(n) for n in names])

    def add_paths(self, paths: list[Path]) -> None:
        allowed = MEDIA_EXTENSIONS | {".srt"}
        files: list[Path] = []
        for path in paths:
            if path.is_dir():
                files += sorted(p for p in path.iterdir() if p.suffix.lower() in allowed)
            elif path.suffix.lower() in allowed:
                files.append(path)
        skipped = [p for p in paths if p.is_file() and p.suffix.lower() not in allowed]
        known = {job.path for job in self.jobs if job.status in (QUEUED, RUNNING)}
        added = 0
        for path in files:
            if path not in known:
                self.jobs.append(Job(path))
                known.add(path)
                added += 1
        if skipped:
            self.log(f"Skipped unsupported files: {', '.join(p.name for p in skipped)}")
        if added:
            self._render_rows()
            self._refresh_actions()

    def remove_job(self, job: Job) -> None:
        if job.status == RUNNING:
            return
        self.jobs.remove(job)
        self._render_rows()
        self._refresh_actions()

    def clear_finished(self) -> None:
        self.jobs[:] = [j for j in self.jobs if j.status in (QUEUED, RUNNING)]  # in place: the worker shares it
        self._render_rows()
        self._refresh_actions()

    def _render_rows(self) -> None:
        for row in self.rows.values():
            row.destroy()
        self.rows = {}
        if not self.jobs:
            self.empty_state.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
            return
        self.empty_state.grid_forget()
        for index, job in enumerate(self.jobs):
            row = JobRow(self.queue_list, self, job, first=index == 0, last=index == len(self.jobs) - 1)
            row.grid(row=index, column=0, padx=(4, 4), pady=0, sticky="ew")
            if self.dnd_ready:
                try:
                    row.drop_target_register(DND_FILES)
                    row.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass
            self.rows[job.id] = row

    def _job_changed(self, job_id: int) -> None:
        row = self.rows.get(job_id)
        if row is not None and row.winfo_exists():
            row.refresh()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        counts = {status: sum(1 for j in self.jobs if j.status == status) for status in (QUEUED, RUNNING, DONE, FAILED)}
        parts = []
        if counts[RUNNING]:
            parts.append(self.t("working"))
        if counts[QUEUED]:
            parts.append(f"{counts[QUEUED]} {self.t('waiting')}")
        if counts[DONE]:
            parts.append(f"{counts[DONE]} {self.t('done')}")
        if counts[FAILED]:
            parts.append(f"{counts[FAILED]} {self.t('failed')}")
        self.summary.configure(text=", ".join(parts))

    def _refresh_actions(self) -> None:
        queued = any(j.status == QUEUED for j in self.jobs)
        self.start_button.configure(state="normal" if queued and not self.busy else "disabled",
                                    text=self.t("Working…") if self.busy else self.t("Start"))
        self.stop_button.configure(state="normal" if self.busy else "disabled")
        self.clear_button.configure(state="normal" if any(j.status not in (QUEUED, RUNNING) for j in self.jobs) else "disabled")
        self._refresh_summary()

    # ------------------------------------------------------------ pipeline
    def start(self) -> None:
        if self.busy:
            return
        jobs = [j for j in self.jobs if j.status == QUEUED]
        if not jobs:
            return
        s = self.settings
        needs_model = any(not j.is_srt for j in jobs)
        model = self.model_manager.installed(s.model_id) or self.model_manager.get(s.model_id)
        if needs_model and s.recognition_language in LANGUAGES and not model.recognizes_language(language_code(s.recognition_language)):
            message = self._unsupported_language_text(model, s.recognition_language)
            alternative = self._model_for_language(s.recognition_language)
            if alternative is None:
                messagebox.showerror(APP_NAME, f"{message}\n\n{self.t('No available model recognizes this language.')}", parent=self)
            else:
                switch = self.t("Switch to {model}").format(model=alternative.name)
                if messagebox.askyesno(APP_NAME, f"{message}\n\n{switch}?", parent=self):
                    self._switch_to_supporting_model()
            return
        if needs_model and self.model_manager.installed(s.model_id) is None:
            messagebox.showwarning(APP_NAME, self.t("Download the selected recognition model first."), parent=self)
            return
        if any(j.is_srt for j in jobs) and not s.translate:
            messagebox.showwarning(APP_NAME, self.t("Turn on translation to process SRT files."), parent=self)
            return
        api_key = ""
        if s.translate:
            if not s.target_languages:
                messagebox.showwarning(APP_NAME, self.t("Add at least one target language."), parent=self)
                return
            try:
                api_key = load_api_key()
            except Exception:
                api_key = ""
            if not api_key:
                messagebox.showwarning(APP_NAME, self.t("Enter a Gemini API key in Settings to translate subtitles."), parent=self)
                self.open_settings()
                return

        self.pipeline = Pipeline(
            deepcopy(s), api_key, self.model_manager.runtime_dir,
            notify=lambda job: self.after(0, self._job_changed, job.id),
            log=self.log_threadsafe, models=self.model_manager,
        )
        self._refresh_actions()
        self.model_menu.configure(state="disabled")
        pipeline = self.pipeline

        def worker():
            try:
                pipeline.run(self.jobs)  # The live list: files added meanwhile are processed too.
            finally:
                self.after(0, self._finished)

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.cancel.cancel()
            self.stop_button.configure(state="disabled")
            self.log("Stopping…")

    def _finished(self) -> None:
        self.pipeline = None
        self.model_menu.configure(state="normal")
        for job in self.jobs:
            if job.status == RUNNING:
                job.status = CANCELLED
        self._render_rows()
        self._refresh_actions()
        failed = [j for j in self.jobs if j.status == FAILED]
        self.bell()
        if failed and not self.log_visible:
            self.toggle_log()

    # ------------------------------------------------------------- windows
    def open_settings(self) -> None:
        from app.ui_settings import SettingsWindow

        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return
        self.settings_window = SettingsWindow(self)

    def open_editor(self, job: Job) -> None:
        from app.ui_editor import EditorWindow

        if job.main_srt and job.main_srt.exists():
            EditorWindow(self, job)

    def apply_ui_language(self, language: str) -> None:
        if language == self.settings.ui_language:
            return
        self.settings.ui_language = language
        self.save()
        if self.busy:
            messagebox.showinfo(APP_NAME, self.t("The new language will be applied after the current work finishes."), parent=self)
            return
        self.rebuild()

    def rebuild(self) -> None:
        for widget in self.winfo_children():
            if widget is not self.settings_window:
                widget.destroy()
        self.rows = {}
        self._build_ui()
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
            self.open_settings()

    # -------------------------------------------------------------- updates
    def check_for_updates(self, silent: bool = False, callback=None) -> None:
        self.check_models()

        def worker():
            try:
                request = urllib.request.Request(LATEST_RELEASE_URL, headers={
                    "Accept": "application/vnd.github+json", "User-Agent": "Subway-Update-Checker"})
                with urlopen(request, timeout=10) as response:
                    release = json.loads(response.read().decode("utf-8"))
                tag = str(release.get("tag_name", "")).strip()
                url = release.get("html_url") or f"{REPOSITORY_URL}/releases"
                newer = bool(tag) and version_tuple(tag) > version_tuple(APP_VERSION)
                self.after(0, self._update_result, tag, url, newer, None, callback)
            except Exception as exc:  # noqa: BLE001
                if not silent:
                    self.after(0, self._update_result, "", "", False, str(exc), callback)

        threading.Thread(target=worker, daemon=True).start()

    def _update_result(self, tag: str, url: str, newer: bool, error: str | None, callback) -> None:
        if newer:
            self.update_info = (tag, url)
            self._refresh_update_link()
        if callback:
            callback(tag, newer, error)

    def check_models(self) -> None:
        """Look for new versions of the recognition models in the online catalog."""
        def worker():
            try:
                models = catalog.fetch()
            except Exception as exc:  # noqa: BLE001
                self.log_threadsafe(f"The model list could not be checked: {exc}")
                return
            self.after(0, self._apply_catalog, models)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_catalog(self, models: list[ModelInfo], quiet: bool = False) -> None:
        current = version_tuple(APP_VERSION)
        usable = []
        for model in models:
            if version_tuple(model.min_app_version or "0") <= current:
                usable.append(model)
            elif not quiet:
                self.log(f"{model.name} {model.version} needs Subway {model.min_app_version} or newer. Update Subway to use it.")
        added = self.model_manager.add_versions(usable)
        if not added or not hasattr(self, "model_menu"):
            return
        if not quiet:
            for model in added:
                self.log(f"New recognition model available: {model.name} {model.version}".rstrip())
        if self.download_cancel is None:
            self.model_menu.configure(values=[m.name for m in self.model_manager.available_models()])
            self.model_menu.set(self.model_manager.get(self.settings.model_id).name)
            self._refresh_model_status()
        self._refresh_language_hint()
        self._refresh_update_link()

    def _model_with_update(self) -> ModelInfo | None:
        return next((m for m in self.model_manager.available_models() if self.model_manager.update_available(m.id)), None)

    def _refresh_update_link(self) -> None:
        if not hasattr(self, "update_link") or not self.update_link.winfo_exists():
            return
        model = self._model_with_update()
        if self.update_info:
            text = f"{self.t('Update available')}: {self.update_info[0]}"
        elif model:
            text = f"{self.t('Model update available')}: {model.name}"
        else:
            text = ""
        self.update_link.configure(text=text)

    def _open_update(self) -> None:
        if self.update_info:
            webbrowser.open(self.update_info[1])
            return
        model = self._model_with_update()
        if model and not self.busy and self.download_cancel is None:
            # Select the model: its status line then offers the update.
            self.model_menu.set(model.name)
            self._model_changed(model.name)

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(APP_NAME, self.t("Processing is still running. Stop it and quit?"), parent=self):
                return
            self.pipeline.cancel.cancel()
        if self.download_cancel is not None:
            self.download_cancel.cancel()
        self.destroy()


class JobRow(ctk.CTkFrame):
    """One station on the queue line."""

    def __init__(self, parent, app: SubwayApp, job: Job, first: bool, last: bool):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.job = job
        self.first, self.last = first, last
        self.grid_columnconfigure(1, weight=1)

        self.canvas = ctk.CTkCanvas(self, width=30, height=72, bg=T.SURFACE, highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(4, 6))
        self.canvas.bind("<Configure>", lambda _e: self._draw_line())

        kind = "SRT" if job.is_srt else ("🎞" if job.path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"} else "♪")
        name = ctk.CTkLabel(self, text=f"{job.path.name}", font=app.font(14, "bold"), text_color=T.TEXT, anchor="w")
        name.grid(row=0, column=1, pady=(10, 0), sticky="ew")
        self.kind = kind
        self.stage = ctk.CTkLabel(self, text="", text_color=T.MUTED, font=app.font(12), anchor="w", justify="left", wraplength=520)
        self.stage.grid(row=1, column=1, sticky="ew")
        self.bar = ctk.CTkProgressBar(self, height=5, progress_color=T.ACCENT, fg_color=T.RAISED)
        self.bar.grid(row=2, column=1, pady=(4, 10), sticky="ew")
        self.bar_mode = "determinate"

        buttons = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        buttons.grid(row=0, column=2, rowspan=3, padx=(8, 4))
        self.edit_button = ctk.CTkButton(buttons, text=app.t("Edit"), width=86, height=30, fg_color=T.RAISED,
                                         hover_color=T.LINE, command=lambda: app.open_editor(job))
        self.folder_button = ctk.CTkButton(buttons, text=app.t("Show"), width=70, height=30, fg_color="transparent",
                                           border_width=1, border_color=T.LINE, hover_color=T.RAISED,
                                           command=self._show_files)
        self.retry_button = ctk.CTkButton(buttons, text=app.t("Retry"), width=70, height=30, fg_color=T.RAISED,
                                          hover_color=T.LINE, command=self._retry)
        self.remove_button = ctk.CTkButton(buttons, text="✕", width=30, height=30, fg_color="transparent",
                                           hover_color=T.DANGER, text_color=T.MUTED, command=lambda: app.remove_job(job))
        self.refresh()

    def _draw_line(self) -> None:
        c = self.canvas
        c.delete("all")
        height = max(c.winfo_height(), 40)
        x, y, r = 15, 24, 7
        color = T.STATUS_COLORS.get(self.job.status, T.MUTED)
        if not self.first:
            c.create_line(x, 0, x, y, fill=T.LINE, width=4)
        if not self.last:
            c.create_line(x, y, x, height, fill=T.LINE, width=4)
        if self.job.status == QUEUED:
            c.create_oval(x - r, y - r, x + r, y + r, outline=color, width=3, fill=T.SURFACE)
        else:
            c.create_oval(x - r - 1, y - r - 1, x + r + 1, y + r + 1, outline=color, width=3, fill=color)

    def _show_files(self) -> None:
        outputs = list(self.job.outputs.values())
        open_in_explorer(outputs[0] if outputs else self.job.path)

    def _retry(self) -> None:
        self.job.status = QUEUED
        self.job.error = ""
        self.job.outputs = {}
        self.job.progress = 0.0
        self.refresh()
        self.app._refresh_actions()

    def _stage_text(self) -> str:
        job, t = self.job, self.app.t
        if job.status == QUEUED:
            return f"{self.kind}  " + (t("Waiting — will be translated") if job.is_srt else t("Waiting"))
        if job.status == FAILED:
            return f"{t('Failed')}: {job.error.splitlines()[0][:300] if job.error else ''}"
        if job.status == CANCELLED:
            return t("Stopped")
        if job.status == DONE:
            names = [p.name for p in job.outputs.values()]
            return f"{t('Saved')}: {', '.join(names)}" if names else t("Done")
        stage = job.stage
        if stage.startswith("Translating → "):
            return f"{t('Translating')} → {stage.split('→', 1)[1].strip()}"
        return t(stage)

    def refresh(self) -> None:
        job = self.job
        self.stage.configure(text=self._stage_text(), text_color=T.DANGER if job.status == FAILED else T.MUTED)
        running = job.status == RUNNING
        if running and job.progress is None:
            if self.bar_mode != "indeterminate":
                self.bar.configure(mode="indeterminate")
                self.bar.start()
                self.bar_mode = "indeterminate"
        else:
            if self.bar_mode != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
                self.bar_mode = "determinate"
            value = 1.0 if job.status == DONE else (job.progress or 0.0)
            self.bar.set(value)
        self.bar.configure(progress_color=T.STATUS_COLORS.get(job.status, T.ACCENT))
        if job.status in (RUNNING, DONE):
            self.bar.grid()
        else:
            self.bar.grid_remove()
        has_srt = job.main_srt is not None and job.status == DONE
        visible = [
            (self.edit_button, has_srt),
            (self.folder_button, job.status == DONE),
            (self.retry_button, job.status in (FAILED, CANCELLED) and not self.app.busy),
            (self.remove_button, job.status != RUNNING and not (self.app.busy and job.status == QUEUED)),
        ]
        for widget, _ in visible:
            widget.pack_forget()
        for widget, show in visible:
            if show:
                widget.pack(side="left", padx=2)
        self._draw_line()


if __name__ == "__main__":
    app = SubwayApp()
    app.mainloop()
