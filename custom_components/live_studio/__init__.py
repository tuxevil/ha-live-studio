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
from .information import selected_sensors, sensor_text

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
            entry.data.get("live_id"),
        )

    async def _async_update_data(self):
        try:
            text = sensor_text(self.hass, self.entry.options)
            await self.client.request("metadata", {"sensor_text": text})
            result = {
                "status": await self.client.request("status"),
                "config": await self.client.request("config"),
            }
            result["status"]["information_sensors"] = selected_sensors(
                self.entry.options
            )
            name = result["status"].get("live_name")
            if name and self.entry.title != "Live Studio · " + name:
                self.hass.config_entries.async_update_entry(
                    self.entry, title="Live Studio · " + name
                )
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


async def async_setup(hass, config):
    from .overlay import setup

    await setup(hass)
    return True


async def async_setup_entry(hass, entry):
    coordinator = StudioCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    registry = entity_registry.async_get(hass)
    for registered in list(registry.entities.values()):
        if (
            registered.config_entry_id == entry.entry_id
            and registered.platform == DOMAIN
            and registered.domain == "number"
            and registered.unique_id.endswith("_day_bonus")
        ):
            registry.async_remove(registered.entity_id)
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


async def async_migrate_entry(hass, entry):
    if entry.version > 2:
        return False
    if entry.version == 1:
        options = dict(entry.options)
        options["sensor_entities"] = selected_sensors(options)
        options.pop("sensor_entity", None)
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True
