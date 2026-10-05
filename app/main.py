import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import write_srt
from app.transcription.engine import ParakeetEngine

APP_NAME = "Subway"

VIDEO_AUDIO_TYPES = [
    ("Video and audio files", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.aac"),
    ("All files", "*.*"),
]


class SubwayApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x500")
        self.minsize(680, 440)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.selected_file: Path | None = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text="Subway", font=ctk.CTkFont(size=32, weight="bold")).grid(row=0, column=0, padx=30, pady=(30, 5))
        ctk.CTkLabel(self, text="Local subtitle generator", font=ctk.CTkFont(size=16)).grid(row=1, column=0, padx=30, pady=(0, 25))

        content = ctk.CTkFrame(self)
        content.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        self.file_label = ctk.CTkLabel(content, text="No file selected", font=ctk.CTkFont(size=15), wraplength=600)
        self.file_label.grid(row=0, column=0, padx=25, pady=(30, 15))

        self.select_button = ctk.CTkButton(content, text="Select video or audio", command=self.select_file, height=42)
        self.select_button.grid(row=1, column=0, padx=25, pady=10)

        self.status = ctk.CTkTextbox(content, height=130)
        self.status.grid(row=2, column=0, padx=25, pady=(15, 25), sticky="nsew")
        self.status.insert("1.0", "Ready. Select a local media file to begin.\\n")
        self.status.configure(state="disabled")

        self.generate_button = ctk.CTkButton(self, text="Create SRT", command=self.create_srt, height=46, state="disabled")
        self.generate_button.grid(row=3, column=0, padx=30, pady=(10, 30))

    def log(self, text: str):
        self.status.configure(state="normal")
        self.status.insert("end", text + "\\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def select_file(self):
        filename = filedialog.askopenfilename(title="Select video or audio", filetypes=VIDEO_AUDIO_TYPES)
        if not filename:
            return
        self.selected_file = Path(filename)
        self.file_label.configure(text=str(self.selected_file))
        self.generate_button.configure(state="normal")
        self.log(f"Selected: {self.selected_file.name}")

    def create_srt(self):
        if not self.selected_file:
            messagebox.showwarning(APP_NAME, "Select a video or audio file first.")
            return
        self.generate_button.configure(state="disabled")
        self.select_button.configure(state="disabled")
        self.log("Loading Parakeet TDT v3...")
        threading.Thread(target=self._transcribe_worker, args=(self.selected_file,), daemon=True).start()

    def _transcribe_worker(self, media_path: Path):
        try:
            engine = ParakeetEngine()
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
        self.generate_button.configure(state="normal")
        self.select_button.configure(state="normal")
        messagebox.showinfo(APP_NAME, f"SRT created successfully.\\n\\n{output_path}")

    def _transcription_failed(self, exc: Exception):
        self.log(f"ERROR: {exc}")
        self.generate_button.configure(state="normal")
        self.select_button.configure(state="normal")
        messagebox.showerror(APP_NAME, str(exc))


if __name__ == "__main__":
    app = SubwayApp()
    app.mainloop()
