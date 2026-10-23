import asyncio
import base64
import json

import httpx
import pytest

from app import ai_extractor


def mock_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(ai_extractor.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_structured_schema_images_and_duplicate_handling(monkeypatch, png_bytes):
    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-key-not-real"
        assert "key=" not in str(request.url)
        payload = json.loads(request.content)
        assert "responseJsonSchema" in payload["generationConfig"]
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        inline = payload["contents"][0]["parts"][1]["inlineData"]
        assert base64.b64decode(inline["data"]) == png_bytes
        records = [{"ten_lop": "12c9", "si_so": 40, "so_vang_khai_bao": 0, "hoc_sinh": []},
                   {"ten_lop": "12C9", "si_so": 40, "so_vang_khai_bao": 1, "hoc_sinh": [{"ten": "an", "loai": None}]}]
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"lop": records})}]}}]})
    mock_transport(monkeypatch, handler)
    result = asyncio.run(ai_extractor.extract_with_gemini("12C9", [("image/png", png_bytes)]))
    assert len(result["lop"]) == 1 and result["lop"][0]["overwritten"] == 1
    assert result["lop"][0]["hoc_sinh"] == [{"ten": "An", "loai": None}]


@pytest.mark.parametrize("status,expected", [(429,429), (401,503), (403,503), (404,503), (500,502)])
def test_http_errors(monkeypatch, status, expected):
    mock_transport(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(ai_extractor.ExtractionError) as error:
        asyncio.run(ai_extractor.extract_with_gemini("", []))
    assert error.value.status_code == expected


@pytest.mark.parametrize("exception,expected", [(httpx.ConnectError,502), (httpx.ReadTimeout,504)])
def test_network_and_timeout(monkeypatch, exception, expected):
    def handler(request):
        raise exception("simulated", request=request)
    mock_transport(monkeypatch, handler)
    with pytest.raises(ai_extractor.ExtractionError) as error:
        asyncio.run(ai_extractor.extract_with_gemini("", []))
    assert error.value.status_code == expected


@pytest.mark.parametrize("body", [
    {}, {"candidates": []},
    {"candidates": [{"finishReason": "MAX_TOKENS"}]},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"lop":[{"ten_lop":"bad"}]}'}]}}]},
])
def test_malformed_blocked_and_truncated_output(monkeypatch, body):
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(ai_extractor.ExtractionError):
        asyncio.run(ai_extractor.extract_with_gemini("", []))
