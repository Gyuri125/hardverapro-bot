"""Fotó alapú billentyűzet-felismerés tesztjei (hálózat és API nélkül)."""

import json

from dealradar import cli
from dealradar.config import Config, Settings, VisionConfig
from dealradar.models import Hit, Listing, Specs
from dealradar.vision import (
    VisionCache,
    VisionClient,
    VisionResult,
    build_client,
    image_key,
    parse_response,
)


# --------------------------------------------------------------------------
#  válasz feldolgozás
# --------------------------------------------------------------------------


def test_parse_response_plain_json():
    result = parse_response('{"layout":"hu","confidence":0.9,"evidence":"í és ű látszik"}')
    assert result is not None
    assert result.layout == "hu"
    assert result.confidence == 0.9


def test_parse_response_with_code_fence():
    result = parse_response(
        '```json\n{"layout":"foreign","confidence":0.75,"evidence":"no accents"}\n```'
    )
    assert result is not None
    assert result.layout == "foreign"


def test_parse_response_rejects_garbage():
    assert parse_response("nem tudom") is None
    assert parse_response('{"layout":"talán"}') is None
    assert parse_response("") is None


def test_confidence_is_clamped():
    result = parse_response('{"layout":"hu","confidence":5,"evidence":"x"}')
    assert result is not None
    assert result.confidence == 1.0


# --------------------------------------------------------------------------
#  kliens
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        return FakeResponse(self.payload)


def test_openai_client_parses_answer(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    session = FakeSession(
        {"choices": [{"message": {"content": '{"layout":"hu","confidence":0.88,"evidence":"ok"}'}}]}
    )
    client = VisionClient(VisionConfig(), session=session)
    result = client.analyze(["https://pelda/1.jpg"])
    assert result is not None
    assert result.layout == "hu"
    assert session.calls == 1


def test_anthropic_client_parses_answer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    session = FakeSession(
        {"content": [{"text": '{"layout":"foreign","confidence":0.8,"evidence":"us layout"}'}]}
    )
    client = VisionClient(
        VisionConfig(provider="anthropic", api_key_env="ANTHROPIC_API_KEY"), session=session
    )
    result = client.analyze(["https://pelda/1.jpg"])
    assert result is not None
    assert result.layout == "foreign"


class FakeGeminiSession:
    """GET: képet ad vissza, POST: Gemini-választ."""

    def __init__(self):
        self.posts = 0
        self.gets = 0

    def get(self, url, timeout=None, headers=None):
        self.gets += 1

        class ImageResponse:
            status_code = 200
            content = b"\xff\xd8\xff\xe0fakejpeg"
            headers = {"Content-Type": "image/jpeg"}

        return ImageResponse()

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts += 1
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": '{"layout":"hu","confidence":0.91,"evidence":"í és ű"}'}
                            ]
                        }
                    }
                ]
            }
        )


