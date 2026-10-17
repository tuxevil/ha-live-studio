from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CurrentVideo(entry.runtime_data)])


class CurrentVideo(StudioEntity, BinarySensorEntity):
    _attr_translation_key = "current_video"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, c):
        super().__init__(c, "current_video")

    @property
    def is_on(self):
        return bool(self.coordinator.data["status"].get("current_video"))

    @property
    def extra_state_attributes(self):
        return {"cameras": self.coordinator.data["status"].get("cameras", {})}
