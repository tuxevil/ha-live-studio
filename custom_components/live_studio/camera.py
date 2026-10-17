from homeassistant.components.camera import Camera

from .api import StudioError
from .entity import StudioEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(
        [StudioCamera(c, None)]
        + (
            [StudioCamera(c, None, overlay=True)]
            if "overlay_layout" in c.data["config"]
            else []
        )
        + [StudioCamera(c, s) for s in c.data["config"]["sources"]]
    )


class StudioCamera(StudioEntity, Camera):
    _attr_is_streaming = False

    def __init__(self, c, source, overlay=False):
        Camera.__init__(self)
        StudioEntity.__init__(
            self,
            c,
            (
                "overlay_view"
                if overlay
                else ("view_" + source["id"] if source else "current_view")
            ),
        )
        self.source = source
        self.overlay = overlay
        if overlay:
            self._attr_translation_key = "overlay_view"
        elif source:
            self._attr_name = source["name"]
        else:
            self._attr_translation_key = "current_view"

    @property
    def source_id(self):
        return (
            self.source["id"]
            if self.source
            else self.coordinator.data["status"]["selection"]["camera_id"]
        )

    @property
    def available(self):
        return (
            super().available
            and self.source_id is not None
            and self.coordinator.data["status"]
            .get("cameras", {})
            .get(self.source_id, {})
            .get("healthy")
            is not False
        )

    @property
    def extra_state_attributes(self):
        source = next(
            (
                s
                for s in self.coordinator.data["config"]["sources"]
                if s["id"] == self.source_id
            ),
            {},
        )
        return {
            "source_id": self.source_id,
            "source_camera": source.get("camera_entity")
            or self.coordinator.camera_entity(self.source_id),
        }

    async def async_camera_image(self, width=None, height=None):
        if self.source_id is None:
            return None
        try:
            return await self.coordinator.client.image(
                None if self.overlay else self.source_id
            )
        except StudioError:
            return None
