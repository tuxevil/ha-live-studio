from homeassistant.components.number import NumberEntity, NumberMode

from .entity import StudioEntity

SETTINGS = [
    ("minimum_margin", 1, 30, 1),
    ("day_bonus", 0, 15, 1),
    ("minimum_dwell", 0, 120, 60),
    ("comparison_interval", 1, 60, 60),
    ("confirmations", 1, 5, 1),
]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PolicyNumber(entry.runtime_data, *s) for s in SETTINGS])


class PolicyNumber(StudioEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1
    _attr_icon = "mdi:tune"

    def __init__(self, c, key, low, high, factor):
        super().__init__(c, key)
        self.key = key
        self.factor = factor
        self._attr_translation_key = key
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        if factor == 60:
            self._attr_native_unit_of_measurement = "min"

    @property
    def native_value(self):
        return self.coordinator.data["config"][self.key] / self.factor

    async def async_set_native_value(self, value):
        await self.coordinator.action("config", {self.key: int(value * self.factor)})
