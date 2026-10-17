from homeassistant.components.button import ButtonEntity

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioButton(entry.runtime_data, mode)
            for mode in ("preview", "stop", "compare")
        ]
    )


class StudioButton(StudioEntity, ButtonEntity):
    def __init__(self, c, mode):
        super().__init__(c, mode)
        self.mode = mode
        self._attr_translation_key = mode
        self._attr_icon = "mdi:movie-check-outline" if mode == "preview" else "mdi:stop"

    async def async_press(self):
        if self.mode == "compare":
            await self.coordinator.compare()
        elif self.mode == "preview":
            await self.coordinator.action("start", {"mode": "preview", "duration": 20})
        else:
            await self.coordinator.action("stop", {})
