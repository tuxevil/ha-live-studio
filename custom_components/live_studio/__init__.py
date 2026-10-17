"""Configure and control a separate Live Studio engine."""

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StudioAuthError, StudioClient, StudioError
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


class StudioCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=15),
            config_entry=entry,
        )
        self.entry = entry
        self.ai_lock = asyncio.Lock()
        self.ai_task = None
        self.last_ai_attempt = 0
        self.ai_error = None
        self.comparing = False
        self.ready = False
        self.client = StudioClient(
            async_get_clientsession(hass),
            entry.data["endpoint"],
            entry.data["api_token"],
        )

    async def _async_update_data(self):
        try:
            sensor = self.hass.states.get(self.entry.options.get("sensor_entity") or "")
            text = ""
            if sensor and sensor.state not in ("unknown", "unavailable"):
                text = f"{sensor.name}: {sensor.state} {sensor.attributes.get('unit_of_measurement','')}".strip()
            sun = self.hass.states.get("sun.sun")
            daylight = (
                (sun.state == "above_horizon")
                if sun and sun.state in ("above_horizon", "below_horizon")
                else None
            )
            await self.client.request(
                "metadata", {"sensor_text": text, "daylight": daylight}
            )
            result = {
                "status": await self.client.request("status"),
                "config": await self.client.request("config"),
            }
            # The timer is driven by the coordinator; no second polling loop.
            if (
                self.ready
                and self.entry.options.get("ai_enabled")
                and result["status"].get("selection", {}).get("mode") == "automatic"
                and result["status"]["state"] == "running"
                and time.monotonic() - self.last_ai_attempt
                >= result["config"].get("comparison_interval", 600)
                and (self.ai_task is None or self.ai_task.done())
            ):

                async def automatic_compare():
                    try:
                        await self.compare()
                    except HomeAssistantError:
                        pass

                self.ai_task = self.hass.async_create_task(
                    automatic_compare(), eager_start=False
                )
            return result
        except StudioAuthError as err:
            raise ConfigEntryAuthFailed("Check the Live Studio API token") from err
        except StudioError as err:
            raise UpdateFailed("Live Studio engine unavailable") from err

    def camera_entity(self, identity):
        return entity_registry.async_get(self.hass).async_get_entity_id(
            "camera", DOMAIN, f"{self.data['status']['id']}_view_{identity}"
        )

    async def compare(self):
        from .ai import compare

        await compare(self)

    async def close(self):
        self.ready = False
        if self.ai_task:
            self.ai_task.cancel()
            await asyncio.gather(self.ai_task, return_exceptions=True)

    async def action(self, path, data):
        try:
            await self.client.request(path, data)
        except StudioError as err:
            raise HomeAssistantError(
                "Live Studio could not complete the operation"
            ) from err
        await self.async_request_refresh()


async def async_setup_entry(hass, entry):
    coordinator = StudioCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.ready = True
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    await entry.runtime_data.close()
    # The engine deliberately continues when Core restarts or this entry unloads.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
