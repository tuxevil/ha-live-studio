from homeassistant.components.switch import SwitchEntity

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StudioStream(entry.runtime_data)])


class StudioStream(StudioEntity, SwitchEntity):
    _attr_translation_key = "stream"
    _attr_icon = "mdi:broadcast"

    def __init__(self, c):
        super().__init__(c, "stream")

    @property
    def is_on(self):
        s = self.coordinator.data["status"]
        return s["mode"] == "live" and s["state"] in ("starting", "running", "retrying")

    async def async_turn_on(self, **kwargs):
        await self.coordinator.action("start", {"mode": "live"})

    async def async_turn_off(self, **kwargs):
        await self.coordinator.action("stop", {})
