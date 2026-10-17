"""Isolated Home Assistant lifecycle/controls test against a fake local engine."""

import asyncio
import json
import pathlib
import shutil
import tempfile
import time
import uuid

import aiohttp
from aiohttp import web
from homeassistant import auth as ha_auth
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    aiohttp_client,
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
    label_registry,
)
from homeassistant.setup import async_setup_component


async def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="live-studio-ha-"))
    shutil.copytree(
        pathlib.Path(__file__).resolve().parents[1] / "custom_components",
        root / "custom_components",
    )
    sources = [
        dict(
            id=c,
            name=n,
            rtsp_url="rtsp://camera.invalid/" + c,
            camera_entity="",
            description="Test view",
        )
        for c, n in [("wide", "Wide"), ("zoom", "Zoom")]
    ]
    config = dict(
        rtsp_url=sources[0]["rtsp_url"],
        sources=sources,
        preferred_camera="wide",
        minimum_margin=10,
        day_bonus=5,
        minimum_dwell=1200,
        confirmations=2,
        comparison_interval=600,
        show_camera_name=True,
        no_signal_text="No signal",
        music_directory="/share/stream_music",
        width=1920,
        height=1080,
        fps=15,
        bitrate_kbps=3000,
        threads=2,
        title="Live Studio",
        timezone="UTC",
        show_clock=True,
        ticker="",
        cta="Like and subscribe",
        cta_period=600,
        cta_duration=12,
    )
    status = dict(
        id="test-engine-unique-id",
        version="0.2.0",
        state="stopped",
        mode="preview",
        sources_revision="source-revision",
        selection=dict(
            mode="automatic",
            camera_id="wide",
            last_switch=time.time(),
            selection_revision="selection-revision",
            candidate=None,
            confirmations=0,
            comparison={},
            compared_at=None,
            effective_scores={},
            applied_day_bonus=0,
            decision="waiting",
        ),
        current_camera=dict(id="wide", name="Wide", camera_entity=""),
        current_video=False,
        cameras={s["id"]: dict(name=s["name"], healthy=None) for s in sources},
    )
    received = {}
    posts = []

    @web.middleware
    async def auth(request, handler):
        if request.headers.get("Authorization") != "Bearer " + ("x" * 40):
            raise web.HTTPUnauthorized()
        return await handler(request)

    async def api(request):
        path = request.match_info["path"]
        if path == "status":
            return web.json_response(status)
        if path == "config":
            if request.method == "POST":
                config.update(await request.json())
            return web.json_response(config)
        if path == "metadata":
            received.update(await request.json())
        if path == "selection":
            body = await request.json()
            status["selection"].update(body)
            status["selection"]["selection_revision"] = uuid.uuid4().hex
            source = next(
                s for s in sources if s["id"] == status["selection"]["camera_id"]
            )
            status["current_camera"] = dict(
                id=source["id"], name=source["name"], camera_entity=""
            )
        if path == "comparison":
            posts.append(await request.json())
        if path.endswith("snapshot.jpg"):
            return web.Response(
                body=b"\xff\xd8fixture\xff\xd9", content_type="image/jpeg"
            )
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[auth])
    app.router.add_route("*", "/api/{path:.*}", api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    connection = dict(
        endpoint="http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1]),
        api_token="x" * 40,
    )
    hass = HomeAssistant(str(root))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    session = aiohttp.ClientSession()
    aiohttp_client.async_get_clientsession = lambda *a, **k: session
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    device_registry.async_setup(hass)
    for registry in [
        floor_registry,
        label_registry,
        area_registry,
        device_registry,
        entity_registry,
    ]:
        await registry.async_load(hass)
    hass.auth = await ha_auth.auth_manager_from_config(
        hass, [{"type": "homeassistant"}], []
    )
    try:
        assert await async_setup_component(hass, "live_studio", {})
        form = await hass.config_entries.flow.async_init(
            "live_studio", context={"source": "user"}
        )
        bad = await hass.config_entries.flow.async_configure(
            form["flow_id"], dict(connection, api_token="wrong")
        )
        assert bad["errors"] == {"base": "invalid_auth"}
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], connection
        )
        assert result["type"] == "create_entry"
        entry = result["result"]
        await hass.async_block_till_done()
        assert entry.state.value == "loaded", entry.state
        registry = entity_registry.async_get(hass)

        def entity(domain, key):
            return registry.async_get_entity_id(
                domain, "live_studio", status["id"] + "_" + key
            )

        entities = [
            e for e in registry.entities.values() if e.config_entry_id == entry.entry_id
        ]
        assert len(entities) == 20, [e.entity_id for e in entities]
        print(
            "PASS installation, authentication and 20 native entities including camera proxies"
        )
        options = await hass.config_entries.options.async_init(entry.entry_id)
        assert options["type"] == "menu"
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "overlays"}
        )
        assert options["step_id"] == "overlays"
        fields = {
            k: config[k]
            for k in [
                "title",
                "timezone",
                "ticker",
                "cta",
                "no_signal_text",
                "show_clock",
                "show_camera_name",
                "cta_period",
                "cta_duration",
            ]
        }
        fields.update(
            sensor_entity="sensor.demo_temperature",
            ticker="Configured through the options menu",
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"], fields
        )
        assert result["type"] == "create_entry", result
        await hass.async_block_till_done()
        hass.states.async_set(
            "sensor.demo_temperature",
            "22.5",
            {"friendly_name": "Temperature", "unit_of_measurement": "°C"},
        )
        hass.states.async_set("sun.sun", "above_horizon")
        await entry.runtime_data.async_refresh()
        assert (
            received["sensor_text"] == "Temperature: 22.5 °C"
            and received["daylight"] is True
        )
        await hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": entity("text", "ticker"), "value": "Dashboard ticker"},
            blocking=True,
        )
        assert config["ticker"] == "Dashboard ticker"
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity("number", "minimum_margin"), "value": 12},
            blocking=True,
        )
        assert config["minimum_margin"] == 12
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity("select", "camera_selection"), "option": "Zoom"},
            blocking=True,
        )
        assert (
            status["selection"]["mode"] == "manual"
            and status["selection"]["camera_id"] == "zoom"
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity("select", "camera_selection"), "option": "automatic"},
            blocking=True,
        )
        assert status["selection"]["mode"] == "automatic"
        print(
            "PASS options menu, sensor/daylight, live text, numeric policy and manual/automatic camera controls"
        )

        async def model(call):
            assert len(call.data["image_entity"]) == 2
            assert set(call.data["image_entity"]) == {
                entity("camera", "view_wide"),
                entity("camera", "view_zoom"),
            }
            return {
                "structured_response": {
                    s["id"]: dict(score=70, usable=True, reason="Visible detail")
                    for s in sources
                }
            }

        hass.services.async_register(
            "llmvision",
            "image_analyzer",
            model,
            supports_response=SupportsResponse.ONLY,
        )
        options = await hass.config_entries.options.async_init(entry.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "automation"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"],
            dict(
                ai_enabled=True,
                ai_provider="fixture-provider",
                ai_model="fixture-vision-model",
                preferred_camera="wide",
                minimum_margin=10,
                day_bonus=5,
                confirmations=2,
                minimum_dwell_minutes=20,
                comparison_interval_minutes=10,
            ),
        )
        assert result["type"] == "create_entry", result
        await hass.async_block_till_done()
        await hass.services.async_call(
            "button", "press", {"entity_id": entity("button", "compare")}, blocking=True
        )
        assert len(posts) == 1 and set(posts[0]["scores"]) == {"wide", "zoom"}
        assert (
            posts[0]["selection_revision"] == status["selection"]["selection_revision"]
        )
        snapshot = await entry.runtime_data.client.image("wide")
        assert snapshot.startswith(b"\xff\xd8")

        async def failing_model(call):
            raise RuntimeError("fixture-provider-private-error")

        hass.services.async_register(
            "llmvision",
            "image_analyzer",
            failing_model,
            supports_response=SupportsResponse.ONLY,
        )
        try:
            await entry.runtime_data.compare()
        except HomeAssistantError as error:
            assert "fixture-provider-private-error" not in str(error)
        else:
            raise AssertionError("Provider failure was not reported")
        assert len(posts) == 1
        from custom_components.live_studio.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert connection["api_token"] not in json.dumps(
            diagnostics
        ) and "rtsp://" not in json.dumps(diagnostics)
        assert await hass.config_entries.async_unload(entry.entry_id)
        print(
            "PASS optional vision provider, validated source IDs, snapshot client, sanitized failures, diagnostics and clean unload"
        )
    finally:
        await hass.async_stop()
        await session.close()
        await runner.cleanup()
        shutil.rmtree(root, ignore_errors=True)


asyncio.run(main())
