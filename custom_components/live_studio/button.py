from homeassistant.components.button import ButtonEntity

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [StudioButton(entry.runtime_data, mode) for mode in ("preview", "stop")]
    )


class StudioButton(StudioEntity, ButtonEntity):
    def __init__(self, c, mode):
        super().__init__(c, mode)
        self.mode = mode
        self._attr_translation_key = mode
        self._attr_icon = "mdi:movie-check-outline" if mode == "preview" else "mdi:stop"

    async def async_press(self):
        (
            await self.coordinator.action("start", {"mode": "preview", "duration": 20})
            if self.mode == "preview"
            else await self.coordinator.action("stop", {})
        )
