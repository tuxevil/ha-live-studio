from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StudioStatus(entry.runtime_data)])


class StudioStatus(StudioEntity, SensorEntity):
    _attr_translation_key = "status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:video-outline"

    def __init__(self, c):
        super().__init__(c, "status")

    @property
    def native_value(self):
        return self.coordinator.data["status"]["state"]

    @property
    def extra_state_attributes(self):
        return {
            k: v
            for k, v in self.coordinator.data["status"].items()
            if k not in ("id", "state")
        }
