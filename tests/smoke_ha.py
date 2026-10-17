"""Isolated Home Assistant lifecycle/controls test against a fake local engine."""

import asyncio
import copy
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
        version="0.3.0",
        live_id="default",
        live_name="First",
        server_id="fixture-server",
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
    profiles = {
        "default": {
            "config": config,
            "status": status,
            "received": received,
            "posts": posts,
            "destination": "",
        }
    }

    @web.middleware
    async def auth(request, handler):
        if request.headers.get("Authorization") != "Bearer " + ("x" * 40):
            raise web.HTTPUnauthorized()
        return await handler(request)

    async def api(request):
        path = request.match_info["path"]
        if path == "server":
            return web.json_response(
                {
                    "id": "fixture-server",
                    "capabilities": ["multiple_lives"],
                    "version": "0.3.0",
                }
            )
        if path == "catalog":
            return web.json_response(
                {
                    "sources": [
                        dict(source, catalog_id="source_" + source["id"])
                        for source in sources
                    ]
                }
            )
        if path == "lives":
            if request.method == "POST":
                body = await request.json()
                identity = "live_" + uuid.uuid4().hex[:12]
                c = copy.deepcopy(config)
                c.update(body["config"])
                st = copy.deepcopy(status)
                st.update(
                    id=uuid.uuid4().hex,
                    live_id=identity,
                    live_name=body["name"],
                    state="stopped",
                )
                st["selection"]["camera_id"] = c["sources"][0]["id"]
                st["current_camera"] = dict(
                    id=c["sources"][0]["id"],
                    name=c["sources"][0]["name"],
                    camera_entity="",
                )
                st["cameras"] = {x["id"]: dict(healthy=None) for x in c["sources"]}
                profiles[identity] = {
                    "config": c,
                    "status": st,
                    "received": {},
                    "posts": [],
                    "destination": "",
                }
                return web.json_response(st, status=201)
            return web.json_response(
                {
                    "lives": [
                        dict(
                            live_id=k,
                            name=v["status"]["live_name"],
                            id=v["status"]["id"],
                        )
                        for k, v in profiles.items()
                    ]
                }
            )
        identity = "default"
        if path.startswith("lives/"):
            segments = path.split("/", 2)
            identity = segments[1]
            if identity not in profiles:
                raise web.HTTPNotFound()
            path = segments[2] if len(segments) == 3 else ""
        profile = profiles[identity]
        c = profile["config"]
        st = profile["status"]
        if path == "":
            if request.method == "PATCH":
                st["live_name"] = (await request.json())["name"]
            elif request.method == "DELETE":
                if st["state"] == "running":
                    raise web.HTTPBadRequest()
                del profiles[identity]
                return web.json_response({"deleted": True})
            return web.json_response(st)
        if path == "status":
            return web.json_response(st)
        if path == "config":
            if request.method == "POST":
                c.update(await request.json())
            return web.json_response(c)
        if path == "metadata":
            profile["received"].update(await request.json())
        elif path == "selection":
            body = await request.json()
            st["selection"].update(body)
            st["selection"]["selection_revision"] = uuid.uuid4().hex
            source = next(
                x for x in c["sources"] if x["id"] == st["selection"]["camera_id"]
            )
            st["current_camera"] = dict(
                id=source["id"], name=source["name"], camera_entity=""
            )
        elif path == "comparison":
            profile["posts"].append(await request.json())
        elif path == "start":
            st.update(state="running", mode=(await request.json())["mode"])
        elif path == "stop":
            st["state"] = "stopped"
        elif path == "destination":
            profile["destination"] = (await request.json())["url"]
            st["destination_configured"] = bool(profile["destination"])
        elif path.endswith("snapshot.jpg"):
            return web.Response(
                body=b"\xff\xd8fixture\xff\xd9", content_type="image/jpeg"
            )
        else:
            raise web.HTTPNotFound()
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
        assert result["step_id"] == "existing", result
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"live_id": "default"}
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
        fields.update(ticker="Configured through the options menu")
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
        hass.states.async_set(
            "sensor.demo_humidity",
            "75",
            {"friendly_name": "Humidity", "unit_of_measurement": "%"},
        )
        options = await hass.config_entries.options.async_init(entry.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "information"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"],
            {
                "name": "First",
                "sensor_entities": ["sensor.demo_temperature", "sensor.demo_humidity"],
            },
        )
        assert result["type"] == "create_entry", result
        await hass.async_block_till_done()
        hass.states.async_set("sun.sun", "above_horizon")
        await entry.runtime_data.async_refresh()
        assert (
            received["sensor_text"] == "Temperature: 22.5 °C  ·  Humidity: 75 %"
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
        form = await hass.config_entries.flow.async_init(
            "live_studio", context={"source": "user"}
        )
        assert form["type"] == "menu"
        form = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"next_step_id": "create_live"}
        )
        assert form["step_id"] == "create", form
        bad = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"name": "Second", "camera_ids": [], "sensor_entities": []}
        )
        assert bad["errors"] == {"base": "cannot_create"}
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            {"name": "Second", "camera_ids": ["source_wide"], "sensor_entities": []},
        )
        assert result["type"] == "create_entry", result
        second = result["result"]
        await hass.async_block_till_done()
        assert second.state.value == "loaded"
        child = second.data["live_id"]
        assert profiles[child]["received"]["sensor_text"] == ""
        assert received["sensor_text"] == "Temperature: 22.5 °C  ·  Humidity: 75 %"
        child_id = profiles[child]["status"]["id"]
        child_switch = registry.async_get_entity_id(
            "switch", "live_studio", child_id + "_stream"
        )
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": child_switch}, blocking=True
        )
        assert (
            profiles[child]["status"]["state"] == "running"
            and status["state"] == "stopped"
        )
        options = await hass.config_entries.options.async_init(second.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "delete_live"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"], {"confirm_delete": True}
        )
        assert result["errors"] == {"base": "stop_live_first"}
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": child_switch}, blocking=True
        )
        options = await hass.config_entries.options.async_init(second.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "information"}
        )
        await hass.config_entries.options.async_configure(
            options["flow_id"],
            {"name": "Second renamed", "sensor_entities": ["sensor.demo_humidity"]},
        )
        await hass.async_block_till_done()
        await second.runtime_data.async_refresh()
        assert second.title == "Live Studio · Second renamed"
        assert profiles[child]["received"]["sensor_text"] == "Humidity: 75 %"
        assert received["sensor_text"] == "Temperature: 22.5 °C  ·  Humidity: 75 %"
        # A missing reading affects only this live's selected sensor, never invents data.
        hass.states.async_set("sensor.demo_humidity", "unavailable")
        await second.runtime_data.async_refresh()
        await entry.runtime_data.async_refresh()
        assert profiles[child]["received"]["sensor_text"] == ""
        assert received["sensor_text"] == "Temperature: 22.5 °C"
        form = await hass.config_entries.flow.async_init(
            "live_studio", context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], dict(connection, live_id=child)
        )
        assert result["errors"] == {"base": "wrong_live"}
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], dict(connection, live_id="default")
        )
        assert (
            result["type"] == "abort" and result["reason"] == "reconfigure_successful"
        )
        await hass.async_block_till_done()
        options = await hass.config_entries.options.async_init(second.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "destination"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"],
            {
                "destination_url": "rtmp://fixture.invalid/live/private-fixture-key",
                "clear_destination": False,
            },
        )
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert "destination_url" not in second.options and profiles[child][
            "destination"
        ].endswith("private-fixture-key")
        options = await hass.config_entries.options.async_init(second.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "delete_live"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"], {"confirm_delete": True}
        )
        assert result["type"] == "abort" and result["reason"] == "live_deleted"
        await hass.async_block_till_done()
        assert (
            child not in profiles
            and hass.config_entries.async_get_entry(second.entry_id) is None
        )
        assert entry.state.value == "loaded"
        from custom_components.live_studio import async_migrate_entry

        hass.config_entries.async_update_entry(
            entry, version=1, options={"sensor_entity": "sensor.demo_temperature"}
        )
        assert await async_migrate_entry(hass, entry)
        await hass.async_block_till_done()
        assert entry.version == 2 and entry.options["sensor_entities"] == [
            "sensor.demo_temperature"
        ]
        assert "sensor_entity" not in entry.options
        assert registry.async_get_entity_id(
            "text", "live_studio", status["id"] + "_ticker"
        ) == entity("text", "ticker")
        print(
            "PASS create/manage multiple lives, independent optional sensor lists, isolated controls, safe destinations/deletion, identity-preserving reconfiguration and legacy migration"
        )
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
