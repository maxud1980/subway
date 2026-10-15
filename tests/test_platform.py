import subprocess
import sys
from pathlib import Path

from app import paths, settings


def test_runtime_dir_inside_mac_app_bundle(monkeypatch, tmp_path):
    exe = tmp_path / "Subway.app" / "Contents" / "MacOS" / "Subway"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(paths, "IS_MAC", True)
    assert paths.runtime_dir() == tmp_path / "Subway.app" / "Contents" / "Resources" / "runtime"


def test_runtime_dir_beside_windows_exe(monkeypatch, tmp_path):
    exe = tmp_path / "Subway" / "Subway.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(paths, "IS_MAC", False)
    assert paths.runtime_dir() == tmp_path / "Subway" / "runtime"


def test_keychain_commands(monkeypatch):
    calls = []
    store = {}

    def fake_run(command, **kwargs):
        calls.append(command)
        action = command[1]
        if action == "add-generic-password":
            store["key"] = command[command.index("-w") + 1]
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == "find-generic-password":
            return subprocess.CompletedProcess(command, 0 if "key" in store else 44, store.get("key", "") + "\n", "")
        store.pop("key", None)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(settings, "IS_MAC", True)
    monkeypatch.setattr(settings, "IS_WINDOWS", False)
    monkeypatch.setattr(settings.subprocess, "run", fake_run)
    assert settings.load_api_key() == ""
    settings.save_api_key(" secret ")
    assert settings.load_api_key() == "secret"
    settings.save_api_key("")
    assert settings.load_api_key() == ""
    assert all(c[0] == "/usr/bin/security" for c in calls)