def test_gemini_client_downloads_images_and_parses(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    session = FakeGeminiSession()
    client = VisionClient(
        VisionConfig(
            provider="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY"
        ),
        session=session,
    )
    result = client.analyze(["https://img/1.jpg", "https://img/2.jpg"])
    assert result is not None
    assert result.layout == "hu"
    assert session.gets == 2
    assert session.posts == 1


def test_client_limits_images(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    session = FakeSession({"choices": [{"message": {"content": '{"layout":"hu","confidence":1}'}}]})
    client = VisionClient(VisionConfig(max_images=2), session=session)
    client.analyze(["a", "b", "c", "d"])
    assert session.calls == 1


def test_build_client_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_client(VisionConfig(enabled="auto")) is None
    assert build_client(VisionConfig(enabled="on")) is None


def test_build_client_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_client(VisionConfig()) is not None


def test_build_client_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_client(VisionConfig(enabled="off")) is None


# --------------------------------------------------------------------------
#  modell-ellenőrzés (self-check)
# --------------------------------------------------------------------------


class ModelSession:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1

        class Response:
            pass

        response = Response()
        response.status_code = self.status_code
        response.text = ""
        return response


def test_check_model_ok(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = VisionClient(
        VisionConfig(provider="gemini", api_key_env="GEMINI_API_KEY"), session=ModelSession(200)
    )
    ok, message = client.check_model()
    assert ok is True
    assert "elérhető" in message


def test_check_model_not_found(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = VisionClient(
        VisionConfig(provider="gemini", api_key_env="GEMINI_API_KEY"), session=ModelSession(404)
    )
    ok, message = client.check_model()
    assert ok is False
    assert "nem található" in message


def test_check_model_rejected_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    client = VisionClient(
        VisionConfig(provider="gemini", api_key_env="GEMINI_API_KEY"), session=ModelSession(403)
    )
    ok, message = client.check_model()
    assert ok is False
    assert "elutasította" in message


def test_check_model_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = VisionClient(VisionConfig(provider="gemini", api_key_env="GEMINI_API_KEY"))
    ok, message = client.check_model()
    assert ok is False
    assert "nincs API-kulcs" in message


# --------------------------------------------------------------------------
#  cache
# --------------------------------------------------------------------------


def test_cache_roundtrip(tmp_path):
    path = tmp_path / "vision_cache.json"
    cache = VisionCache(path)
    cache.load()
    key = image_key(["https://a/1.jpg", "https://a/2.jpg"])
    cache.put(key, VisionResult("hu", 0.8, "ok"))
    cache.save()

    again = VisionCache(path)
    again.load()
    result = again.get(key)
    assert result is not None
    assert result.layout == "hu"


def test_image_key_is_order_independent():
    assert image_key(["a", "b"]) == image_key(["b", "a"])


# --------------------------------------------------------------------------
#  refine_keyboards
# --------------------------------------------------------------------------


class StubClient:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def analyze(self, urls):
        self.calls += 1
        return self.result


def make_hit() -> Hit:
    listing = Listing(uadid="1", title="Lenovo Legion 5 RTX 4060", url="https://x", price=300_000)
    listing.images = ["https://img/1.jpg", "https://img/2.jpg"]
    listing.specs = Specs()
    return Hit(listing=listing, profile="profil", score=80)


def make_config(tmp_path) -> Config:
    return Config(
        settings=Settings(state_file=str(tmp_path / "seen.json")),
        vision=VisionConfig(enabled="on"),
    )


def test_refine_marks_hungarian_from_photo(monkeypatch, tmp_path):
    stub = StubClient(VisionResult("hu", 0.9, "í és ű látszik"))
    monkeypatch.setattr(cli, "build_client", lambda config: stub)
    hit = make_hit()

    kept, excluded = cli.refine_keyboards(make_config(tmp_path), [hit])

    assert len(kept) == 1 and not excluded
    assert hit.listing.specs.keyboard == "hu"
    assert hit.listing.specs.keyboard_source == "photo"
    assert any("fotó" in reason for reason in hit.reasons)


def test_refine_excludes_foreign(monkeypatch, tmp_path):
    stub = StubClient(VisionResult("foreign", 0.9, "nincs ékezet"))
    monkeypatch.setattr(cli, "build_client", lambda config: stub)
    hit = make_hit()

    kept, excluded = cli.refine_keyboards(make_config(tmp_path), [hit])

    assert not kept
    assert len(excluded) == 1
    assert hit.listing.specs.keyboard == "foreign"


def test_refine_keeps_low_confidence_foreign(monkeypatch, tmp_path):
    stub = StubClient(VisionResult("foreign", 0.3, "bizonytalan"))
    monkeypatch.setattr(cli, "build_client", lambda config: stub)
    hit = make_hit()

    kept, excluded = cli.refine_keyboards(make_config(tmp_path), [hit])

    assert len(kept) == 1 and not excluded
    assert hit.listing.specs.keyboard is None
    assert "nem derült ki" in (hit.listing.specs.keyboard_note or "")


def test_refine_skips_when_keyboard_already_known(monkeypatch, tmp_path):
    stub = StubClient(VisionResult("hu", 0.9, "x"))
    monkeypatch.setattr(cli, "build_client", lambda config: stub)
    hit = make_hit()
    hit.listing.specs.keyboard = "hu"

    kept, _ = cli.refine_keyboards(make_config(tmp_path), [hit])

    assert len(kept) == 1
    assert stub.calls == 0


def test_refine_uses_cache(monkeypatch, tmp_path):
    stub = StubClient(VisionResult("hu", 0.9, "x"))
    monkeypatch.setattr(cli, "build_client", lambda config: stub)
    config = make_config(tmp_path)

    cli.refine_keyboards(config, [make_hit()])
    cli.refine_keyboards(config, [make_hit()])

    assert stub.calls == 1
