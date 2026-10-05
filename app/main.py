import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import write_srt
from app.transcription.engine import ParakeetEngine
from app.transcription.models import ModelManager, ModelInfo

APP_NAME = "Subway"

VIDEO_AUDIO_TYPES = [
    ("Video and audio files", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.aac"),
    ("All files", "*.*"),
]


class SubwayApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x620")
        self.minsize(680, 540)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.selected_file: Path | None = None
        self.model_manager = ModelManager()
        self.models = self.model_manager.available_models()
        self.selected_model: ModelInfo = self.models[0]

        self._build_ui()
        self._refresh_model_status()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Subway", font=ctk.CTkFont(size=32, weight="bold")).grid(row=0, column=0, padx=30, pady=(25, 5))
        ctk.CTkLabel(self, text="Local subtitle generator", font=ctk.CTkFont(size=16)).grid(row=1, column=0, padx=30, pady=(0, 15))

        content = ctk.CTkFrame(self)
        content.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(4, weight=1)

        model_frame = ctk.CTkFrame(content)
        model_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        model_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(model_frame, text="Recognition model", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 6), sticky="w")

        self.model_menu = ctk.CTkOptionMenu(model_frame, values=[model.name for model in self.models], command=self._model_changed, height=38)
        self.model_menu.grid(row=1, column=0, padx=(15, 8), pady=(0, 8), sticky="ew")

        self.download_button = ctk.CTkButton(model_frame, text="Download model", command=self.download_model, height=38, width=155)
        self.download_button.grid(row=1, column=1, padx=(8, 15), pady=(0, 8))

        self.model_status = ctk.CTkLabel(model_frame, text="", anchor="w", justify="left")
        self.model_status.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 8), sticky="w")

        self.progress = ctk.CTkProgressBar(model_frame, height=10)
        self.progress.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 12), sticky="ew")
        self.progress.set(0)

        self.file_label = ctk.CTkLabel(content, text="No file selected", font=ctk.CTkFont(size=15), wraplength=600)
        self.file_label.grid(row=1, column=0, padx=25, pady=(15, 8))

        self.select_button = ctk.CTkButton(content, text="Select video or audio", command=self.select_file, height=42)
        self.select_button.grid(row=2, column=0, padx=25, pady=8)

        self.status = ctk.CTkTextbox(content, height=130)
        self.status.grid(row=4, column=0, padx=25, pady=(10, 20), sticky="nsew")
        self.status.insert("1.0", "Ready. Select a local media file to begin.\n")
        self.status.configure(state="disabled")

        self.generate_button = ctk.CTkButton(self, text="Create SRT", command=self.create_srt, height=46, state="disabled")
        self.generate_button.grid(row=3, column=0, padx=30, pady=(10, 25))

    def log(self, text: str):
        self.status.configure(state="normal")
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def _model_changed(self, name: str):
        self.selected_model = next(model for model in self.models if model.name == name)
        self._refresh_model_status()

    def _refresh_model_status(self):
        model = self.selected_model
        if self.model_manager.is_downloaded(model):
            self.model_status.configure(text=f"✓ Ready • {model.size_mb} MB • {model.languages}")
            self.download_button.configure(text="Model ready", state="disabled")
            self.progress.set(1)
        else:
            self.model_status.configure(text=f"Not downloaded • {model.size_mb} MB • {model.languages}")
            self.download_button.configure(text="Download model", state="normal")
            self.progress.set(0)
        self._update_generate_state()

    def download_model(self):
        model = self.selected_model
        self.download_button.configure(state="disabled")
        self.model_menu.configure(state="disabled")
        self.select_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self.progress.set(0)
        self.log(f"Downloading {model.name}...")
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
            self.model_status.configure(text=f"Downloading… {received / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB")

    def _download_done(self, path: Path):
        self.log(f"Model downloaded: {path}")
        self.model_menu.configure(state="normal")
        self.select_button.configure(state="normal")
        self._refresh_model_status()

    def _download_failed(self, exc: Exception):
        self.log(f"ERROR: model download failed: {exc}")
        self.model_menu.configure(state="normal")
        self.select_button.configure(state="normal")
        self._refresh_model_status()
        messagebox.showerror(APP_NAME, f"Model download failed.\n\n{exc}")

    def select_file(self):
        filename = filedialog.askopenfilename(title="Select video or audio", filetypes=VIDEO_AUDIO_TYPES)
        if not filename:
            return
        self.selected_file = Path(filename)
        self.file_label.configure(text=str(self.selected_file))
        self._update_generate_state()
        self.log(f"Selected: {self.selected_file.name}")

    def _update_generate_state(self):
        ready = self.selected_file is not None and self.model_manager.is_downloaded(self.selected_model)
        self.generate_button.configure(state="normal" if ready else "disabled")

    def create_srt(self):
        if not self.selected_file:
            messagebox.showwarning(APP_NAME, "Select a video or audio file first.")
            return
        if not self.model_manager.is_downloaded(self.selected_model):
            messagebox.showwarning(APP_NAME, "Download the selected recognition model first.")
            return

        self.generate_button.configure(state="disabled")
        self.select_button.configure(state="disabled")
        self.model_menu.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.log(f"Loading {self.selected_model.name}...")
        threading.Thread(target=self._transcribe_worker, args=(self.selected_file,), daemon=True).start()

    def _transcribe_worker(self, media_path: Path):
        try:
            engine = ParakeetEngine(runtime_dir=self.model_manager.runtime_dir, model_name=self.selected_model.filename)
            segments = list(engine.transcribe(media_path))
            subtitles = segments_to_subtitles(segments)
            output_path = media_path.with_suffix(".srt")
            write_srt(subtitles, output_path)
            self.after(0, self._transcription_done, output_path, len(subtitles))
        except Exception as exc:
            self.after(0, self._transcription_failed, exc)

    def _transcription_done(self, output_path: Path, count: int):
        self.log(f"Done: {count} subtitles")
        self.log(f"Saved: {output_path}")
        self._restore_controls()
        messagebox.showinfo(APP_NAME, f"SRT created successfully.\n\n{output_path}")

    def _transcription_failed(self, exc: Exception):
        self.log(f"ERROR: {exc}")
        self._restore_controls()
        messagebox.showerror(APP_NAME, str(exc))

    def _restore_controls(self):
        self.model_menu.configure(state="normal")
        self.select_button.configure(state="normal")
        self._refresh_model_status()


if __name__ == "__main__":
    app = SubwayApp()
    app.mainloop()
