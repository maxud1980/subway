import ssl
import urllib.error
from pathlib import Path

import pytest

from app import net
from app.transcription.models import ModelManager, get_model


class EmptyContext:
    def get_ca_certs(self):
        return []


@pytest.fixture(autouse=True)
def reset_context():
    net._context = None
    yield
    net._context = None


def test_default_store_is_used_when_it_has_certificates(monkeypatch):
    real = ssl.create_default_context()
    monkeypatch.setattr(net, "_is_empty", lambda context: False)
    monkeypatch.setattr(ssl, "create_default_context", lambda **kwargs: real)
    assert net.ssl_context() is real


def test_falls_back_to_certifi_when_store_is_empty(monkeypatch, tmp_path):
    bundle = tmp_path / "cacert.pem"
    bundle.write_text("")
    created = {}

    def fake_create(**kwargs):
        created.update(kwargs)
        return EmptyContext()

    monkeypatch.setattr(ssl, "create_default_context", fake_create)
    monkeypatch.setattr(net, "_certifi_bundle", lambda: str(bundle))
    net.ssl_context()
    assert created == {"cafile": str(bundle)}


def test_no_certifi_still_returns_a_context(monkeypatch):
    monkeypatch.setattr(ssl, "create_default_context", lambda **kwargs: EmptyContext())
    monkeypatch.setattr(net, "_certifi_bundle", lambda: None)
    assert net.ssl_context() is not None


def test_certifi_is_installed_and_readable():
    bundle = net._certifi_bundle()
    assert bundle and Path(bundle).stat().st_size > 1000


def test_unreachable_host_is_reported_clearly(monkeypatch, tmp_path):
    manager = ModelManager(tmp_path)
    monkeypatch.setattr(manager, "models_dir", tmp_path / "models")

    def fail(request, timeout=60):
        raise urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")

    monkeypatch.setattr("app.transcription.models.urlopen", fail)
    with pytest.raises(RuntimeError) as error:
        manager.download(get_model("parakeet-tdt-v3"))
    assert "huggingface.co" in str(error.value) and "CERTIFICATE_VERIFY_FAILED" in str(error.value)
