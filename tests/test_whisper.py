import json
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from app.transcription import catalog
from app.transcription.engine import SpeechEngine, WhisperEngine, language_argument, parse_whisper
from app.transcription.models import WHISPER_VAD, ModelManager, get_model

WHISPER = get_model("whisper-large-v3-turbo")


def _token(text, start=None, end=None):
    token = {"text": text, "id": 1, "p": 0.9, "t_dtw": -1}
    if start is not None:
        token["offsets"] = {"from": start, "to": end}
    return token


def _segment(text, start, end, tokens):
    return {"offsets": {"from": start, "to": end}, "text": text, "tokens": tokens}


def test_whisper_languages():
    assert WHISPER.engine == "whisper"
    for code in ("ar", "uk", "fa", "he", "jv", "fil", "no", "pt-BR", "zh-Hans"):
        assert WHISPER.recognizes_language(code), code
    assert not WHISPER.recognizes_language("zu")
    assert language_argument(WHISPER, "jv") == "jw"
    assert language_argument(WHISPER, "fil") == "tl"
    assert language_argument(WHISPER, "zh-Hans") == "zh"
    assert language_argument(WHISPER, "pt-BR") == "pt"
    assert language_argument(WHISPER, "ar") == "ar"
    assert language_argument(WHISPER, "auto") == "auto"


def test_parse_whisper_joins_tokens_into_words():
    data = {"transcription": [
        _segment(" Привіт, світ!", 0, 1500, [
            _token("[_BEG_]", 0, 0), _token(" При", 100, 300), _token("віт", 300, 500), _token(",", 500, 520),
            _token(" світ", 700, 1100), _token("!", 1100, 1200), _token("[_TT_75]", 1500, 1500),
        ]),
        _segment(" [Music]", 1500, 4000, [_token(" [", 1500, 1600), _token("Music", 1600, 1700), _token("]", 1700, 1800)]),
        _segment(" مرحبا", 4000, 5000, [_token(" مر", 4100, 4400), _token("حبا", 4400, 4800), _token("<|endoftext|>")]),
    ]}
    words, segments = parse_whisper(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    assert [(w.text, w.start, w.end) for w in words] == [
        ("Привіт,", 0.1, 0.52), ("світ!", 0.7, 1.2), ("مرحبا", 4.1, 4.8)]
    assert [(s.text, s.start, s.end) for s in segments] == [("Привіт, світ!", 0.0, 1.5), ("مرحبا", 4.0, 5.0)]


def test_parse_whisper_reassembles_split_characters():
    # Older whisper.cpp builds write a token that ends in the middle of a UTF-8 character as is.
    word = " Київ".encode("utf-8")
    raw = (b'{"transcription": [{"offsets": {"from": 0, "to": 900}, "text": "' + word + b'", "tokens": ['
           b'{"text": "' + word[:4] + b'", "offsets": {"from": 0, "to": 300}},'
           b'{"text": "' + word[4:] + b'", "offsets": {"from": 300, "to": 800}}]}]}')
    words, _ = parse_whisper(raw)
    assert [(w.text, w.end) for w in words] == [("Київ", 0.8)]


def _fake_cli(folder: Path, body: str) -> Path:
    binary = folder / "bin" / ("whisper-cli.exe" if sys.platform == "win32" else "whisper-cli")
    binary.parent.mkdir(parents=True)
    script = binary.with_suffix(".py")
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    binary.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return binary


@pytest.mark.skipif(sys.platform == "win32", reason="the fake runtime is a shell script")
def test_whisper_engine_falls_back_to_the_cpu_build(tmp_path):
    runtime = tmp_path / "runtime"
    _fake_cli(runtime / "whisper-vulkan", "import sys\nprint('ggml_vulkan: no device')\nsys.exit(3)\n")
    _fake_cli(runtime / "whisper-cpu", """
        import json, sys
        args = sys.argv[1:]
        out = args[args.index("-of") + 1] + ".json"
        print("whisper_print_progress_callback: progress =  50%", file=sys.stderr)
        tokens = [{"text": " Hello", "offsets": {"from": 0, "to": 400}},
                  {"text": " world", "offsets": {"from": 500, "to": 900}}]
        data = {"args": args, "transcription": [{"offsets": {"from": 0, "to": 1000}, "text": " Hello world", "tokens": tokens}]}
        open(out, "w").write(json.dumps(data))
    """)
    manager = ModelManager(runtime)
    manager.models_dir = manager.fallback_dir = tmp_path / "models"
    engine = WhisperEngine(runtime, manager)
    assert [v for v, _ in engine.installed()] == ["vulkan", "cpu"]
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"")
    seen, lines = [], []
    transcript = SpeechEngine(runtime, manager).whisper.transcribe(
        wav, WHISPER, tmp_path / "model.bin", language="uk", phrases=["Subway", "Київ"],
        progress=seen.append, log=lines.append)
    assert [(w.text, w.start, w.end) for w in transcript.words] == [("Hello", 0.0, 0.4), ("world", 0.5, 0.9)]
    assert transcript.backend == "CPU" and seen == [0.5]
    assert any("vulkan build of whisper.cpp failed" in line for line in lines)
    assert not (tmp_path / "audio.whisper.json").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the fake runtime is a shell script")
