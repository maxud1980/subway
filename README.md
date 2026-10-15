# Subway v0.2.0

**Subway is a local subtitle generator for Windows.** Create subtitles from video and audio files without uploading your media to a server.

<img width="1238" alt="Subway application screenshot" src="https://github.com/user-attachments/assets/a9da5201-3194-4e8b-9483-66959ed8a417" />

## Features

- **Local speech recognition** with NVIDIA's NeMo-Speech.cpp runtime:
  - **Parakeet TDT v3** — 25 European languages, including Ukrainian and Russian.
  - **Nemotron 3.5 ASR** — 40 languages with automatic language detection.
- **Runs on any PC.** Subway picks the best device automatically: an NVIDIA card (CUDA), another graphics card (Vulkan) or the processor.
- **A queue of files.** Drag and drop several videos, press Start and come back when they are done. Files added while the queue runs are processed too.
- **Readable subtitles.** Lines are cut at sentences, clauses and pauses using word timings, with limits for line length, number of lines, time on screen and reading speed.
- **Translation into several languages at once** through the Gemini API, with context from the previous lines and your own glossary (names, places, terms).
- **Output formats:** SRT, WebVTT, ASS, a plain-text transcript with time marks, and an MP4 with subtitles burned into the picture.
- **Built-in editor** to fix text and timing and listen to any line.
- **Encrypted API key storage** on Windows using DPAPI.
- Interface in English, Ukrainian, German, French and Spanish.

## How it works

Local video/audio → FFmpeg → local speech model (word timings) → subtitle rules → SRT / VTT / ASS / TXT → optional translation → optional burned-in MP4

When translation is turned on, only subtitle text (and your glossary) is sent to the Gemini API. The original video and audio remain on your computer.

Existing files are never overwritten unless you allow it in Settings: Subway creates a numbered copy such as `video (2).srt` instead.

## Download and run

1. Download `Subway-Windows.zip` from the Assets section of the latest release.
2. Extract the ZIP archive to a folder.
3. Run `Subway.exe`.
4. Download a recognition model from within the application (about 700 MB, verified by checksum, resumable).
5. Optionally enter a Gemini API key in Settings to translate subtitles.

The Windows package includes the application, three builds of the NeMo-Speech runtime (CUDA, Vulkan, CPU) and FFmpeg. Speech models are downloaded separately.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python subway.py   # expects runtime/ with nemo-speech*/bin and ffmpeg
```

## Privacy

Subway processes the original media locally. Cloud access is optional and used only for subtitle translation; only subtitle text is sent to Gemini when translation is on.

## Project

[GitHub repository](https://github.com/maxud1980/subway)
