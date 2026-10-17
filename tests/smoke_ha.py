import asyncio
import json
import pathlib
import shutil
import tempfile

import aiohttp
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant
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
    p = pathlib.Path(tempfile.mkdtemp(prefix="live-studio-ha-"))
    shutil.copytree(
        pathlib.Path(__file__).resolve().parents[1] / "custom_components",
        p / "custom_components",
    )
    from aiohttp import web

    config = dict(
        rtsp_url="",
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
        id="test-engine-unique-id", version="0.1.0", state="stopped", mode="preview"
    )

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
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[auth])
    app.router.add_route("*", "/api/{path}", api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    settings = {
        "endpoint": "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1]),
        "api_token": "x" * 40,
    }
    h = HomeAssistant(str(p))
    h.config.skip_pip = True
    loader.async_setup(h)
    session = aiohttp.ClientSession()
    aiohttp_client.async_get_clientsession = lambda *a, **kw: session
    h.config_entries = config_entries.ConfigEntries(h, {})
    await h.config_entries.async_initialize()
    device_registry.async_setup(h)
    for registry in [
        floor_registry,
        label_registry,
        area_registry,
        device_registry,
        entity_registry,
    ]:
        await registry.async_load(h)
    assert await async_setup_component(h, "live_studio", {})
    form = await h.config_entries.flow.async_init(
        "live_studio", context={"source": "user"}
    )
    assert form["type"] == "form", form
    bad = await h.config_entries.flow.async_configure(
        form["flow_id"], {"endpoint": settings["endpoint"], "api_token": "incorrect"}
    )
    assert bad["errors"] == {"base": "invalid_auth"}, bad
    result = await h.config_entries.flow.async_configure(form["flow_id"], settings)
    assert result["type"] == "create_entry", result
    await h.async_block_till_done()
    entry = result["result"]
    assert entry.state.value == "loaded", entry.state
    entities = [
        s.entity_id
        for s in h.states.async_all()
        if s.entity_id.startswith(
            (
                "sensor.live_studio",
                "text.live_studio",
                "switch.live_studio",
                "button.live_studio",
            )
        )
    ]
    assert len(entities) == 7, entities
    print(
        "PASS: UI flow, rejected wrong token, real engine connection, config entry setup and 7 entities"
    )
    options = await h.config_entries.options.async_init(entry.entry_id)
    assert options["type"] == "form", options
    current = dict(entry.runtime_data.data["config"])
    current["sensor_entity"] = "sensor.demo_temperature"
    current["ticker"] = "Updated from Home Assistant options flow"
    result = await h.config_entries.options.async_configure(options["flow_id"], current)
    assert result["type"] == "create_entry", result
    await h.async_block_till_done()
    assert entry.options["sensor_entity"] == "sensor.demo_temperature"
    h.states.async_set(
        "sensor.demo_temperature",
        "22.5",
        {"friendly_name": "Temperature", "unit_of_measurement": "°C"},
    )
    await entry.runtime_data.async_refresh()
    assert (
        entry.runtime_data.data["config"]["ticker"]
        == "Updated from Home Assistant options flow"
    )
    await h.services.async_call(
        "text",
        "set_value",
        {
            "entity_id": next(
                e for e in entities if e.startswith("text.") and "ticker" in e
            ),
            "value": "Dashboard ticker",
        },
        blocking=True,
    )
    assert entry.runtime_data.data["config"]["ticker"] == "Dashboard ticker"
    print("PASS: options flow, selected HA sensor, text entity edits")
    from custom_components.live_studio.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(h, entry)
    assert settings["api_token"] not in json.dumps(diagnostics)
    assert "rtsp://" not in json.dumps(diagnostics)
    assert await h.config_entries.async_unload(entry.entry_id)
    print("PASS: redacted diagnostics and clean unload; production HA untouched")
    await h.async_stop()
    await session.close()
    await runner.cleanup()
    shutil.rmtree(p, ignore_errors=True)


asyncio.run(main())
