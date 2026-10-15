from __future__ import annotations

import threading
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app import theme as T
from app.config import AppSettings
from app.i18n import GLOSSARY_HINT, UI_LANGUAGES
from app.settings import load_api_key, save_api_key
from app.transcription.engine import RuntimeSelector

MENU = dict(fg_color=T.RAISED, button_color=T.LINE, button_hover_color=T.ACCENT)

DEVICE_LABELS = {
    "auto": "Automatic (best available)",
    "cuda": "NVIDIA graphics card (CUDA)",
    "vulkan": "Other graphics card (Vulkan)",
    "cpu": "Processor only (slow)",
}


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.t = app.t
        self.s: AppSettings = app.settings
        self.title(self.t("Settings"))
        self.geometry("620x640")
        self.minsize(560, 560)
        self.configure(fg_color=T.BG)
        self.transient(app)
        self.after(150, self.lift)
        self.protocol("WM_DELETE_WINDOW", self.close)

        tabs = ctk.CTkTabview(self, fg_color=T.SURFACE, segmented_button_selected_color=T.ACCENT,
                              segmented_button_selected_hover_color=T.ACCENT_HOVER)
        tabs.pack(fill="both", expand=True, padx=16, pady=(8, 8))
        self._general(tabs.add(self.t("General")))
        self._subtitles(tabs.add(self.t("Subtitles")))
        self._glossary(tabs.add(self.t("Glossary")))
        self._about(tabs.add(self.t("About")))

        ctk.CTkButton(self, text=self.t("Close"), width=120, command=self.close, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER).pack(anchor="e", padx=16, pady=(0, 14))

    # -- helpers --------------------------------------------------------------
    def _label(self, parent, text: str, row: int, hint: str | None = None) -> None:
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT).grid(
            row=row, column=0, columnspan=3, padx=12, pady=(14, 0), sticky="w")
        if hint:
            ctk.CTkLabel(parent, text=hint, text_color=T.MUTED, font=ctk.CTkFont(size=12), wraplength=520,
                         justify="left").grid(row=row + 1, column=0, columnspan=3, padx=12, sticky="w")

    # -- general --------------------------------------------------------------
    def _general(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        self._label(tab, self.t("Interface language"), 0)
        menu = ctk.CTkOptionMenu(tab, values=list(UI_LANGUAGES), command=self._language, **MENU)
        menu.set(self.s.ui_language)
        menu.grid(row=2, column=0, columnspan=3, padx=12, pady=(6, 0), sticky="w")

        self._label(tab, self.t("Gemini API key"), 3, self.t("Stored encrypted for this Windows account. Needed only for translation."))
        self.key_entry = ctk.CTkEntry(tab, show="•", placeholder_text="AIza…")
        self.key_entry.grid(row=5, column=0, columnspan=2, padx=(12, 6), pady=(6, 0), sticky="ew")
        try:
            key = load_api_key()
        except Exception:
            key = ""
        if key:
            self.key_entry.insert(0, key)
        self.key_entry.bind("<FocusOut>", lambda _e: self._save_key())
        self.show_key = ctk.CTkButton(tab, text=self.t("Show"), width=70, fg_color=T.RAISED, hover_color=T.LINE,
                                      command=self._toggle_key)
        self.show_key.grid(row=5, column=2, padx=(0, 12), pady=(6, 0))
        ctk.CTkButton(tab, text=self.t("Get a key"), width=10, fg_color="transparent", text_color=T.ACCENT,
                      hover_color=T.RAISED, command=lambda: webbrowser.open("https://aistudio.google.com/apikey")).grid(
            row=6, column=0, padx=6, sticky="w")

        self._label(tab, self.t("Where to save results"), 7)
        self.folder_label = ctk.CTkLabel(tab, text="", text_color=T.MUTED, wraplength=360, justify="left", anchor="w")
        self.folder_label.grid(row=9, column=0, padx=12, pady=(4, 0), sticky="ew")
        ctk.CTkButton(tab, text=self.t("Choose…"), width=90, fg_color=T.RAISED, hover_color=T.LINE,
                      command=self._choose_folder).grid(row=9, column=1, padx=4, pady=(4, 0))
        ctk.CTkButton(tab, text=self.t("Reset"), width=70, fg_color="transparent", border_width=1, border_color=T.LINE,
                      hover_color=T.RAISED, command=self._reset_folder).grid(row=9, column=2, padx=(0, 12), pady=(4, 0))
        self._show_folder()
        self.overwrite = ctk.BooleanVar(value=self.s.overwrite)
        ctk.CTkCheckBox(tab, text=self.t("Overwrite existing files (otherwise a numbered copy is created)"),
                        variable=self.overwrite, command=self._overwrite, fg_color=T.ACCENT).grid(
            row=10, column=0, columnspan=3, padx=12, pady=(10, 0), sticky="w")

        self._label(tab, self.t("Recognition device"), 11)
        labels = {key: self.t(value) for key, value in DEVICE_LABELS.items()}
        self.device_labels = labels
        device = ctk.CTkOptionMenu(tab, values=list(labels.values()), command=self._device, width=300, **MENU)
        device.set(labels.get(self.s.device, labels["auto"]))
        device.grid(row=13, column=0, columnspan=3, padx=12, pady=(6, 0), sticky="w")
        self.devices_label = ctk.CTkLabel(tab, text=self.t("Checking devices…"), text_color=T.MUTED, font=ctk.CTkFont(size=12))
        self.devices_label.grid(row=14, column=0, columnspan=3, padx=12, sticky="w")
        threading.Thread(target=self._detect_devices, daemon=True).start()

    def _language(self, value: str) -> None:
        self._save_key()
        self.app.apply_ui_language(value)

    def _toggle_key(self) -> None:
        hidden = self.key_entry.cget("show") == "•"
        self.key_entry.configure(show="" if hidden else "•")
        self.show_key.configure(text=self.t("Hide") if hidden else self.t("Show"))

    def _save_key(self) -> None:
        if not hasattr(self, "key_entry") or not self.key_entry.winfo_exists():
            return
        try:
            save_api_key(self.key_entry.get().strip())
        except Exception as exc:  # noqa: BLE001
            self.app.log(f"WARNING: could not save the API key securely: {exc}")

    def _show_folder(self) -> None:
        self.folder_label.configure(text=self.s.output_dir or self.t("Next to each source file"))

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self, title=self.t("Where to save results"))
        if folder:
            self.s.output_dir = folder
            self.app.save()
            self._show_folder()

    def _reset_folder(self) -> None:
        self.s.output_dir = ""
        self.app.save()
        self._show_folder()

    def _overwrite(self) -> None:
        self.s.overwrite = bool(self.overwrite.get())
        self.app.save()

    def _device(self, label: str) -> None:
        self.s.device = next(key for key, value in self.device_labels.items() if value == label)
        self.app.save()

    def _detect_devices(self) -> None:
        selector = RuntimeSelector(self.app.model_manager.runtime_dir)
        found = []
        for _variant, binary in selector.installed():
            for kind in selector.devices(binary) or []:
                if kind not in found:
                    found.append(kind)
        names = {"cuda": "NVIDIA CUDA", "vulkan": "Vulkan", "cpu": "CPU", "metal": "Metal"}
        text = (self.t("Available") + ": " + ", ".join(names.get(k, k) for k in found)) if found else self.t("No working runtime found.")
        try:
            self.after(0, lambda: self.devices_label.winfo_exists() and self.devices_label.configure(text=text))
        except RuntimeError:
            pass

    # -- subtitles ------------------------------------------------------------
    def _subtitles(self, tab) -> None:
        tab.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(tab, text=self.t("These rules decide how speech is cut into subtitles and how long each one stays on screen."),
                     text_color=T.MUTED, wraplength=520, justify="left").grid(row=0, column=0, columnspan=3, padx=12, pady=(10, 6), sticky="w")
        self.sliders = {}
        specs = [
            ("max_chars_per_line", self.t("Characters per line"), 20, 60, 40, int),
            ("max_lines", self.t("Lines per subtitle"), 1, 3, 2, int),
            ("min_duration", self.t("Minimum time on screen, s"), 0.5, 3.0, 25, float),
            ("max_duration", self.t("Maximum time on screen, s"), 3.0, 12.0, 18, float),
            ("max_cps", self.t("Reading speed, characters per second"), 10, 30, 20, float),
        ]
        for row, (key, label, low, high, steps, kind) in enumerate(specs, start=1):
            ctk.CTkLabel(tab, text=label, text_color=T.TEXT).grid(row=row, column=0, padx=12, pady=8, sticky="w")
            value_label = ctk.CTkLabel(tab, text="", width=48, text_color=T.TEXT)
            value_label.grid(row=row, column=2, padx=(4, 12))
            slider = ctk.CTkSlider(tab, from_=low, to=high, number_of_steps=steps, button_color=T.ACCENT,
                                   progress_color=T.ACCENT,
                                   command=lambda v, k=key, lab=value_label, c=kind: self._slider(k, v, lab, c))
            slider.set(getattr(self.s, key))
            slider.grid(row=row, column=1, padx=4, sticky="ew")
            self.sliders[key] = (slider, value_label, kind)
            self._slider(key, getattr(self.s, key), value_label, kind, save=False)
        ctk.CTkButton(tab, text=self.t("Restore defaults"), fg_color="transparent", border_width=1, border_color=T.LINE,
                      hover_color=T.RAISED, command=self._defaults).grid(row=7, column=0, padx=12, pady=(16, 0), sticky="w")

    def _slider(self, key, value, label, kind, save: bool = True) -> None:
        value = round(float(value)) if kind is int else round(float(value), 1)
        setattr(self.s, key, value)
        label.configure(text=str(value))
        if save:
            self.app.save()

    def _defaults(self) -> None:
        default = AppSettings()
        for key, (slider, label, kind) in self.sliders.items():
            slider.set(getattr(default, key))
            self._slider(key, getattr(default, key), label, kind)

    # -- glossary -------------------------------------------------------------
    def _glossary(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(tab, text=self.t(GLOSSARY_HINT),
                     text_color=T.MUTED, wraplength=520, justify="left").grid(row=0, column=0, padx=12, pady=(10, 6), sticky="w")
        self.glossary = ctk.CTkTextbox(tab, fg_color=T.BG, border_width=1, border_color=T.LINE)
        self.glossary.grid(row=1, column=0, padx=12, sticky="nsew")
        self.glossary.insert("1.0", self.s.glossary)
        self.glossary.bind("<FocusOut>", lambda _e: self._save_glossary())
        self.boost = ctk.BooleanVar(value=self.s.boost_glossary_in_recognition)
        ctk.CTkCheckBox(tab, text=self.t("Also use these terms to improve speech recognition"), variable=self.boost,
                        command=self._save_glossary, fg_color=T.ACCENT).grid(row=2, column=0, padx=12, pady=(10, 4), sticky="w")

    def _save_glossary(self) -> None:
        if hasattr(self, "glossary") and self.glossary.winfo_exists():
            self.s.glossary = self.glossary.get("1.0", "end").strip()
            self.s.boost_glossary_in_recognition = bool(self.boost.get())
            self.app.save()

    # -- about ----------------------------------------------------------------
    def _about(self, tab) -> None:
        from app.main import APP_VERSION, REPOSITORY_URL

        ctk.CTkLabel(tab, text=f"Subway {APP_VERSION}", font=ctk.CTkFont(size=20, weight="bold"), text_color=T.TEXT).pack(anchor="w", padx=12, pady=(14, 2))
        ctk.CTkLabel(tab, text=f"{self.t('Created by')} Maxim Kapinus", text_color=T.TEXT).pack(anchor="w", padx=12)
        ctk.CTkLabel(tab, text=self.t("Speech recognition runs on this computer. Only subtitle text is sent to Gemini, and only when translation is on."),
                     text_color=T.MUTED, wraplength=520, justify="left").pack(anchor="w", padx=12, pady=(8, 12))
        ctk.CTkButton(tab, text=self.t("GitHub repository"), fg_color="transparent", border_width=1, border_color=T.LINE,
                      hover_color=T.RAISED, command=lambda: webbrowser.open(REPOSITORY_URL)).pack(anchor="w", padx=12)
        self.update_status = ctk.CTkLabel(tab, text="", text_color=T.MUTED, wraplength=520, justify="left")
        self.update_button = ctk.CTkButton(tab, text=self.t("Check for updates"), command=self._check_updates,
                                           fg_color=T.RAISED, hover_color=T.LINE)
        self.update_button.pack(anchor="w", padx=12, pady=(18, 4))
        self.update_status.pack(anchor="w", padx=12)

    def _check_updates(self) -> None:
        self.update_button.configure(state="disabled")
        self.update_status.configure(text=self.t("Checking for updates…"))
        self.app.check_for_updates(callback=self._update_done)

    def _update_done(self, tag: str, newer: bool, error: str | None) -> None:
        if not self.winfo_exists():
            return
        self.update_button.configure(state="normal")
        if error:
            text = self.t("Could not check for updates. Check your internet connection and try again.")
        elif newer:
            text = f"{self.t('Update available')}: {tag}"
            if messagebox.askyesno("Subway", f"{text}\n\n{self.t('Open the release page?')}", parent=self):
                self.app._open_update()
        else:
            text = self.t("You are using the latest version.")
        self.update_status.configure(text=text)

    def close(self) -> None:
        self._save_key()
        self._save_glossary()
        self.app.settings_window = None
        self.destroy()
