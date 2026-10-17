async def async_get_config_entry_diagnostics(hass, entry):
    # Configuration includes RTSP credentials: include only non-sensitive status.
    return {"status": entry.runtime_data.data["status"]}
