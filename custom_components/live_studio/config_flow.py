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
    @property
    def coordinator(self):
        return self.config_entry.runtime_data

    def current(self):
        return self.coordinator.data["config"]

    def saved(self, **updates):
        keys = {"sensor_entity", "ai_enabled", "ai_provider", "ai_model"}
        data = {k: v for k, v in self.config_entry.options.items() if k in keys}
        data.update(updates)
        return self.async_create_entry(title="", data=data)

    async def apply(self, patch, **updates):
        changed = {k: v for k, v in patch.items() if self.current().get(k) != v}
        if changed:
            await self.coordinator.client.request("config", changed)
        return self.saved(**updates)

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init", menu_options=["cameras", "video", "overlays", "automation"]
        )

    async def async_step_cameras(self, user_input=None):
        sources = self.current()["sources"]
        items = []
        if len(sources) < 8:
            items.append("camera_add")
        if sources:
            items.append("camera_edit")
        if len(sources) > 1:
            items.append("camera_remove")
        return self.async_show_menu(step_id="cameras", menu_options=items)

    def picker(self):
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": s["id"], "label": s["name"]}
                    for s in self.current()["sources"]
                ]
            )
        )

    async def async_step_camera_add(self, user_input=None):
        self.editing = None
        return await self.async_step_camera_details(user_input)

    async def async_step_camera_edit(self, user_input=None):
        if user_input:
            self.editing = user_input["camera_id"]
            return await self.async_step_camera_details()
        return self.async_show_form(
            step_id="camera_edit",
            data_schema=vol.Schema({vol.Required("camera_id"): self.picker()}),
        )

    async def async_step_camera_details(self, user_input=None):
        import uuid

        sources = self.current()["sources"]
        current = dict(
            next((s for s in sources if s["id"] == getattr(self, "editing", None)), {})
        )
        errors = {}
        if user_input is not None:
            source = dict(
                id=current.get("id", "camera_" + uuid.uuid4().hex[:12]),
                name=user_input["name"],
                rtsp_url=user_input["rtsp_url"],
                camera_entity=user_input.get("camera_entity") or "",
                description=user_input.get("description", ""),
            )
            updated = (
                [source if s["id"] == source["id"] else s for s in sources]
                if current
                else sources + [source]
            )
            try:
                return await self.apply({"sources": updated})
            except StudioError:
                errors["base"] = "cannot_apply"
            current.update(user_input)
        return self.async_show_form(
            step_id="camera_details",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=current.get("name", "")): str,
                    vol.Required(
                        "rtsp_url", default=current.get("rtsp_url", "")
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(
                        "camera_entity",
                        description={
                            "suggested_value": current.get("camera_entity") or None
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="camera")
                    ),
                    vol.Required(
                        "description", default=current.get("description", "")
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_camera_remove(self, user_input=None):
        errors = {}
        if user_input:
            sources = [
                s
                for s in self.current()["sources"]
                if s["id"] != user_input["camera_id"]
            ]
            if not sources:
                errors["base"] = "cannot_apply"
            else:
                try:
                    return await self.apply({"sources": sources})
                except StudioError:
                    errors["base"] = "cannot_apply"
        return self.async_show_form(
            step_id="camera_remove",
            data_schema=vol.Schema({vol.Required("camera_id"): self.picker()}),
            errors=errors,
        )

    async def async_step_video(self, user_input=None):
        current = self.current()
        errors = {}
        if user_input is not None:
            try:
                return await self.apply(user_input)
            except StudioError:
                errors["base"] = "cannot_apply"
        fields = {
            vol.Required("music_directory", default=current["music_directory"]): str
        }
        for name, low, high in [
            ("width", 640, 3840),
            ("height", 360, 2160),
            ("fps", 5, 30),
            ("threads", 1, 8),
            ("bitrate_kbps", 500, 15000),
        ]:
            fields[vol.Required(name, default=current[name])] = vol.All(
                vol.Coerce(int), vol.Range(min=low, max=high)
            )
        return self.async_show_form(
            step_id="video", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_overlays(self, user_input=None):
        current = self.current()
        errors = {}
        if user_input is not None:
            try:
                return await self.apply(
                    {k: v for k, v in user_input.items() if k != "sensor_entity"},
                    sensor_entity=user_input.get("sensor_entity") or "",
                )
            except StudioError:
                errors["base"] = "cannot_apply"
        fields = {
            vol.Required(k, default=current[k]): str
            for k in ["title", "timezone", "ticker", "cta", "no_signal_text"]
        }
        fields.update(
            {
                vol.Required(k, default=current[k]): bool
                for k in ["show_clock", "show_camera_name"]
            }
        )
        for key, low, high in [("cta_period", 60, 7200), ("cta_duration", 3, 60)]:
            fields[vol.Required(key, default=current[key])] = vol.All(
                vol.Coerce(int), vol.Range(min=low, max=high)
            )
        fields[
            vol.Optional(
                "sensor_entity",
                description={
                    "suggested_value": self.config_entry.options.get("sensor_entity")
                    or None
                },
            )
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        )
        return self.async_show_form(
            step_id="overlays", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_automation(self, user_input=None):
        current = self.current()
        options = self.config_entry.options
        errors = {}
        if user_input is not None:
            enabled = user_input.get("ai_enabled", False)
            provider = user_input.get("ai_provider")
            model = user_input.get("ai_model", "").strip()
            if enabled and (
                not provider
                or not model
                or not self.hass.services.has_service("llmvision", "image_analyzer")
            ):
                errors["base"] = "missing_ai_provider"
            else:
                patch = {k: v for k, v in user_input.items() if not k.startswith("ai_")}
                patch["minimum_dwell"] = patch.pop("minimum_dwell_minutes") * 60
                patch["comparison_interval"] = (
                    patch.pop("comparison_interval_minutes") * 60
                )
                try:
                    return await self.apply(
                        patch,
                        ai_enabled=enabled,
                        ai_provider=provider or "",
                        ai_model=model,
                    )
                except StudioError:
                    errors["base"] = "cannot_apply"
        fields = {
            vol.Required("ai_enabled", default=options.get("ai_enabled", False)): bool,
            vol.Optional(
                "ai_provider",
                description={"suggested_value": options.get("ai_provider") or None},
            ): selector.ConfigEntrySelector(
                selector.ConfigEntrySelectorConfig(integration="llmvision")
            ),
            vol.Required("ai_model", default=options.get("ai_model", "")): str,
        }
        if current["sources"]:
            fields[
                vol.Required("preferred_camera", default=current["preferred_camera"])
            ] = self.picker()
        for key, low, high, value in [
            ("minimum_margin", 1, 30, current["minimum_margin"]),
            ("day_bonus", 0, 15, current["day_bonus"]),
            ("confirmations", 1, 5, current["confirmations"]),
            ("minimum_dwell_minutes", 0, 120, current["minimum_dwell"] // 60),
            (
                "comparison_interval_minutes",
                1,
                60,
                current["comparison_interval"] // 60,
            ),
        ]:
            fields[vol.Required(key, default=value)] = vol.All(
                vol.Coerce(int), vol.Range(min=low, max=high)
            )
        return self.async_show_form(
            step_id="automation", data_schema=vol.Schema(fields), errors=errors
        )
