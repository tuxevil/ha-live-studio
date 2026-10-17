"""Discover Frigate camera entities through Home Assistant's camera API."""

import asyncio
import hashlib
from urllib.parse import urlsplit, urlunsplit

from homeassistant.components.camera import async_get_stream_source
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry


async def discover_sources(hass, known):
    registry = entity_registry.async_get(hass)
    entities = [
        entry
        for entry in registry.entities.values()
        if entry.platform == "frigate"
        and entry.entity_id.startswith("camera.")
        and not entry.disabled_by
    ]

    async def read(entry):
        try:
            url = await asyncio.wait_for(
                async_get_stream_source(hass, entry.entity_id), 3
            )
            parsed = urlsplit(url or "")
            if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname:
                return None
            return entry, url
        except (HomeAssistantError, TimeoutError, ValueError):
            return None

    available = [
        item
        for item in await asyncio.gather(*(read(entry) for entry in entities))
        if item
    ]
    # An external engine cannot resolve an HA app's internal Docker hostname.
    # Reuse an already configured, working restream origin for the SAME Frigate
    # entry and native origin; retain the camera API's path/query unchanged.
    by_entity = {source.get("camera_entity"): source for source in known}
    origins = {}
    for entry, url in available:
        if source := by_entity.get(entry.entity_id):
            native, working = urlsplit(url), urlsplit(source["rtsp_url"])
            if native.path == working.path and native.query == working.query:
                origins[(entry.config_entry_id, native.scheme, native.netloc)] = (
                    working.scheme,
                    working.netloc,
                )
    result = []
    for entry, url in available:
        native = urlsplit(url)
        if origin := origins.get((entry.config_entry_id, native.scheme, native.netloc)):
            url = urlunsplit(
                (origin[0], origin[1], native.path, native.query, native.fragment)
            )
        state = hass.states.get(entry.entity_id)
        name = (
            (state.attributes.get("friendly_name") if state else None)
            or entry.name
            or entry.original_name
            or entry.entity_id.removeprefix("camera.").replace("_", " ")
        )
        identity = "source_" + hashlib.sha256(url.encode()).hexdigest()[:16]
        result.append(
            dict(
                catalog_id=identity,
                id="camera_" + identity.removeprefix("source_"),
                name=name[:64],
                rtsp_url=url,
                camera_entity=entry.entity_id,
                description="",
            )
        )
    return result


async def catalog_sources(hass, client):
    """Use the same discovered library in dashboards and configuration flows."""
    known = (await client.request("catalog", server=True))["sources"]
    discovered = await discover_sources(hass, known)
    combined = {source["rtsp_url"]: source for source in known}
    for source in discovered:
        combined[source["rtsp_url"]] = source
    names = {source["rtsp_url"]: source["name"] for source in discovered}
    sources = sorted(
        combined.values(),
        key=lambda source: (source["rtsp_url"] not in names, source["name"].casefold()),
    )
    return sources, names
