"""Authenticated overlay editor and bundled Lovelace card."""

from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry

from .api import StudioError
from .const import DOMAIN

PUBLIC_KEYS = {
    "broadcast_layout",
    "vertical_news",
    "sidebar_width",
    "weather_footer_enabled",
    "overlay_layout",
    "title",
    "ticker",
    "cta",
    "timezone",
    "cta_period",
    "cta_duration",
}


def coordinator(hass, entity_id):
    entity = entity_registry.async_get(hass).async_get(entity_id)
    entry = (
        hass.config_entries.async_get_entry(entity.config_entry_id) if entity else None
    )
    if not entry or entry.domain != DOMAIN or not getattr(entry, "runtime_data", None):
        raise ValueError("Choose an available Live Studio entity")
    return entry.runtime_data


def payload(current, status=None):
    return {
        "config": {
            key: value
            for key, value in current.data["config"].items()
            if key in PUBLIC_KEYS
        },
        "pending": (status or current.data["status"]).get("overlay_pending", False),
        "version": current.data["status"].get("version"),
        "preview_entity": entity_registry.async_get(current.hass).async_get_entity_id(
            "camera", DOMAIN, current.data["status"]["id"] + "_overlay_view"
        ),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "live_studio/overlay/get",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def get_overlay(hass, connection, msg):
    if not connection.user.is_admin and not connection.user.permissions.check_entity(
        msg["entity_id"], POLICY_READ
    ):
        connection.send_error(msg["id"], "unauthorized", "Entity access required")
        return
    try:
        current = coordinator(hass, msg["entity_id"])
        connection.send_result(
            msg["id"], payload(current, await current.client.request("status"))
        )
    except (ValueError, StudioError):
        connection.send_error(msg["id"], "not_found", "Live Studio is unavailable")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "live_studio/overlay/update",
        vol.Required("entity_id"): str,
        vol.Required("changes"): dict,
    }
)
@websocket_api.async_response
async def update_overlay(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access required"
        )
        return
    try:
        changes = msg["changes"]
        if not changes or changes.keys() - PUBLIC_KEYS:
            raise ValueError()
        current = coordinator(hass, msg["entity_id"])
        if "overlay_layout" not in current.data["config"]:
            raise ValueError()
        await current.client.request("config", changes)
        await current.async_request_refresh()
        connection.send_result(msg["id"], payload(current))
    except (ValueError, StudioError):
        connection.send_error(
            msg["id"], "cannot_apply", "Overlay changes could not be applied"
        )


async def setup(hass):
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/live_studio_static",
                str(Path(__file__).parent / "frontend"),
                cache_headers=False,
            )
        ]
    )
    frontend.add_extra_js_url(
        hass, "/live_studio_static/live-studio-overlay-card.js?v=0.5.0"
    )
    frontend.add_extra_js_url(
        hass, "/live_studio_static/live-studio-cameras-card.js?v=0.6.1"
    )
    frontend.add_extra_js_url(
        hass, "/live_studio_static/live-studio-news-card.js?v=0.7.1"
    )
    from .cameras import setup as setup_cameras

    setup_cameras(hass)
    websocket_api.async_register_command(hass, get_overlay)
    websocket_api.async_register_command(hass, update_overlay)
