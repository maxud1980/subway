# Subway

**Local subtitle generator for Windows**

Subway creates subtitles from local video/audio without uploading the media.

## Recognition engines

- **NVIDIA Parakeet TDT v3** — primary engine. Supports 25 European languages including Ukrainian and Russian, automatic language detection, punctuation/capitalization, and word/segment timestamps.
- **Qwen3-ASR 1.7B** — high-quality alternative for difficult recordings and multilingual material.
- Whisper is not the primary engine.

## Pipeline

Local media → local ASR → word timestamps → subtitle segmentation → SRT

Optional translation is a separate step:

SRT text → user-selected Gemini or OpenAI API → translated SRT

The original video/audio is never sent to the translation API.

## Current status

Early development. The ASR abstraction and SRT modules are being prepared for the first Windows end-to-end test.

## Privacy

Subway is local-first. Cloud APIs are optional and only receive subtitle text when the user explicitly requests translation.
