from homeassistant.components.select import SelectEntity

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CameraSelection(entry.runtime_data)])


class CameraSelection(StudioEntity, SelectEntity):
    _attr_translation_key = "camera_selection"
    _attr_icon = "mdi:camera-switch-outline"

    def __init__(self, c):
        super().__init__(c, "camera_selection")

    @property
    def options(self):
        return ["automatic"] + [
            s["name"] for s in self.coordinator.data["config"]["sources"]
        ]

    @property
    def current_option(self):
        status = self.coordinator.data["status"]
        if status["selection"]["mode"] == "automatic":
            return "automatic"
        return next(
            (
                s["name"]
                for s in self.coordinator.data["config"]["sources"]
                if s["id"] == status["selection"]["camera_id"]
            ),
            None,
        )

    async def async_select_option(self, option):
        if option == "automatic":
            await self.coordinator.action("selection", {"mode": "automatic"})
            return
        source = next(
            s for s in self.coordinator.data["config"]["sources"] if s["name"] == option
        )
        await self.coordinator.action(
            "selection", {"mode": "manual", "camera_id": source["id"]}
        )
