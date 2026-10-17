"""Configure and control a separate Live Studio engine."""

import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
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
        self.client = StudioClient(
            async_get_clientsession(hass),
            entry.data["endpoint"],
            entry.data["api_token"],
        )

    async def _async_update_data(self):
        try:
            sensor = self.hass.states.get(self.entry.options.get("sensor_entity", ""))
            text = ""
            if sensor and sensor.state not in ("unknown", "unavailable"):
                text = f"{sensor.name}: {sensor.state} {sensor.attributes.get('unit_of_measurement','')}".strip()
            await self.client.request("metadata", {"sensor_text": text})
            return {
                "status": await self.client.request("status"),
                "config": await self.client.request("config"),
            }
        except StudioAuthError as err:
            raise ConfigEntryAuthFailed("Check the Live Studio API token") from err
        except StudioError as err:
            raise UpdateFailed("Live Studio engine unavailable") from err

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
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    # The engine deliberately continues when Core restarts or this entry unloads.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
