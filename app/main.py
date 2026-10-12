import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import read_srt, translated_path, write_srt
from app.transcription.engine import ParakeetEngine
from app.transcription.models import ModelManager, ModelInfo
from app.translation.translator import TranslationError, create_translator
from app.settings import load_api_key, save_api_key

APP_NAME = 'Subway'

VIDEO_AUDIO_TYPES = [('Video and audio files', '*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.aac'), ('All files', '*.*')]
SRT_TYPES = [('SubRip subtitles', '*.srt'), ('All files', '*.*')]
LANGUAGES = {
    'Afrikaans': 'af', 'Akan': 'ak', 'Albanian': 'sq', 'Amharic': 'am', 'Assamese': 'as',
    'Arabic': 'ar', 'Armenian': 'hy', 'Azerbaijani': 'az', 'Basque': 'eu',
    'Belarusian': 'be', 'Bengali': 'bn', 'Bosnian': 'bs', 'Bulgarian': 'bg', 'Burmese (Myanmar)': 'my',
    'Catalan': 'ca', 'Cebuano': 'ceb', 'Chinese (Simplified)': 'zh-Hans', 'Chinese (Traditional)': 'zh-Hant',
    'Croatian': 'hr', 'Czech': 'cs', 'Danish': 'da', 'Dutch': 'nl',
    'English': 'en', 'Estonian': 'et', 'Filipino': 'fil', 'Finnish': 'fi',
    'French': 'fr', 'Galician': 'gl', 'Georgian': 'ka', 'German': 'de',
    'Greek': 'el', 'Gujarati': 'gu', 'Hausa': 'ha', 'Hebrew': 'he',
    'Hindi': 'hi', 'Hungarian': 'hu', 'Icelandic': 'is', 'Indonesian': 'id',
    'Italian': 'it', 'Japanese': 'ja', 'Javanese': 'jv', 'Kannada': 'kn',
    'Kazakh': 'kk', 'Khmer': 'km', 'Kinyarwanda': 'rw', 'Korean': 'ko',
    'Lao': 'lo', 'Latvian': 'lv', 'Lithuanian': 'lt', 'Macedonian': 'mk', 'Maori': 'mi', 'Maltese': 'mt',
    'Malay': 'ms', 'Malayalam': 'ml', 'Marathi': 'mr', 'Mongolian': 'mn',
    'Nepali': 'ne', 'Norwegian': 'no', 'Odia': 'or', 'Oromo': 'om', 'Pashto': 'ps', 'Persian': 'fa', 'Polish': 'pl',
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
        self.geometry('820x790')
        self.minsize(740, 700)
        ctk.set_appearance_mode('System')
        ctk.set_default_color_theme('blue')

        self.selected_file: Path | None = None
        self.current_srt: Path | None = None
        self.model_manager = ModelManager()
        self.models = self.model_manager.available_models()
        self.selected_model: ModelInfo = self.models[0]
        self._build_ui()
        self._refresh_model_status()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text='Subway', font=ctk.CTkFont(size=32, weight='bold')).grid(row=0, column=0, padx=30, pady=(20, 2))
        ctk.CTkLabel(self, text='Local subtitle generator', font=ctk.CTkFont(size=16)).grid(row=1, column=0, padx=30, pady=(0, 10))

        content = ctk.CTkScrollableFrame(self)
        content.grid(row=2, column=0, padx=30, pady=8, sticky='nsew')
        content.grid_columnconfigure(0, weight=1)

        model_frame = ctk.CTkFrame(content)
        model_frame.grid(row=0, column=0, padx=5, pady=5, sticky='ew')
        model_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(model_frame, text='Recognition model', font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 6), sticky='w')
        self.model_menu = ctk.CTkOptionMenu(model_frame, values=[model.name for model in self.models], command=self._model_changed, height=38)
        self.model_menu.grid(row=1, column=0, padx=(15, 8), pady=(0, 8), sticky='ew')
        self.download_button = ctk.CTkButton(model_frame, text='Download model', command=self.download_model, height=38, width=155)
        self.download_button.grid(row=1, column=1, padx=(8, 15), pady=(0, 8))
        self.model_status = ctk.CTkLabel(model_frame, text='', anchor='w', justify='left')
        self.model_status.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 8), sticky='w')
        self.progress = ctk.CTkProgressBar(model_frame, height=10)
        self.progress.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 12), sticky='ew')
        self.progress.set(0)

        file_frame = ctk.CTkFrame(content)
        file_frame.grid(row=1, column=0, padx=5, pady=5, sticky='ew')
        file_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(file_frame, text='1. Create subtitles', font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 6), sticky='w')
        self.file_label = ctk.CTkLabel(file_frame, text='No media file selected', wraplength=650, anchor='w', justify='left')
        self.file_label.grid(row=1, column=0, padx=15, pady=8, sticky='ew')
        self.select_button = ctk.CTkButton(file_frame, text='Select video or audio', command=self.select_file, height=40)
        self.select_button.grid(row=2, column=0, padx=15, pady=(0, 12), sticky='w')
        self.generate_button = ctk.CTkButton(file_frame, text='Create SRT', command=self.create_srt, height=40, state='disabled')
        self.generate_button.grid(row=2, column=1, padx=15, pady=(0, 12), sticky='e')

        translation_frame = ctk.CTkFrame(content)
        translation_frame.grid(row=2, column=0, padx=5, pady=5, sticky='ew')
        translation_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(translation_frame, text='2. Optional translation', font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, columnspan=3, padx=15, pady=(12, 8), sticky='w')
        ctk.CTkLabel(translation_frame, text='Provider').grid(row=1, column=0, padx=(15, 8), pady=5, sticky='w')
        self.provider_menu = ctk.CTkOptionMenu(translation_frame, values=['Gemini'], command=self._provider_changed, width=130)
        self.provider_menu.grid(row=1, column=1, padx=8, pady=5, sticky='w')
        ctk.CTkLabel(translation_frame, text='Target language').grid(row=2, column=0, padx=(15, 8), pady=5, sticky='w')
        self.language_menu = ctk.CTkOptionMenu(translation_frame, values=list(LANGUAGES), width=180)
        self.language_menu.set('Ukrainian')
        self.language_menu.grid(row=2, column=1, padx=8, pady=5, sticky='w')
        ctk.CTkLabel(translation_frame, text='Model').grid(row=3, column=0, padx=(15, 8), pady=5, sticky='w')
        self.translation_model = ctk.CTkOptionMenu(
            translation_frame,
            values=GEMINI_MODELS,
            width=260,
            command=self._translation_model_changed,
        )
        self.translation_model.grid(row=3, column=1, padx=8, pady=5, sticky='ew')
        self.translation_model.set(GEMINI_MODELS[0])
        ctk.CTkLabel(translation_frame, text='API key (encrypted)').grid(row=4, column=0, padx=(15, 8), pady=5, sticky='w')
        self.api_key = ctk.CTkEntry(translation_frame, show='•')
        self.api_key.grid(row=4, column=1, columnspan=2, padx=8, pady=5, sticky='ew')
        self.api_key.bind('<FocusOut>', self._save_api_key)
        try:
            saved_key = load_api_key()
            if saved_key:
                self.api_key.insert(0, saved_key)
        except Exception as exc:
            self.log(f'WARNING: Could not load saved API key: {exc}')
        self.srt_label = ctk.CTkLabel(translation_frame, text='No SRT selected', wraplength=620, anchor='w', justify='left')
        self.srt_label.grid(row=5, column=0, columnspan=2, padx=15, pady=(8, 5), sticky='ew')
        self.select_srt_button = ctk.CTkButton(translation_frame, text='Select SRT', command=self.select_srt, width=130)
        self.select_srt_button.grid(row=5, column=2, padx=15, pady=5)
        self.translate_button = ctk.CTkButton(translation_frame, text='Translate SRT', command=self.translate_srt, height=40, state='disabled')
        self.translate_button.grid(row=6, column=0, columnspan=3, padx=15, pady=(8, 14), sticky='ew')

        status_frame = ctk.CTkFrame(content)
        status_frame.grid(row=3, column=0, padx=5, pady=5, sticky='ew')
        ctk.CTkLabel(status_frame, text='Status', font=ctk.CTkFont(size=14, weight='bold')).pack(anchor='w', padx=15, pady=(10, 5))
        self.status = ctk.CTkTextbox(status_frame, height=130)
        self.status.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        self.status.insert('1.0', 'Ready. Select a local media file to begin.\n')
        self.status.configure(state='disabled')

    def log(self, text: str):
        self.status.configure(state='normal')
        self.status.insert('end', text + '\n')
        self.status.see('end')
        self.status.configure(state='disabled')

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
            self.download_button.configure(text='Download model', state='normal')
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
        filename = filedialog.askopenfilename(title='Select video or audio', filetypes=VIDEO_AUDIO_TYPES)
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
        filename = filedialog.askopenfilename(title='Select SRT', filetypes=SRT_TYPES)
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
            messagebox.showwarning(APP_NAME, 'Select a video or audio file first.')
            return
        if not self.model_manager.is_downloaded(self.selected_model):
            messagebox.showwarning(APP_NAME, 'Download the selected recognition model first.')
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
            messagebox.showwarning(APP_NAME, 'Enter an API key first.')
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
