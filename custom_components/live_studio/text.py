from homeassistant.components.text import TextEntity, TextMode

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioText(entry.runtime_data, k, n)
            for k, n in [("title", 100), ("ticker", 1200), ("cta", 200)]
        ]
    )


class StudioText(StudioEntity, TextEntity):
    _attr_mode = TextMode.TEXT

    def __init__(self, c, key, limit):
        super().__init__(c, key)
        self.key = key
        self._attr_translation_key = key
        self._attr_native_max = limit
        self._attr_native_min = 0

    @property
    def native_value(self):
        return self.coordinator.data["config"].get(self.key, "")

    async def async_set_value(self, value):
        await self.coordinator.action("config", {self.key: value})
