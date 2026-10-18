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
        minimum_margin=10,
        morning_camera="",
        morning_start="05:00",
        morning_end="08:00",
        morning_bonus=0,
        evening_camera="",
        evening_start="16:30",
        evening_end="19:00",
        evening_bonus=0,
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
        camera_sidebar=False,
        sidebar_refresh_seconds=3,
        ticker="",
        cta="Like and subscribe",
        cta_period=600,
        cta_duration=12,
        overlay_layout={"band": {"position": "bottom"}},
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
                patch = await request.json()
                c.update(patch)
                if "sources" in patch:
                    st["sources_revision"] = uuid.uuid4().hex
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
        registry = entity_registry.async_get(hass)
        registry.async_get_or_create(
            "number",
            "live_studio",
            status["id"] + "_day_bonus",
            config_entry=entry,
        )
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state.value == "loaded", entry.state

        def entity(domain, key):
            return registry.async_get_entity_id(
                domain, "live_studio", status["id"] + "_" + key
            )

        entities = [
            e for e in registry.entities.values() if e.config_entry_id == entry.entry_id
        ]
        assert len(entities) == 24, [e.entity_id for e in entities]
        assert entity("number", "morning_bonus")
        assert entity("number", "evening_bonus")
        assert registry.async_get_entity_id(
            "number", "live_studio", status["id"] + "_day_bonus"
        ) is None
        print(
            "PASS installation, authentication and 24 native entities including timed bonuses and camera proxies"
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
        await entry.runtime_data.async_refresh()
        assert received["sensor_text"] == "Temperature: 22.5 °C  ·  Humidity: 75 %"
        assert "daylight" not in received
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
            "PASS options menu, sensor metadata, live text, numeric policy and manual/automatic camera controls"
        )

        async def model(call):
            assert "Test subject: chickens" in call.data["message"]
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
                ai_focus="Test subject: chickens",
                minimum_margin=10,
                morning_camera="zoom",
                morning_start="05:00:00",
                morning_end="08:00:00",
                morning_bonus=15,
                evening_camera="wide",
                evening_start="16:30:00",
                evening_end="19:00:00",
                evening_bonus=15,
                confirmations=2,
                minimum_dwell_minutes=20,
                comparison_interval_minutes=10,
            ),
        )
        assert result["type"] == "create_entry", result
        assert config["morning_camera"] == "zoom"
        assert config["morning_start"] == "05:00:00"
        assert config["morning_bonus"] == 15
        assert config["evening_camera"] == "wide"
        assert config["evening_bonus"] == 15
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
        from types import SimpleNamespace
        from inspect import unwrap
        from custom_components.live_studio.overlay import get_overlay, update_overlay

        class Connection:
            def __init__(self, admin=True):
                self.user = SimpleNamespace(is_admin=admin)
                self.result = self.error = None

            def send_result(self, identity, result):
                self.result = result

            def send_error(self, identity, code, message):
                self.error = code

        overlay_entity = registry.async_get_entity_id(
            "sensor", "live_studio", child_id + "_status"
        )
        connection_test = Connection()
        await unwrap(get_overlay)(
            hass, connection_test, {"id": 1, "entity_id": overlay_entity}
        )
        assert "rtsp_url" not in json.dumps(connection_test.result)
        assert "api_token" not in json.dumps(connection_test.result)
        message = {
            "id": 2,
            "entity_id": overlay_entity,
            "changes": {"overlay_layout": {"band": {"position": "top"}}},
        }
        await unwrap(update_overlay)(hass, connection_test, message)
        assert connection_test.error is None
        assert profiles[child]["config"]["overlay_layout"]["band"]["position"] == "top"
        assert config["overlay_layout"]["band"]["position"] == "bottom"
        forbidden = Connection(False)
        await unwrap(update_overlay)(hass, forbidden, message)
        assert forbidden.error == "unauthorized"
        forbidden = Connection()
        await unwrap(update_overlay)(
            hass,
            forbidden,
            {
                "id": 3,
                "entity_id": overlay_entity,
                "changes": {"destination_url": "rtmp://fixture.invalid/not-allowed"},
            },
        )
        assert forbidden.error == "cannot_apply"
        assert (await second.runtime_data.client.image(None)).startswith(b"\xff\xd8")
        print(
            "PASS bundled overlay frontend, sanitized editor API, administrator-only changes, independent lives and composed camera proxy"
        )
        from custom_components.live_studio.frigate import discover_sources
        from unittest.mock import AsyncMock, patch

        entries = [
            SimpleNamespace(
                platform="frigate",
                entity_id="camera." + name,
                disabled_by=None,
                config_entry_id=server,
                name=None,
                original_name=None,
            )
            for name, server in [
                ("known", "fg1"),
                ("new", "fg1"),
                ("other", "fg2"),
                ("broken", "fg1"),
            ]
        ]
        fake_hass = SimpleNamespace(
            states=SimpleNamespace(
                get=lambda identity: SimpleNamespace(
                    attributes={"friendly_name": "Friendly " + identity}
                )
            )
        )

        async def fixture_stream(hass, identity):
            if identity == "camera.broken":
                raise HomeAssistantError("private failure")
            return "rtsp://frigate-internal:8554/" + identity.removeprefix("camera.")

        known = [
            dict(
                camera_entity="camera.known",
                rtsp_url="rtsp://reachable.invalid:8554/known",
            )
        ]
        with patch(
            "custom_components.live_studio.frigate.entity_registry.async_get",
            return_value=SimpleNamespace(entities={e.entity_id: e for e in entries}),
        ), patch(
            "custom_components.live_studio.frigate.async_get_stream_source",
            new=AsyncMock(side_effect=fixture_stream),
        ):
            discovered = await discover_sources(fake_hass, known)
        by_camera = {source["camera_entity"]: source for source in discovered}
        assert len(discovered) == 3
        assert (
            by_camera["camera.new"]["rtsp_url"] == "rtsp://reachable.invalid:8554/new"
        )
        assert (
            by_camera["camera.other"]["rtsp_url"]
            == "rtsp://frigate-internal:8554/other"
        )
        assert by_camera["camera.new"]["name"] == "Friendly camera.new"
        print(
            "PASS Frigate auto-discovery: friendly names, external restream origin reuse, separate Frigate servers and unavailable source isolation"
        )
        from custom_components.live_studio.cameras import get_cameras, update_cameras

        camera_connection = Connection()
        await unwrap(get_cameras)(
            hass, camera_connection, {"id": 4, "entity_id": overlay_entity}
        )
        camera_result = camera_connection.result
        assert "rtsp_url" not in json.dumps(camera_result)
        assert "fixture.invalid" not in json.dumps(camera_result)
        assert camera_result["cameras"]
        original_sources = copy.deepcopy(config["sources"])
        edit = {
            "id": 5,
            "entity_id": overlay_entity,
            "revision": camera_result["revision"],
            "camera_ids": [camera_result["cameras"][0]["id"]],
        }
        forbidden = Connection(False)
        await unwrap(update_cameras)(hass, forbidden, edit)
        assert forbidden.error == "unauthorized"
        stale = Connection()
        await unwrap(update_cameras)(hass, stale, dict(edit, revision="stale"))
        assert stale.error == "conflict"
        await unwrap(update_cameras)(hass, camera_connection, edit)
        assert camera_connection.error is None
        await hass.async_block_till_done()
        assert config["sources"] == original_sources
        assert len(profiles[child]["config"]["sources"]) == 1
        assert len(second.runtime_data.data["config"]["sources"]) == 1
        renamed_connection = Connection()
        await unwrap(get_cameras)(
            hass, renamed_connection, {"id": 8, "entity_id": overlay_entity}
        )
        payload = renamed_connection.result
        rename = dict(
            edit,
            revision=payload["revision"],
            camera_names={edit["camera_ids"][0]: "Vista pública"},
        )
        await unwrap(update_cameras)(hass, renamed_connection, rename)
        assert renamed_connection.error is None
        await hass.async_block_till_done()
        assert profiles[child]["config"]["sources"][0]["name"] == "Vista pública"
        assert config["sources"] == original_sources
        await unwrap(get_cameras)(
            hass, renamed_connection, {"id": 9, "entity_id": overlay_entity}
        )
        assert (
            next(c for c in renamed_connection.result["cameras"] if c["selected"])[
                "public_name"
            ]
            == "Vista pública"
        )
        invalid = Connection()
        await unwrap(update_cameras)(
            hass,
            invalid,
            dict(
                rename,
                revision=renamed_connection.result["revision"],
                camera_names={edit["camera_ids"][0]: " "},
            ),
        )
        assert invalid.error == "cannot_apply"
        print(
            "PASS public camera names: persisted, isolated per live, returned after discovery, empty names rejected"
        )
        discovered_source = dict(
            catalog_id="source_auto_sky",
            id="camera_auto_sky",
            name="Sky",
            rtsp_url="rtsp://fixture.invalid/sky",
            camera_entity="camera.sky",
            description="",
        )
        with patch(
            "custom_components.live_studio.frigate.discover_sources",
            new=AsyncMock(return_value=[discovered_source]),
        ):
            auto_connection = Connection()
            await unwrap(get_cameras)(
                hass, auto_connection, {"id": 6, "entity_id": overlay_entity}
            )
            auto_payload = auto_connection.result
            assert any(
                source["id"] == "source_auto_sky" for source in auto_payload["cameras"]
            )
            assert "rtsp_url" not in json.dumps(auto_payload)
            await unwrap(update_cameras)(
                hass,
                auto_connection,
                {
                    "id": 7,
                    "entity_id": overlay_entity,
                    "revision": auto_payload["revision"],
                    "camera_ids": ["source_auto_sky"],
                },
            )
            assert auto_connection.error is None
            assert (
                profiles[child]["config"]["sources"][0]["camera_entity"] == "camera.sky"
            )
            await hass.async_block_till_done()
            assert config["sources"] == original_sources
        print(
            "PASS newly discovered Frigate camera selected by opaque ID without entering a name or RTSP URL"
        )
        # Restore the fixture for subsequent lifecycle tests.
        profiles[child]["config"]["sources"] = copy.deepcopy(sources)
        await second.runtime_data.async_request_refresh()
        print(
            "PASS camera checklist API: no RTSP disclosure, admin-only, stale-edit protection, independent live changes and entity reload"
        )
        rail_switch = registry.async_get_entity_id("switch", "live_studio", child_id + "_camera_sidebar")
        await hass.services.async_call("switch", "turn_on", {"entity_id": rail_switch}, blocking=True)
        assert profiles[child]["config"]["camera_sidebar"] is True
        assert config["camera_sidebar"] is False
        refresh_number = registry.async_get_entity_id("number", "live_studio", child_id + "_sidebar_refresh_seconds")
        await hass.services.async_call("number", "set_value", {"entity_id": refresh_number, "value": 5}, blocking=True)
        assert profiles[child]["config"]["sidebar_refresh_seconds"] == 5
        await hass.services.async_call("switch", "turn_off", {"entity_id": rail_switch}, blocking=True)
        assert profiles[child]["config"]["camera_sidebar"] is False
        print("PASS independent sidebar switch and thumbnail refresh number")
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
