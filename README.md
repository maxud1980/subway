# Subway v0.3.0

**Subway is a local subtitle generator for Windows and macOS (Apple Silicon).** Create subtitles from video and audio files without uploading your media to a server.

<img width="1238" alt="Subway application screenshot" src="https://github.com/user-attachments/assets/a9da5201-3194-4e8b-9483-66959ed8a417" />

## Features

- **Local speech recognition** with NVIDIA's NeMo-Speech.cpp runtime and whisper.cpp:
  - **Parakeet TDT v3** — 25 European languages, including Ukrainian and Russian.
  - **Nemotron 3.5 ASR** — 40 languages with automatic language detection.
  - **Whisper large-v3-turbo** (OpenAI, through whisper.cpp) — 99 languages, including Arabic, Persian, Hebrew and Turkish. Speech is first found with Silero voice activity detection, so music and silence do not turn into invented text.
- **Language check before recognition.** Choose the spoken language and Subway tells you whether the selected model knows it, offers a model that does, and refuses to start rather than produce meaningless subtitles.
- **Model updates without reinstalling.** At startup Subway reads the model list in [`models.json`](models.json) and offers to download newer versions of the models (pinned revision, checked by SHA-256). The previous version keeps working until the new one is downloaded.
- **Runs on any computer.** Subway picks the best device automatically: an NVIDIA card (CUDA) or another graphics card (Vulkan) on Windows, Apple graphics (Metal) on Apple Silicon Macs, or the processor.
- **A queue of files.** Drag and drop several videos, press Start and come back when they are done. Files added while the queue runs are processed too.
- **Readable subtitles.** Lines are cut at sentences, clauses and pauses using word timings, with limits for line length, number of lines, time on screen and reading speed.
- **Translation into several languages at once** through the Gemini API, with context from the previous lines and your own glossary (names, places, terms).
- **Output formats:** SRT, WebVTT, ASS, a plain-text transcript with time marks, and an MP4 with subtitles burned into the picture.
- **Built-in editor** to fix text and timing and listen to any line.
- **Secure API key storage:** DPAPI on Windows, the Keychain on macOS.
- Interface in English, Ukrainian, German, French and Spanish.

## How it works

Local video/audio → FFmpeg → local speech model (word timings) → subtitle rules → SRT / VTT / ASS / TXT → optional translation → optional burned-in MP4

When translation is turned on, only subtitle text (and your glossary) is sent to the Gemini API. The original video and audio remain on your computer.

Existing files are never overwritten unless you allow it in Settings: Subway creates a numbered copy such as `video (2).srt` instead.

## Download and run

### Windows

1. Download `Subway-Windows.zip` from the Assets section of the latest release.
2. Extract the ZIP archive to a folder.
3. Run `Subway.exe`.
4. Download a recognition model from within the application (about 700 MB, verified by checksum, resumable).
5. Optionally enter a Gemini API key in Settings to translate subtitles.

The Windows package includes the application, three builds of the NeMo-Speech runtime (CUDA, Vulkan, CPU), two builds of whisper.cpp (Vulkan, CPU) and FFmpeg. Speech models are downloaded separately.

### macOS (Apple Silicon)

1. Download `Subway-macOS-AppleSilicon.dmg` from the Assets section of the latest release.
2. Open the DMG and drag Subway to Applications.
3. The app is not notarized by Apple, so the first launch is blocked. Open **System Settings → Privacy & Security** and click **Open Anyway** next to the Subway message.
4. Download a recognition model from within the application.

Requires macOS 11 or newer on an Apple Silicon Mac (M1 and later); recognition runs on the GPU through Metal. Settings and models are stored in `~/Library/Application Support/Subway`.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python subway.py   # expects runtime/ with nemo-speech*/bin, whisper-*/bin and ffmpeg
```

### Publishing a new model version

A weekly workflow (`Model updates`) compares `models.json` with Hugging Face and opens an issue when NVIDIA publishes a new file, with the revision, size and checksum to copy. Update the entry in `models.json` on `main` and every installed Subway offers it at the next start. Set `min_app_version` when the model needs a newer NeMo-Speech runtime than older Subway builds carry; older builds skip that entry and keep the version they have until Subway itself is updated.

## Privacy

Subway processes the original media locally. Cloud access is optional and used only for subtitle translation; only subtitle text is sent to Gemini when translation is on.

## Project

[GitHub repository](https://github.com/maxud1980/subway)
