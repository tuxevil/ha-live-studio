from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioStatus(entry.runtime_data),
            CurrentCamera(entry.runtime_data),
            ViewDecision(entry.runtime_data),
        ]
    )


class StudioStatus(StudioEntity, SensorEntity):
    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "stopped",
        "starting",
        "running",
        "retrying",
        "preview_completed",
        "error",
    ]
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


class CurrentCamera(StudioEntity, SensorEntity):
    _attr_translation_key = "current_camera"
    _attr_icon = "mdi:camera"

    def __init__(self, c):
        super().__init__(c, "current_camera")

    @property
    def native_value(self):
        return (self.coordinator.data["status"].get("current_camera") or {}).get("name")

    @property
    def extra_state_attributes(self):
        s = self.coordinator.data["status"]
        current = s.get("current_camera") or {}
        return {
            "camera_id": current.get("id"),
            "camera_entity": current.get("camera_entity")
            or self.coordinator.camera_entity(current.get("id")),
            "last_switch": s["selection"]["last_switch"],
            "mode": s["selection"]["mode"],
        }


class ViewDecision(StudioEntity, SensorEntity):
    _attr_translation_key = "view_decision"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "waiting",
        "manual",
        "idle",
        "no_video",
        "no_detail",
        "candidate",
        "selected",
        "failover",
        "keep",
        "comparing",
    ]
    _attr_icon = "mdi:camera-switch-outline"

    def __init__(self, c):
        super().__init__(c, "view_decision")

    @property
    def native_value(self):
        return (
            "comparing"
            if self.coordinator.comparing
            else self.coordinator.data["status"]["selection"]["decision"]
        )

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data["status"]["selection"]
        return {**d, "last_error": self.coordinator.ai_error}
