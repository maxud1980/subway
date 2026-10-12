# Subway v0.1.2

**Subway is a local subtitle generator for Windows.** Create subtitles from video and audio files without uploading your media to a server.

<img width="1238" alt="Subway application screenshot" src="https://github.com/user-attachments/assets/a9da5201-3194-4e8b-9483-66959ed8a417" />

## Features

- **Local speech recognition** using NVIDIA Parakeet TDT v3 through the native NeMo-Speech.cpp runtime.
- **SRT subtitle generation** from local video and audio files.
- **FFmpeg integration** to prepare audio for recognition.
- **Optional subtitle translation** through the Gemini API.
- **Multiple interface and target languages.**
- **Encrypted API key storage** on Windows using DPAPI.

## How it works

Local video/audio → FFmpeg → local Parakeet model → timestamped subtitles → SRT

When translation is requested, only subtitle text is sent to the Gemini API. The original video and audio remain on your computer.

## Download and run

1. Download `Subway-Windows.zip` from the Assets section of this release.
2. Extract the ZIP archive to a folder.
3. Run `Subway.exe`.
4. Download the Parakeet model from within the application if it is not already installed.
5. Optionally enter a Gemini API key to translate SRT files.

The Windows package includes the application, native NeMo-Speech runtime, required runtime libraries, and FFmpeg. The speech recognition model is downloaded separately.

## Privacy

Subway processes the original media locally. Cloud access is optional and used only for subtitle translation; only subtitle text is sent to Gemini when you explicitly start translation.

## Project

[GitHub repository](https://github.com/maxud1980/subway)
