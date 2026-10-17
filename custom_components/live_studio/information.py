"""Per-live optional information, with lossless legacy sensor migration."""

MAX_SENSORS = 8


def selected_sensors(options):
    if "sensor_entities" in options:
        return list(dict.fromkeys(options["sensor_entities"]))[:MAX_SENSORS]
    legacy = options.get("sensor_entity")
    return [legacy] if legacy else []


def sensor_text(hass, options):
    parts = []
    for identity in selected_sensors(options):
        state = hass.states.get(identity)
        if state and state.state not in ("unknown", "unavailable"):
            unit = str(state.attributes.get("unit_of_measurement") or "")[:16]
            name = (state.name or identity)[:48]
            value = state.state[:48]
            parts.append(f"{name}: {value} {unit}".strip())
    return "  ·  ".join(parts)
