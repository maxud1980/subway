import json
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import read_srt, translated_path, write_srt
from app.transcription.engine import ParakeetEngine
from app.transcription.models import ModelManager, ModelInfo
from app.translation.translator import TranslationError, create_translator
from app.settings import load_api_key, save_api_key
from app.i18n import UI_LANGUAGES, load_ui_language, save_ui_language, translate as tr

APP_NAME = 'Subway'
APP_VERSION = '0.1.2'
REPOSITORY_URL = 'https://github.com/maxud1980/subway'
LATEST_RELEASE_URL = 'https://api.github.com/repos/maxud1980/subway/releases/latest'


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return base / relative_path

VIDEO_AUDIO_TYPES = [('Video and audio files', '*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.aac'), ('All files', '*.*')]
SRT_TYPES = [('SubRip subtitles', '*.srt'), ('All files', '*.*')]
LANGUAGES = {
    'Afrikaans': 'af', 'Akan': 'ak', 'Albanian': 'sq', 'Amharic': 'am',
    'Arabic': 'ar', 'Armenian': 'hy', 'Azerbaijani': 'az', 'Basque': 'eu',
    'Belarusian': 'be', 'Bengali': 'bn', 'Bulgarian': 'bg', 'Burmese (Myanmar)': 'my',
    'Catalan': 'ca', 'Chinese (Simplified)': 'zh-Hans', 'Chinese (Traditional)': 'zh-Hant',
    'Croatian': 'hr', 'Czech': 'cs', 'Danish': 'da', 'Dutch': 'nl',
    'English': 'en', 'Estonian': 'et', 'Filipino': 'fil', 'Finnish': 'fi',
    'French': 'fr', 'Galician': 'gl', 'Georgian': 'ka', 'German': 'de',
    'Greek': 'el', 'Gujarati': 'gu', 'Hausa': 'ha', 'Hebrew': 'he',
    'Hindi': 'hi', 'Hungarian': 'hu', 'Icelandic': 'is', 'Indonesian': 'id',
    'Italian': 'it', 'Japanese': 'ja', 'Javanese': 'jv', 'Kannada': 'kn',
    'Kazakh': 'kk', 'Khmer': 'km', 'Kinyarwanda': 'rw', 'Korean': 'ko',
    'Lao': 'lo', 'Latvian': 'lv', 'Lithuanian': 'lt', 'Macedonian': 'mk',
    'Malay': 'ms', 'Malayalam': 'ml', 'Marathi': 'mr', 'Mongolian': 'mn',
    'Nepali': 'ne', 'Norwegian': 'no', 'Persian': 'fa', 'Polish': 'pl',
    'Portuguese (Brazil)': 'pt-BR', 'Portuguese (Portugal)': 'pt-PT', 'Punjabi': 'pa',
    'Romanian': 'ro', 'Russian': 'ru', 'Serbian': 'sr', 'Sindhi': 'sd',
    'Sinhala': 'si', 'Slovak': 'sk', 'Slovenian': 'sl', 'Spanish': 'es',
    'Sundanese': 'su', 'Swahili': 'sw', 'Swedish': 'sv', 'Tamil': 'ta',
    'Telugu': 'te', 'Thai': 'th', 'Turkish': 'tr', 'Ukrainian': 'uk',
    'Urdu': 'ur', 'Uzbek': 'uz', 'Vietnamese': 'vi', 'Zulu': 'zu',
}

GEMINI_MODELS = ['gemini-3.5-flash-lite', 'gemini-3.8-flash']

class SubwayApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        try:
            self.iconbitmap(str(resource_path('assets/subway.ico')))
        except Exception:
            pass
        self.geometry('1180x850')
        self.minsize(1000, 740)
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')

        self.ui_language = load_ui_language()
        self.selected_file: Path | None = None
        self.current_srt: Path | None = None
        self.model_manager = ModelManager()
        self.models = self.model_manager.available_models()
        self.selected_model: ModelInfo = self.models[0]
        self._build_ui()
        self._refresh_model_status()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=320)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=28, pady=(22, 4), sticky="ew")
        ctk.CTkLabel(header, text="Subway", font=ctk.CTkFont(size=32, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text=tr("Local subtitle generator", self.ui_language), font=ctk.CTkFont(size=15), text_color="#9DB4CF").pack(anchor="w")

        workspace = ctk.CTkScrollableFrame(self, fg_color="transparent")
        workspace.grid(row=2, column=0, padx=(22, 10), pady=(12, 22), sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)

        model_frame = ctk.CTkFrame(workspace, corner_radius=14, border_width=1, border_color="#26364A")
        model_frame.grid(row=0, column=0, padx=4, pady=(0, 10), sticky="ew")
        model_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(model_frame, text=tr("Recognition model", self.ui_language), font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, padx=16, pady=(13, 7), sticky="w")
        self.model_menu = ctk.CTkOptionMenu(model_frame, values=[model.name for model in self.models], command=self._model_changed, height=38)
        self.model_menu.grid(row=1, column=0, padx=(16, 8), pady=(0, 8), sticky="ew")
        self.download_button = ctk.CTkButton(model_frame, text=tr("Download model", self.ui_language), command=self.download_model, height=38, width=155)
        self.download_button.grid(row=1, column=1, padx=(8, 16), pady=(0, 8))
        self.model_status = ctk.CTkLabel(model_frame, text="", anchor="w", justify="left", text_color="#9DB4CF")
        self.model_status.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 7), sticky="w")
        self.progress = ctk.CTkProgressBar(model_frame, height=8)
        self.progress.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 13), sticky="ew")
        self.progress.set(0)

        file_frame = ctk.CTkFrame(workspace, corner_radius=14, border_width=1, border_color="#26364A")
        file_frame.grid(row=1, column=0, padx=4, pady=5, sticky="ew")
        file_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(file_frame, text=tr("1. Create subtitles", self.ui_language), font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, columnspan=2, padx=18, pady=(16, 5), sticky="w")
        ctk.CTkLabel(file_frame, text=tr("Choose a local video or audio file.", self.ui_language), text_color="#9DB4CF").grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 10), sticky="w")
        self.file_label = ctk.CTkLabel(file_frame, text=tr("No media file selected", self.ui_language), wraplength=620, anchor="w", justify="left", fg_color="#172333", corner_radius=8, height=46)
        self.file_label.grid(row=2, column=0, padx=(18, 8), pady=5, sticky="ew")
        self.select_button = ctk.CTkButton(file_frame, text=tr("Select video or audio", self.ui_language), command=self.select_file, height=40, width=175)
        self.select_button.grid(row=2, column=1, padx=(8, 18), pady=5)
        ctk.CTkLabel(file_frame, text=tr("Supported formats: MP4, MKV, MOV, AVI, WebM, MP3, WAV and more.", self.ui_language), text_color="#8199B6", font=ctk.CTkFont(size=12)).grid(row=3, column=0, columnspan=2, padx=18, pady=(2, 10), sticky="w")
        self.generate_button = ctk.CTkButton(file_frame, text=tr("Create SRT", self.ui_language), command=self.create_srt, height=44, state="disabled", font=ctk.CTkFont(size=15, weight="bold"))
        self.generate_button.grid(row=4, column=0, columnspan=2, padx=18, pady=(3, 17), sticky="ew")

        translation_frame = ctk.CTkFrame(workspace, corner_radius=14, border_width=1, border_color="#26364A")
        translation_frame.grid(row=2, column=0, padx=4, pady=5, sticky="ew")
        translation_frame.grid_columnconfigure(1, weight=1)
        translation_frame.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(translation_frame, text=tr("2. Optional translation", self.ui_language), font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, columnspan=3, padx=18, pady=(16, 12), sticky="w")
        ctk.CTkLabel(translation_frame, text=tr("Target language", self.ui_language)).grid(row=1, column=0, padx=(18, 8), pady=6, sticky="w")
        self.language_menu = ctk.CTkComboBox(translation_frame, values=list(LANGUAGES), width=220)
        self.language_menu.set("Ukrainian")
        self.language_menu.grid(row=1, column=1, columnspan=2, padx=(8, 18), pady=6, sticky="ew")
        ctk.CTkLabel(translation_frame, text=tr("Model", self.ui_language)).grid(row=2, column=0, padx=(18, 8), pady=6, sticky="w")
        self.translation_model = ctk.CTkOptionMenu(translation_frame, values=GEMINI_MODELS, width=240, command=self._translation_model_changed)
        self.translation_model.grid(row=2, column=1, columnspan=2, padx=(8, 18), pady=6, sticky="ew")
        self.translation_model.set(GEMINI_MODELS[0])
        self.srt_label = ctk.CTkLabel(translation_frame, text=tr("No SRT selected", self.ui_language), wraplength=570, anchor="w", justify="left", fg_color="#172333", corner_radius=8, height=44)
        self.srt_label.grid(row=3, column=0, columnspan=2, padx=(18, 8), pady=(12, 6), sticky="ew")
        self.select_srt_button = ctk.CTkButton(translation_frame, text=tr("Select SRT", self.ui_language), command=self.select_srt, width=130, height=40)
        self.select_srt_button.grid(row=3, column=2, padx=(8, 18), pady=(12, 6))
        self.translate_button = ctk.CTkButton(translation_frame, text=tr("Translate SRT", self.ui_language), command=self.translate_srt, height=44, state="disabled", fg_color="#168A54", hover_color="#117343", font=ctk.CTkFont(size=15, weight="bold"))
        self.translate_button.grid(row=4, column=0, columnspan=3, padx=18, pady=(7, 17), sticky="ew")

        status_frame = ctk.CTkFrame(workspace, corner_radius=12, border_width=1, border_color="#26364A")
        status_frame.grid(row=3, column=0, padx=4, pady=(5, 0), sticky="ew")
        ctk.CTkLabel(status_frame, text="ⓘ  " + tr("Subway works locally. Your video never leaves your computer.", self.ui_language), text_color="#9DB4CF", wraplength=650, justify="left").pack(anchor="w", padx=15, pady=12)

        settings = ctk.CTkFrame(self, corner_radius=14, border_width=1, border_color="#26364A")
        settings.grid(row=2, column=1, padx=(10, 22), pady=(12, 22), sticky="nsew")
        settings.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(settings, text="⚙  " + tr("Settings", self.ui_language), font=ctk.CTkFont(size=21, weight="bold")).grid(row=0, column=0, padx=18, pady=(18, 14), sticky="w")
        ctk.CTkFrame(settings, height=2, fg_color="#26364A").grid(row=1, column=0, padx=18, sticky="ew")
        ctk.CTkLabel(settings, text="◉  " + tr("About the author", self.ui_language), font=ctk.CTkFont(size=15, weight="bold")).grid(row=2, column=0, padx=18, pady=(18, 5), sticky="w")
        ctk.CTkLabel(settings, text=f"{tr('Created by', self.ui_language)} Maxim Kapinus", text_color="#D7E4F5").grid(row=3, column=0, padx=18, pady=3, sticky="w")
        ctk.CTkLabel(settings, text=tr("Built for creators. No servers. No limits.", self.ui_language), text_color="#9DB4CF", wraplength=270, justify="left").grid(row=4, column=0, padx=18, pady=(3, 12), sticky="w")
        ctk.CTkButton(settings, text=tr("GitHub repository", self.ui_language), command=lambda: webbrowser.open(REPOSITORY_URL), height=32, fg_color="transparent", border_width=1).grid(row=5, column=0, padx=18, pady=(0, 14), sticky="ew")
        ctk.CTkFrame(settings, height=2, fg_color="#26364A").grid(row=6, column=0, padx=18, sticky="ew")
        ctk.CTkLabel(settings, text="🔑  " + tr("API key (encrypted)", self.ui_language), font=ctk.CTkFont(size=15, weight="bold")).grid(row=7, column=0, padx=18, pady=(16, 5), sticky="w")
        self.api_key = ctk.CTkEntry(settings, show="•", placeholder_text="Gemini API key")
        self.api_key.grid(row=8, column=0, padx=18, pady=5, sticky="ew")
        self.api_key.bind("<FocusOut>", self._save_api_key)
        try:
            saved_key = load_api_key()
            if saved_key:
                self.api_key.insert(0, saved_key)
        except Exception as exc:
            self.log(f"WARNING: Could not load saved API key: {exc}")
        ctk.CTkLabel(settings, text=tr("Stored securely on this Windows account.", self.ui_language), text_color="#8199B6", wraplength=270, justify="left", font=ctk.CTkFont(size=12)).grid(row=9, column=0, padx=18, pady=(0, 14), sticky="w")
        ctk.CTkFrame(settings, height=2, fg_color="#26364A").grid(row=10, column=0, padx=18, sticky="ew")
        ctk.CTkLabel(settings, text="◎  " + tr("Interface language", self.ui_language), font=ctk.CTkFont(size=15, weight="bold")).grid(row=11, column=0, padx=18, pady=(16, 5), sticky="w")
        self.ui_language_menu = ctk.CTkOptionMenu(settings, values=list(UI_LANGUAGES.keys()), command=self._change_ui_language, height=36)
        self.ui_language_menu.set(self.ui_language)
        self.ui_language_menu.grid(row=12, column=0, padx=18, pady=(0, 15), sticky="ew")
        ctk.CTkFrame(settings, height=2, fg_color="#26364A").grid(row=13, column=0, padx=18, sticky="ew")
        ctk.CTkLabel(settings, text="↻  " + tr("Check for updates", self.ui_language), font=ctk.CTkFont(size=15, weight="bold")).grid(row=14, column=0, padx=18, pady=(16, 4), sticky="w")
        self.update_status = ctk.CTkLabel(settings, text=f"{tr('Current version', self.ui_language)}: {APP_VERSION}", text_color="#9DB4CF", wraplength=270, justify="left")
        self.update_status.grid(row=15, column=0, padx=18, pady=(0, 7), sticky="w")
        self.update_button = ctk.CTkButton(settings, text=tr("Check for updates", self.ui_language), command=self.check_for_updates, height=40, fg_color="transparent", border_width=1)
        self.update_button.grid(row=16, column=0, padx=18, pady=(0, 14), sticky="ew")
        ctk.CTkLabel(settings, text=f"Subway v{APP_VERSION}", text_color="#8199B6", font=ctk.CTkFont(size=12)).grid(row=17, column=0, padx=18, pady=(10, 15), sticky="w")

        self.status = ctk.CTkTextbox(workspace, height=90, fg_color="#0D1520", text_color="#AFC4DE")
        self.status.grid(row=4, column=0, padx=4, pady=(10, 2), sticky="ew")
        self.status.insert("1.0", tr("Ready. Select a local media file to begin.", self.ui_language) + "\\n")
        self.status.configure(state="disabled")

    def log(self, text: str):
        self.status.configure(state='normal')
        self.status.insert('end', text + '\n')
        self.status.see('end')
        self.status.configure(state='disabled')


    def _change_ui_language(self, language: str):
        if language not in UI_LANGUAGES or language == self.ui_language:
            return
        self.ui_language = language
        save_ui_language(language)
        selected_model = self.selected_model
        selected_file = self.selected_file
        current_srt = self.current_srt
        target_language = self.language_menu.get() if hasattr(self, "language_menu") else "Ukrainian"
        translation_model = self.translation_model.get() if hasattr(self, "translation_model") else GEMINI_MODELS[0]
        api_key = self.api_key.get() if hasattr(self, "api_key") else ""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
        self.selected_model = selected_model
        self.model_menu.set(selected_model.name)
        self.selected_file = selected_file
        self.current_srt = current_srt
        self.language_menu.set(target_language)
        self.translation_model.set(translation_model)
        if api_key:
            self.api_key.delete(0, "end")
            self.api_key.insert(0, api_key)
        if selected_file:
            self.file_label.configure(text=str(selected_file))
        if current_srt:
            self._set_srt(current_srt)
        self._refresh_model_status()

    def check_for_updates(self, dialog=None):
        if hasattr(self, 'update_button') and self.update_button.winfo_exists():
            self.update_button.configure(state='disabled')
            self.update_status.configure(text=tr('Checking for updates…', self.ui_language))
        threading.Thread(target=self._check_updates_worker, args=(dialog,), daemon=True).start()

    def _check_updates_worker(self, dialog=None):
        lang = self.ui_language
        try:
            request = urllib.request.Request(
                LATEST_RELEASE_URL,
                headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Subway-Update-Checker'})
            with urllib.request.urlopen(request, timeout=10) as response:
                release = json.loads(response.read().decode('utf-8'))
            tag = str(release.get('tag_name', '')).strip()
            latest = tag[1:] if tag.lower().startswith('v') else tag
            release_url = release.get('html_url', REPOSITORY_URL)
            if not latest:
                raise ValueError('Release tag missing')
            if latest == APP_VERSION:
                text = f'{tr("Current version", lang)}: {APP_VERSION} — {tr("You are using the latest version.", lang)}'
                self.after(0, self._update_check_done, text, None, dialog)
            else:
                text = f'{tr("Current version", lang)}: {APP_VERSION} • {tr("Latest version", lang)}: {tag}'
                self.after(0, self._update_check_done, text, (tr('Update available', lang), f'{tr("Latest version", lang)}: {tag}\\n\\n{release_url}', release_url), dialog)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                try:
                    tags_request = urllib.request.Request(
                        'https://api.github.com/repos/maxud1980/subway/tags?per_page=1',
                        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Subway-Update-Checker'})
                    with urllib.request.urlopen(tags_request, timeout=10) as response:
                        tags = json.loads(response.read().decode('utf-8'))
                    if tags:
                        tag = str(tags[0].get('name', '')).strip()
                        latest = tag[1:] if tag.lower().startswith('v') else tag
                        release_url = f'{REPOSITORY_URL}/releases/tag/{tag}'
                        if latest and latest != APP_VERSION:
                            text = f'{tr("Current version", lang)}: {APP_VERSION} • {tr("Latest version", lang)}: {tag}'
                            info = (tr('Update available', lang), f'{tr("Latest version", lang)}: {tag}\\n\\n{release_url}', release_url)
                            self.after(0, self._update_check_done, text, info, dialog)
                        else:
                            text = f'{tr("Current version", lang)}: {APP_VERSION} — {tr("You are using the latest version.", lang)}'
                            self.after(0, self._update_check_done, text, None, dialog)
                    else:
                        text = f'{tr("Current version", lang)}: {APP_VERSION} — {tr("No published releases were found.", lang)}'
                        self.after(0, self._update_check_done, text, None, dialog)
                except Exception:
                    text = f'{tr("Current version", lang)}: {APP_VERSION} — {tr("No published releases were found.", lang)}'
                    self.after(0, self._update_check_done, text, None, dialog)
            else:
                self.after(0, self._update_check_failed, tr('Could not check for updates. Check your internet connection and try again.', lang), dialog)
        except Exception:
            self.after(0, self._update_check_failed, tr('Could not check for updates. Check your internet connection and try again.', lang), dialog)

    def _update_check_done(self, status_text, update_info, dialog=None):
        if hasattr(self, 'update_status') and self.update_status.winfo_exists():
            self.update_status.configure(text=status_text)
        if hasattr(self, 'update_button') and self.update_button.winfo_exists():
            self.update_button.configure(state='normal')
        if update_info:
            title, message, url = update_info
            if messagebox.askyesno(title, message + '\\n\\n' + tr('Open the release page?', self.ui_language), parent=dialog or self):
                webbrowser.open(url)

    def _update_check_failed(self, message, dialog=None):
        if hasattr(self, 'update_button') and self.update_button.winfo_exists():
            self.update_button.configure(state='normal')
        if hasattr(self, 'update_status') and self.update_status.winfo_exists():
            self.update_status.configure(text=tr('Could not check for updates. Check your internet connection and try again.', self.ui_language))
        messagebox.showwarning(APP_NAME, message, parent=dialog or self)

    def _model_changed(self, name: str):
        self.selected_model = next(model for model in self.models if model.name == name)
        self._refresh_model_status()

    def _provider_changed(self, provider: str):
        models = GEMINI_MODELS
        self.translation_model.configure(values=models)
        self.translation_model.set(models[0])

    def _translation_model_changed(self, model: str):
        self.log(f'Translation model: {model}')

    def _save_api_key(self, _event=None):
        try:
            save_api_key(self.api_key.get().strip())
        except Exception as exc:
            self.log(f'WARNING: Could not securely save API key: {exc}')

    def _refresh_model_status(self):
        model = self.selected_model
        if self.model_manager.is_downloaded(model):
            self.model_status.configure(text=f'✓ Ready • {model.size_mb} MB • {model.languages}')
            self.download_button.configure(text='Model ready', state='disabled')
            self.progress.set(1)
        else:
            self.model_status.configure(text=f'Not downloaded • {model.size_mb} MB • {model.languages}')
            self.download_button.configure(text=tr('Download model', self.ui_language), state='normal')
            self.progress.set(0)
        self._update_generate_state()

    def download_model(self):
        model = self.selected_model
        self.download_button.configure(state='disabled')
        self.model_menu.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.generate_button.configure(state='disabled')
        self.progress.set(0)
        self.log(f'Downloading {model.name}...')
        threading.Thread(target=self._download_worker, args=(model,), daemon=True).start()

    def _download_worker(self, model: ModelInfo):
        try:
            path = self.model_manager.download(model, progress=lambda received, total: self.after(0, self._download_progress, received, total))
            self.after(0, self._download_done, path)
        except Exception as exc:
            self.after(0, self._download_failed, exc)

    def _download_progress(self, received: int, total: int):
        if total > 0:
            self.progress.set(min(received / total, 1))
            self.model_status.configure(text=f'Downloading… {received / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB')

    def _download_done(self, path: Path):
        self.log(f'Model downloaded: {path}')
        self.model_menu.configure(state='normal')
        self.select_button.configure(state='normal')
        self._refresh_model_status()

    def _download_failed(self, exc: Exception):
        self.log(f'ERROR: model download failed: {exc}')
        self.model_menu.configure(state='normal')
        self.select_button.configure(state='normal')
        self._refresh_model_status()
        messagebox.showerror(APP_NAME, f'Model download failed.\n\n{exc}')

    def select_file(self):
        filename = filedialog.askopenfilename(title=tr('Select video or audio', self.ui_language), filetypes=VIDEO_AUDIO_TYPES)
        if not filename:
            return
        self.selected_file = Path(filename)
        self.file_label.configure(text=str(self.selected_file))
        self.current_srt = self.selected_file.with_suffix('.srt')
        if self.current_srt.exists():
            self._set_srt(self.current_srt)
        self._update_generate_state()
        self.log(f'Selected: {self.selected_file.name}')

    def select_srt(self):
        filename = filedialog.askopenfilename(title=tr('Select SRT', self.ui_language), filetypes=SRT_TYPES)
        if filename:
            self._set_srt(Path(filename))

    def _set_srt(self, path: Path):
        self.current_srt = path
        self.srt_label.configure(text=str(path))
        self.translate_button.configure(state='normal')

    def _update_generate_state(self):
        ready = self.selected_file is not None and self.model_manager.is_downloaded(self.selected_model)
        self.generate_button.configure(state='normal' if ready else 'disabled')

    def create_srt(self):
        if not self.selected_file:
            messagebox.showwarning(APP_NAME, tr('Select a video or audio file first.', self.ui_language))
            return
        if not self.model_manager.is_downloaded(self.selected_model):
            messagebox.showwarning(APP_NAME, tr('Download the selected recognition model first.', self.ui_language))
            return
        self.generate_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.model_menu.configure(state='disabled')
        self.download_button.configure(state='disabled')
        self.log(f'Loading {self.selected_model.name}...')
        threading.Thread(target=self._transcribe_worker, args=(self.selected_file,), daemon=True).start()

    def _transcribe_worker(self, media_path: Path):
        try:
            engine = ParakeetEngine(runtime_dir=self.model_manager.runtime_dir, model_name=self.selected_model.filename)
            segments = list(engine.transcribe(media_path))
            subtitles = segments_to_subtitles(segments)
            output_path = media_path.with_suffix('.srt')
            write_srt(subtitles, output_path)
            self.after(0, self._transcription_done, output_path, len(subtitles))
        except Exception as exc:
            self.after(0, self._transcription_failed, exc)

    def _transcription_done(self, output_path: Path, count: int):
        self.current_srt = output_path
        self._set_srt(output_path)
        self.log(f'Done: {count} subtitles')
        self.log(f'Saved: {output_path}')
        self._restore_controls()
        messagebox.showinfo(APP_NAME, f'SRT created successfully.\n\n{output_path}')

    def _transcription_failed(self, exc: Exception):
        self.log(f'ERROR: {exc}')
        self._restore_controls()
        messagebox.showerror(APP_NAME, str(exc))

    def _restore_controls(self):
        self.model_menu.configure(state='normal')
        self.select_button.configure(state='normal')
        self._refresh_model_status()

    def translate_srt(self):
        if not self.current_srt:
            messagebox.showwarning(APP_NAME, 'Select or create an SRT file first.')
            return
        api_key = self.api_key.get().strip()
        if not api_key:
            messagebox.showwarning(APP_NAME, tr('Enter an API key first.', self.ui_language))
            return
        try:
            save_api_key(api_key)
        except Exception as exc:
            self.log(f'WARNING: API key could not be saved: {exc}')
        provider = self.provider_menu.get()
        model = self.translation_model.get()
        language = self.language_menu.get()
        self.translate_button.configure(state='disabled')
        self.select_srt_button.configure(state='disabled')
        self.log(f'Translating {self.current_srt.name} → {language} using {provider}...')
        threading.Thread(target=self._translate_worker, args=(self.current_srt, provider, api_key, model, language), daemon=True).start()

    def _translate_worker(self, source: Path, provider: str, api_key: str, model: str, language: str):
        try:
            subtitles = read_srt(source)
            if not subtitles:
                raise TranslationError('The selected SRT contains no subtitles.')
            translator = create_translator(provider, api_key, model, language)
            translated = translator.translate([subtitle.text for subtitle in subtitles])
            result = [type(subtitle)(subtitle.start, subtitle.end, text) for subtitle, text in zip(subtitles, translated)]
            code = LANGUAGES[language]
            output = translated_path(source, code)
            write_srt(result, output)
            self.after(0, self._translation_done, output, len(result))
        except Exception as exc:
            self.after(0, self._translation_failed, exc)

    def _translation_done(self, output: Path, count: int):
        self._set_srt(output)
        self.log(f'Translation done: {count} subtitles')
        self.log(f'Saved: {output}')
        self.translate_button.configure(state='normal')
        self.select_srt_button.configure(state='normal')
        messagebox.showinfo(APP_NAME, f'Translated SRT created successfully.\n\n{output}')

    def _translation_failed(self, exc: Exception):
        self.log(f'ERROR: translation failed: {exc}')
        self.translate_button.configure(state='normal')
        self.select_srt_button.configure(state='normal')
        messagebox.showerror(APP_NAME, str(exc))

if __name__ == '__main__':
    app = SubwayApp()
    app.mainloop()
