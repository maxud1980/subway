# Subway

Local subtitle generator for Windows.

## Goal

Subway creates subtitles from local video and audio files without uploading the media to a server.

Pipeline:

1. Select a local video/audio file.
2. Extract audio locally.
3. Transcribe locally with Whisper.
4. Generate an SRT subtitle file.
5. Later: translate subtitles through a user-selected Gemini or OpenAI API.

## Privacy

Media files are processed locally. Cloud APIs will only receive subtitle text when the user explicitly starts a translation operation.

## Status

Early development — project skeleton.
