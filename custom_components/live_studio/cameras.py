"""Private engine access behind a simple per-live camera checklist."""

import asyncio
import uuid

import voluptuous as vol
from homeassistant.components import websocket_api

from .api import StudioError
from .overlay import coordinator
from .const import DOMAIN
from .frigate import catalog_sources


async def catalog(current):
    sources, frigate_names = await catalog_sources(current.hass, current.client)
    config = await current.client.request("config")
    status = await current.client.request("status")
    selected = {source["rtsp_url"]: source["name"] for source in config["sources"]}
    owners = {}
    for entry in current.hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if not runtime or entry.data.get("endpoint") != current.entry.data.get(
            "endpoint"
        ):
            continue
        for source in runtime.data["config"]["sources"]:
            owners.setdefault(source["rtsp_url"], []).append(
                runtime.data["status"].get("live_name", entry.title)
            )
    return (
        sources,
        config,
        {
            "name": status.get("live_name", "Live Studio"),
            "revision": status.get("sources_revision"),
            "cameras": [
                {
                    "id": source["catalog_id"],
                    "name": frigate_names.get(
                        source["rtsp_url"],
                        selected.get(source["rtsp_url"], source["name"]),
                    )
                    + (
                        " · " + ", ".join(owners[source["rtsp_url"]])
                        if source["rtsp_url"] in owners
                        else ""
                    ),
                    "selected": source["rtsp_url"] in selected,
                    "public_name": selected.get(source["rtsp_url"], source["name"]),
                }
                for source in sources
            ],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "live_studio/cameras/get",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def get_cameras(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access required"
        )
        return
    try:
        _, _, result = await catalog(coordinator(hass, msg["entity_id"]))
        connection.send_result(msg["id"], result)
    except (ValueError, StudioError):
        connection.send_error(msg["id"], "unavailable", "Live Studio is unavailable")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "live_studio/cameras/update",
        vol.Required("entity_id"): str,
        vol.Required("revision"): str,
        vol.Required("camera_ids"): [str],
        vol.Optional("camera_names"): {str: str},
        vol.Optional("new_camera"): {
            vol.Required("name"): str,
            vol.Required("rtsp_url"): str,
        },
    }
)
@websocket_api.async_response
async def update_cameras(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access required"
        )
        return
    try:
        current = coordinator(hass, msg["entity_id"])
        if not hasattr(current, "camera_edit_lock"):
            current.camera_edit_lock = asyncio.Lock()
        async with current.camera_edit_lock:
            sources, config, previous = await catalog(current)
            if previous["revision"] != msg["revision"]:
                connection.send_error(
                    msg["id"], "conflict", "Reload the camera list before saving"
                )
                return
            ids = msg["camera_ids"]
            choices = {source["catalog_id"]: source for source in sources}
            if len(ids) != len(set(ids)) or set(ids) - choices.keys():
                raise ValueError()
            public_names = msg.get("camera_names", {})
            if public_names.keys() - set(ids):
                raise ValueError()
            for name in public_names.values():
                if (
                    not name.strip()
                    or len(name) > 64
                    or any(not c.isprintable() for c in name)
                    or name.strip().casefold() in ("automatic", "automático", "manual")
                ):
                    raise ValueError()
            existing = {source["rtsp_url"]: source for source in config["sources"]}
            selected = []
            for identity in ids:
                source = choices[identity]
                selected.append(
                    existing.get(
                        source["rtsp_url"],
                        {
                            **{
                                key: value
                                for key, value in source.items()
                                if key != "catalog_id"
                            },
                            "id": "camera_" + identity.removeprefix("source_"),
                        },
                    )
                )
                if identity in public_names:
                    selected[-1] = dict(
                        selected[-1], name=" ".join(public_names[identity].split())
                    )
            names = {
                source["name"].casefold()
                for source in selected
                if source["rtsp_url"] in existing
            }
            for index, source in enumerate(selected):
                if source["rtsp_url"] in existing or ids[index] in public_names:
                    continue
                if source["name"].casefold() in names:
                    source = dict(source)
                    base = source["name"][:55]
                    suffix = 2
                    while source["name"].casefold() in names:
                        source["name"] = f"{base} ({suffix})"
                        suffix += 1
                    selected[index] = source
                names.add(source["name"].casefold())
            if new := msg.get("new_camera"):
                if new["rtsp_url"] in {source["rtsp_url"] for source in selected}:
                    raise ValueError()
                selected.append(
                    dict(
                        new,
                        id="camera_" + uuid.uuid4().hex[:12],
                        camera_entity="",
                        description="",
                    )
                )
            if not 1 <= len(selected) <= 8:
                raise ValueError()
            if len({source["name"].casefold() for source in selected}) != len(selected):
                raise ValueError()
            # Reordering checkboxes does not reorder or replace retained cameras.
            keep = {source["id"]: source for source in selected}
            selected = [
                keep.pop(source["id"])
                for source in config["sources"]
                if source["id"] in keep
            ] + list(keep.values())
            if selected != config["sources"]:
                await current.client.request("config", {"sources": selected})
            await current.async_request_refresh()
            _, _, result = await catalog(current)
            connection.send_result(msg["id"], result)
            # Rebuild per-camera entities; the separate encoder and music continue.
            if selected != config["sources"]:
                hass.async_create_task(
                    hass.config_entries.async_reload(current.entry.entry_id),
                    eager_start=False,
                )
    except (ValueError, StudioError):
        connection.send_error(
            msg["id"], "cannot_apply", "Camera changes could not be applied"
        )


def setup(hass):
    websocket_api.async_register_command(hass, get_cameras)
    websocket_api.async_register_command(hass, update_cameras)
