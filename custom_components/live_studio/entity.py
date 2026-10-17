from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class StudioEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        identity = coordinator.data["status"]["id"]
        self._attr_unique_id = f"{identity}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=coordinator.entry.title,
            manufacturer="Tuxevil",
            model="Streaming engine",
            sw_version=coordinator.data["status"]["version"],
        )
