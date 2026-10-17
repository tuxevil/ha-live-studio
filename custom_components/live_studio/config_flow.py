"""UI installation and engine settings; no YAML configuration required."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import StudioAuthError, StudioClient, StudioError, endpoint
from .const import DOMAIN


class LiveStudioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["endpoint"] = endpoint(user_input["endpoint"])
                client = StudioClient(
                    async_get_clientsession(self.hass),
                    user_input["endpoint"],
                    user_input["api_token"],
                )
                status = await client.request("status")
                if not isinstance(status.get("id"), str) or not status["id"]:
                    raise StudioError()
                await self.async_set_unique_id(status["id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Live Studio", data=user_input)
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except (StudioError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("endpoint"): str,
                    vol.Required("api_token"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input:
            entry = self._get_reauth_entry()
            try:
                client = StudioClient(
                    async_get_clientsession(self.hass),
                    entry.data["endpoint"],
                    user_input["api_token"],
                )
                status = await client.request("status")
                if status.get("id") != entry.unique_id:
                    raise StudioError()
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except StudioError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("api_token"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LiveStudioOptionsFlow()


class LiveStudioOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        coordinator = self.config_entry.runtime_data
        current = {**self.config_entry.options, **coordinator.data["config"]}
        errors = {}
        if user_input is not None:
            try:
                patch = {
                    k: v
                    for k, v in user_input.items()
                    if k != "sensor_entity" and v != coordinator.data["config"].get(k)
                }
                if patch:
                    await coordinator.client.request("config", patch)
                return self.async_create_entry(title="", data=user_input)
            except StudioError:
                errors["base"] = "cannot_apply"
            current.update(user_input)
        fields = {
            vol.Required(
                "rtsp_url", default=current.get("rtsp_url", "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                "music_directory",
                default=current.get("music_directory", "/share/stream_music"),
            ): str,
            vol.Required("title", default=current.get("title", "Live Studio")): str,
            vol.Required("show_clock", default=current.get("show_clock", True)): bool,
            vol.Required(
                "timezone", default=current.get("timezone", self.hass.config.time_zone)
            ): str,
            vol.Required("ticker", default=current.get("ticker", "")): str,
            vol.Required("cta", default=current.get("cta", "Like and subscribe")): str,
        }
        for name, lo, hi, default in [
            ("width", 640, 3840, 1920),
            ("height", 360, 2160, 1080),
            ("fps", 5, 30, 15),
            ("threads", 1, 8, 2),
            ("bitrate_kbps", 500, 15000, 3000),
            ("cta_period", 60, 7200, 600),
            ("cta_duration", 3, 60, 12),
        ]:
            fields[vol.Required(name, default=current.get(name, default))] = vol.All(
                vol.Coerce(int), vol.Range(min=lo, max=hi)
            )
        fields[
            vol.Optional(
                "sensor_entity",
                description={"suggested_value": current.get("sensor_entity")},
            )
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        )
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields), errors=errors
        )