def test_whisper_command_line(tmp_path):
    runtime = tmp_path / "runtime"
    record = tmp_path / "args.json"
    _fake_cli(runtime / "whisper-cpu", f"""
        import json, sys
        args = sys.argv[1:]
        open({str(record)!r}, "w").write(json.dumps(args))
        tokens = [{{"text": " Hi", "offsets": {{"from": 0, "to": 400}}}}]
        data = {{"transcription": [{{"offsets": {{"from": 0, "to": 500}}, "text": " Hi", "tokens": tokens}}]}}
        open(args[args.index("-of") + 1] + ".json", "w").write(json.dumps(data))
    """)
    manager = ModelManager(runtime)
    manager.models_dir = manager.fallback_dir = tmp_path / "models"
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"")
    WhisperEngine(runtime, manager).transcribe(wav, WHISPER, tmp_path / "model.bin", language="ar",
                                               device="cpu", phrases=["Subway", "Київ"])
    args = json.loads(record.read_text())
    assert args[args.index("-l") + 1] == "ar"
    assert args[args.index("-vm") + 1] == str(manager.path_for(WHISPER_VAD))
    assert args[args.index("--prompt") + 1] == "Subway, Київ"
    assert {"-oj", "-ojf", "--vad", "-sns", "-pp"} <= set(args) and "-ng" not in args


def test_whisper_model_needs_the_vad_file(tmp_path, monkeypatch):
    manager = ModelManager(tmp_path / "runtime")
    manager.models_dir = manager.fallback_dir = tmp_path / "models"
    manager.models_dir.mkdir()
    fetched = []

    def fake_download(model, progress, cancel):
        fetched.append(model.id)
        path = manager.models_dir / model.local_filename
        with path.open("wb") as handle:
            handle.truncate(model.size)
        return path

    monkeypatch.setattr(manager, "_download_file", fake_download)
    assert not manager.is_downloaded(WHISPER)
    manager.download(WHISPER)
    assert fetched == ["silero-vad", WHISPER.id] and manager.is_downloaded(WHISPER)
    (manager.models_dir / WHISPER_VAD.filename).unlink()
    assert not manager.is_downloaded(WHISPER) and manager.installed(WHISPER.id) is None
    manager.download(get_model("parakeet-tdt-v3"))
    assert fetched[-1] == "parakeet-tdt-v3" and "silero-vad" not in fetched[2:]


def test_catalog_accepts_whisper_entries_only_with_the_engine():
    entry = {"id": "whisper-large-v3-turbo", "name": "Whisper", "repo": "ggerganov/whisper.cpp",
             "revision": "c" * 40, "filename": "ggml-large-v3-turbo-q8_0.bin", "size": 10, "sha256": "d" * 64}
    assert catalog.parse_entry(entry) is None  # A NeMo model is always a .gguf file.
    assert catalog.parse_entry({**entry, "engine": "other"}) is None
    model = catalog.parse_entry({**entry, "engine": "whisper"})
    assert model is not None and model.engine == "whisper"
    assert catalog.parse_entry({**entry, "filename": "x.gguf"}).engine == "nemo"
