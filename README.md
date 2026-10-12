# Subway

**Local subtitle generator for Windows**

Subway creates subtitles from local video/audio without uploading the media.

<img width="1238" height="1047" alt="image" src="https://github.com/user-attachments/assets/a9da5201-3194-4e8b-9483-66959ed8a417" />


## Recognition engine

The primary engine is **NVIDIA Parakeet TDT v3**, executed through NVIDIA's native **NeMo-Speech.cpp** runtime. The runtime supports Windows x64 and CUDA, while the quantized Parakeet model is kept as a separate local file rather than being embedded into the GUI executable.

This keeps the Windows distribution practical:

- Subway GUI is a small Python/CustomTkinter application compiled to an EXE.
- NeMo-Speech.cpp provides native GPU-accelerated speech recognition.
- Parakeet model is stored separately under runtime/models.
- FFmpeg converts local video/audio to 16 kHz mono WAV before recognition.
- Original media never leaves the computer.

## Pipeline

Local video/audio → FFmpeg → local Parakeet → word/segment timestamps → subtitle formatting → SRT

Optional translation is a separate step:

SRT text → user-selected Gemini or OpenAI API → translated SRT

The GUI supports Gemini and OpenAI, target-language selection, batching, and preservation of the original subtitle timings. Only subtitle text is sent to the translation API. The original media is never uploaded. OpenAI requests explicitly use `store: false`.

## Windows distribution

GitHub Actions builds a Windows distribution containing:

- Subway.exe
- native NeMo-Speech runtime
- CUDA backend libraries
- FFmpeg
- quantized Parakeet model

The build can be triggered manually or by pushing a version tag such as v0.1.0. The resulting ZIP is uploaded as a GitHub Actions artifact and attached to the GitHub Release for version tags.

## Current status

Early development. Local Parakeet recognition is working in the Windows build. The next layer adds optional SRT translation through Gemini or OpenAI while keeping the media and recognition pipeline local.

## Privacy

Subway is local-first. Cloud APIs are optional and only receive subtitle text when the user explicitly requests translation.
