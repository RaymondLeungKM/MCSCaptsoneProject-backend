import unittest
from unittest.mock import patch

import httpx

from app.services.llm_service import LLMMessage, LLMProvider, LLMService


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses, seen_models):
        self._responses = list(responses)
        self._seen_models = seen_models

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self._seen_models.append(json.get("model"))
        return self._responses.pop(0)


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_404_retries_with_free_fallback_model(self):
        seen_models = []
        responses = [
            _FakeResponse(status_code=404, payload={}),
            _FakeResponse(
                status_code=200,
                payload={
                    "choices": [
                        {"message": {"content": "fallback-success"}},
                    ]
                },
            ),
        ]

        service = LLMService(
            provider=LLMProvider.OPENROUTER,
            api_key="test-key",
            model="invalid/model",
            base_url="https://openrouter.ai/api/v1",
        )

        with patch("app.services.llm_service.httpx.AsyncClient", return_value=_FakeAsyncClient(responses, seen_models)):
            result = await service.generate(
                messages=[LLMMessage(role="user", content="hello")],
                temperature=0.1,
                max_tokens=20,
            )

        self.assertEqual(result, "fallback-success")
        self.assertEqual(seen_models, ["invalid/model", "openai/gpt-oss-120b:free"])

    async def test_openrouter_403_advances_to_second_fallback_model(self):
        seen_models = []
        responses = [
            _FakeResponse(status_code=403, payload={}),
            _FakeResponse(
                status_code=200,
                payload={
                    "choices": [
                        {"message": {"content": "second-fallback-success"}},
                    ]
                },
            ),
        ]

        service = LLMService(
            provider=LLMProvider.OPENROUTER,
            api_key="test-key",
            model="openai/gpt-oss-120b:free",
            base_url="https://openrouter.ai/api/v1",
        )

        with patch("app.services.llm_service.httpx.AsyncClient", return_value=_FakeAsyncClient(responses, seen_models)):
            result = await service.generate(
                messages=[LLMMessage(role="user", content="hello")],
                temperature=0.1,
                max_tokens=20,
            )

        self.assertEqual(result, "second-fallback-success")
        self.assertEqual(seen_models, ["openai/gpt-oss-120b:free", "openai/gpt-4o-mini"])

    async def test_openrouter_404_does_not_loop_after_all_fallback_models_fail(self):
        seen_models = []
        responses = [
            _FakeResponse(status_code=404, payload={}),
            _FakeResponse(status_code=404, payload={}),
        ]

        service = LLMService(
            provider=LLMProvider.OPENROUTER,
            api_key="test-key",
            model="openai/gpt-oss-120b:free",
            base_url="https://openrouter.ai/api/v1",
        )

        with patch("app.services.llm_service.httpx.AsyncClient", return_value=_FakeAsyncClient(responses, seen_models)):
            with self.assertRaises(httpx.HTTPStatusError):
                await service.generate(
                    messages=[LLMMessage(role="user", content="hello")],
                    temperature=0.1,
                    max_tokens=20,
                )

        self.assertEqual(seen_models, ["openai/gpt-oss-120b:free", "openai/gpt-4o-mini"])


if __name__ == "__main__":
    unittest.main()