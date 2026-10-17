"""UI installation and engine settings; no YAML configuration required."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import StudioAuthError, StudioClient, StudioError, endpoint
from .const import DOMAIN
from .information import selected_sensors


class LiveStudioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def known_servers(self):
        result = {}
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator and coordinator.data["status"].get("server_id"):
                result.setdefault(entry.data["endpoint"], entry)
        return list(result.values())

    async def async_step_user(self, user_input=None):
        if not self.known_servers():
            self.goal = "connect"
            return await self.async_step_engine(user_input)
        return self.async_show_menu(
            step_id="user", menu_options=["create_live", "connect_live", "engine"]
        )

    async def async_step_create_live(self, user_input=None):
        self.goal = "create"
        return await self.async_step_server(user_input)

    async def async_step_connect_live(self, user_input=None):
        self.goal = "connect"
        return await self.async_step_server(user_input)

    async def async_step_server(self, user_input=None):
        servers = self.known_servers()
        if not servers:
            return await self.async_step_engine()
        if user_input or len(servers) == 1:
            entry = next(
                (
                    e
                    for e in servers
                    if user_input and e.entry_id == user_input["server"]
                ),
                servers[0],
            )
            self.connection = {k: entry.data[k] for k in ["endpoint", "api_token"]}
            return await self.after_connection()
        return self.async_show_form(
            step_id="server",
            data_schema=vol.Schema(
                {
                    vol.Required("server"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": e.entry_id, "label": e.data["endpoint"]}
                                for e in servers
                            ]
                        )
                    )
                }
            ),
        )

    def client(self):
        return StudioClient(
            async_get_clientsession(self.hass),
            self.connection["endpoint"],
            self.connection["api_token"],
        )

    async def async_step_engine(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.connection = {
                    "endpoint": endpoint(user_input["endpoint"]),
                    "api_token": user_input["api_token"],
                }
                server = await self.client().request("server", server=True)
                if "multiple_lives" not in server.get("capabilities", []):
                    raise StudioError()
                return await self.after_connection()
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except (StudioError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="engine",
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

    async def after_connection(self):
        if getattr(self, "goal", "connect") == "create":
            return await self.async_step_create()
        return await self.async_step_existing()

    async def async_step_existing(self, user_input=None):
        errors = {}
        try:
            if user_input:
                identity = user_input["live_id"]
                status = await self.client().request(
                    "lives/" + identity + "/status", server=True
                )
                return await self.finish(status, {})
            lives = (await self.client().request("lives", server=True))["lives"]
        except StudioError:
            return self.async_abort(reason="engine_unavailable")
        configured = {
            e.unique_id for e in self.hass.config_entries.async_entries(DOMAIN)
        }
        available = [x for x in lives if x.get("id") not in configured and x.get("id")]
        if not available:
            return await self.async_step_create()
        return self.async_show_form(
            step_id="existing",
            data_schema=vol.Schema(
                {
                    vol.Required("live_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": x["live_id"], "label": x["name"]}
                                for x in available
                            ]
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_create(self, user_input=None):
        errors = {}
        try:
            catalog = (await self.client().request("catalog", server=True))["sources"]
            catalog += getattr(self, "new_sources", [])
            self.catalog = {s["catalog_id"]: s for s in catalog}
            if not self.catalog:
                return await self.async_step_first_camera()
            if user_input is not None:
                choices = user_input["camera_ids"]
                if not 1 <= len(choices) <= 8:
                    raise ValueError()
                sources = [
                    {k: v for k, v in self.catalog[key].items() if k != "catalog_id"}
                    for key in choices
                ]
                # IDs are local to each live. Avoid collisions between source catalogs.
                for index, source in enumerate(sources):
                    source["id"] = "camera_" + choices[index].removeprefix("source_")
                status = await self.client().request(
                    "lives",
                    {"name": user_input["name"], "config": {"sources": sources}},
                    server=True,
                )
                return await self.finish(
                    status, {"sensor_entities": user_input.get("sensor_entities", [])}
                )
        except (StudioError, KeyError, ValueError):
            errors["base"] = "cannot_create"
        return self.async_show_form(
            step_id="create",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): vol.All(str, vol.Length(min=1, max=100)),
                    vol.Required("camera_ids"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            multiple=True,
                            options=[
                                {"value": k, "label": s["name"]}
                                for k, s in self.catalog.items()
                            ],
                        )
                    ),
                    vol.Optional("sensor_entities", default=[]): sensor_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_first_camera(self, user_input=None):
        errors = {}
        if user_input:
            import uuid
            from urllib.parse import urlsplit

            parsed = urlsplit(user_input["rtsp_url"])
            if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname:
                errors["base"] = "invalid_camera"
            else:
                identity = uuid.uuid4().hex[:12]
                self.new_sources = [
                    dict(
                        catalog_id=identity,
                        id="camera_" + identity,
                        name=user_input["name"],
                        rtsp_url=user_input["rtsp_url"],
                        camera_entity=user_input.get("camera_entity") or "",
                        description="",
                    )
                ]
                return await self.async_step_create()
        return self.async_show_form(
            step_id="first_camera",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required("rtsp_url"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional("camera_entity"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="camera")
                    ),
                }
            ),
            errors=errors,
        )

    async def finish(self, status, options):
        await self.async_set_unique_id(status["id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Live Studio · " + status["live_name"],
            data=dict(self.connection, live_id=status["live_id"]),
            options=options,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input:
            try:
                client = StudioClient(
                    async_get_clientsession(self.hass),
                    entry.data["endpoint"],
                    user_input["api_token"],
                    entry.data.get("live_id"),
                )
                status = await client.request("status")
                if status.get("id") != entry.unique_id:
                    raise StudioError()
                return self.updated_entry(entry, user_input)
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

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input:
            try:
                user_input["endpoint"] = endpoint(user_input["endpoint"])
                client = StudioClient(
                    async_get_clientsession(self.hass),
                    user_input["endpoint"],
                    user_input["api_token"],
                    user_input["live_id"],
                )
                status = await client.request("status")
                if status["id"] != entry.unique_id:
                    errors["base"] = "wrong_live"
                else:
                    return self.updated_entry(entry, user_input)
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except (StudioError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("endpoint", default=entry.data["endpoint"]): str,
                    vol.Required("api_token"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        "live_id", default=entry.data.get("live_id") or "default"
                    ): str,
                }
            ),
            errors=errors,
        )

    def updated_entry(self, entry, updates):
        if entry.update_listeners:
            return self.async_update_and_abort(entry, data_updates=updates)
        return self.async_update_reload_and_abort(entry, data_updates=updates)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LiveStudioOptionsFlow()


def sensor_selector():
    return vol.All(
        selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "binary_sensor"], multiple=True
            )
        ),
        vol.Length(max=8),
    )


class LiveStudioOptionsFlow(config_entries.OptionsFlow):
    @property
    def coordinator(self):
        return self.config_entry.runtime_data

    def current(self):
        return self.coordinator.data["config"]

    def saved(self, **updates):
        keys = {
            "sensor_entity",
            "sensor_entities",
            "ai_enabled",
            "ai_provider",
            "ai_model",
        }
        data = {k: v for k, v in self.config_entry.options.items() if k in keys}
        data.update(updates)
        if "sensor_entities" in data:
            data.pop("sensor_entity", None)
        return self.async_create_entry(title="", data=data)

    async def apply(self, patch, **updates):
        changed = {k: v for k, v in patch.items() if self.current().get(k) != v}
        if changed:
            await self.coordinator.client.request("config", changed)
        return self.saved(**updates)

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "information",
                "cameras",
                "video",
                "overlays",
                "automation",
                "destination",
                "delete_live",
            ],
        )

    async def async_step_cameras(self, user_input=None):
        sources = self.current()["sources"]
        items = []
        if len(sources) < 8:
            items.extend(["camera_pick", "camera_add"])
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
                return await self.apply(user_input)
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

    async def async_step_information(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                name = user_input["name"]
                status = self.coordinator.data["status"]
                if name != status.get("live_name"):
                    await self.coordinator.client.request(
                        "lives/" + status.get("live_id", "default"),
                        {"name": name},
                        server=True,
                        method="PATCH",
                    )
                return self.saved(
                    sensor_entities=user_input.get("sensor_entities", []),
                    sensor_entity="",
                )
            except StudioError:
                errors["base"] = "cannot_apply"
        return self.async_show_form(
            step_id="information",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name",
                        default=self.coordinator.data["status"].get(
                            "live_name", self.config_entry.title
                        ),
                    ): str,
                    vol.Optional(
                        "sensor_entities",
                        default=selected_sensors(self.config_entry.options),
                    ): sensor_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_camera_pick(self, user_input=None):
        errors = {}
        try:
            catalog = (await self.coordinator.client.request("catalog", server=True))[
                "sources"
            ]
            choices = {s["catalog_id"]: s for s in catalog}
            current = {s["rtsp_url"]: s for s in self.current()["sources"]}
            if user_input:
                ids = user_input["camera_ids"]
                if not 1 <= len(ids) <= 8:
                    raise ValueError()
                sources = []
                for identity in ids:
                    source = choices[identity]
                    sources.append(
                        current.get(
                            source["rtsp_url"],
                            {
                                k: v
                                for k, v in dict(
                                    source,
                                    id="camera_" + identity.removeprefix("source_"),
                                ).items()
                                if k != "catalog_id"
                            },
                        )
                    )
                return await self.apply({"sources": sources})
        except (StudioError, ValueError, KeyError):
            errors["base"] = "cannot_apply"
            choices = locals().get("choices", {})
            current = locals().get("current", {})
        return self.async_show_form(
            step_id="camera_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "camera_ids",
                        default=[
                            k for k, s in choices.items() if s["rtsp_url"] in current
                        ],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            multiple=True,
                            options=[
                                {"value": k, "label": s["name"]}
                                for k, s in choices.items()
                            ],
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_destination(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input.get("destination_url", "").strip()
            clear = user_input.get("clear_destination", False)
            if url and clear:
                errors["base"] = "cannot_apply"
            else:
                try:
                    if url or clear:
                        await self.coordinator.client.request(
                            "destination", {"url": url}
                        )
                    return self.saved()
                except StudioError:
                    errors["base"] = "stop_live_first"
        return self.async_show_form(
            step_id="destination",
            data_schema=vol.Schema(
                {
                    vol.Optional("destination_url"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required("clear_destination", default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_delete_live(self, user_input=None):
        errors = {}
        if user_input and user_input.get("confirm_delete"):
            try:
                identity = self.coordinator.data["status"].get("live_id")
                if not identity:
                    raise StudioError()
                await self.coordinator.client.request(
                    "lives/" + identity, server=True, method="DELETE"
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_remove(self.config_entry.entry_id),
                    eager_start=False,
                )
                return self.async_abort(reason="live_deleted")
            except StudioError:
                errors["base"] = "stop_live_first"
        elif user_input is not None:
            errors["base"] = "confirm_delete"
        return self.async_show_form(
            step_id="delete_live",
            data_schema=vol.Schema(
                {vol.Required("confirm_delete", default=False): bool}
            ),
            errors=errors,
        )
