"""Real HA exception type, fake engine/provider; no camera/cloud network I/O."""

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location(
    "studio_ai_under_test",
    Path(__file__).resolve().parents[1] / "custom_components/live_studio/ai.py",
)
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)


class AIAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    def coordinator(self):
        sources = [dict(id=key, name=key) for key in ("wide", "town", "sky")]
        status = dict(
            state="running",
            sources_revision="fresh",
            selection={"selection_revision": "selection"},
            cameras={key: {"healthy": key != "sky"} for key in ("wide", "town", "sky")},
        )
        calls = []

        async def request(path, body=None):
            calls.append((path, copy.deepcopy(body)))
            return copy.deepcopy({"sources": sources} if path == "config" else status)

        async def provider(*args, **kwargs):
            keys = json.loads(args[2]["structure"])["required"]
            return {
                "structured_response": {
                    key: dict(score=80, usable=True, reason="Visible view")
                    for key in keys
                }
            }

        services = SimpleNamespace(
            has_service=lambda *args: True, async_call=AsyncMock(side_effect=provider)
        )
        c = SimpleNamespace(
            ai_lock=asyncio.Lock(),
            entry=SimpleNamespace(
                options={
                    "ai_enabled": True,
                    "ai_provider": "fixture",
                    "ai_model": "fixture",
                }
            ),
            hass=SimpleNamespace(services=services),
            client=SimpleNamespace(request=request),
            data={"stale": True},
            camera_entity=lambda key: "camera." + key,
            async_update_listeners=lambda: None,
            async_request_refresh=AsyncMock(),
        )
        return c, status, calls

    async def test_offline_skipped_but_complete_explicit_result_sent(self):
        c, status, calls = self.coordinator()
        await ai.compare(c)
        payload = c.hass.services.async_call.call_args.args[2]
        self.assertEqual(payload["image_entity"], ["camera.wide", "camera.town"])
        self.assertNotIn("sky", json.loads(payload["structure"])["required"])
        body = next(body for path, body in calls if path == "comparison")
        self.assertEqual(body["sources_revision"], "fresh")
        self.assertEqual(set(body["scores"]), {"wide", "town", "sky"})
        self.assertFalse(body["scores"]["sky"]["usable"])
        self.assertIn("no evaluada", body["scores"]["sky"]["reason"])
        self.assertIsNone(c.ai_error)

    async def test_only_one_healthy_does_not_call_model(self):
        c, status, calls = self.coordinator()
        status["cameras"]["town"]["healthy"] = False
        with self.assertRaises(ai.CompareConfigurationError):
            await ai.compare(c)
        c.hass.services.async_call.assert_not_awaited()
        self.assertFalse(any(path == "comparison" for path, body in calls))

    async def test_recovered_camera_automatically_rejoins(self):
        c, status, calls = self.coordinator()
        status["cameras"]["sky"]["healthy"] = True
        await ai.compare(c)
        self.assertEqual(
            len(c.hass.services.async_call.call_args.args[2]["image_entity"]), 3
        )
        body = next(body for path, body in calls if path == "comparison")
        self.assertTrue(body["scores"]["sky"]["usable"])

    async def test_extra_or_missing_provider_scores_rejected(self):
        c, status, calls = self.coordinator()
        c.hass.services.async_call = AsyncMock(
            return_value={
                "structured_response": {
                    "wide": dict(score=99, usable=True, reason="view")
                }
            }
        )
        with self.assertRaises(ai.CompareConfigurationError):
            await ai.compare(c)
        self.assertFalse(any(path == "comparison" for path, body in calls))

    async def test_complete_json_text_and_markdown_fence_are_accepted(self):
        scores = {key: dict(score=80, usable=True, reason="Visible") for key in ("wide", "town")}
        for text in (json.dumps(scores), "```json\n" + json.dumps(scores) + "\n```"):
            c, status, calls = self.coordinator()
            c.hass.services.async_call = AsyncMock(return_value={"response_text": text})
            await ai.compare(c)
            body = next(body for path, body in calls if path == "comparison")
            self.assertEqual(body["scores"]["wide"], scores["wide"])

    async def test_malformed_truncated_and_invalid_scores_preserve_view(self):
        valid = {key: dict(score=80, usable=True, reason="Visible") for key in ("wide", "town")}
        invalid = copy.deepcopy(valid)
        invalid["town"]["score"] = True
        for text in ('{"wide":', "No image available", json.dumps(invalid)):
            c, status, calls = self.coordinator()
            c.hass.services.async_call = AsyncMock(return_value={"response_text": text})
            with self.assertRaises(ai.CompareConfigurationError):
                await ai.compare(c)
            self.assertFalse(any(path == "comparison" for path, body in calls))


if __name__ == "__main__":
    unittest.main()
