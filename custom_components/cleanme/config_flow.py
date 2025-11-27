"""Config flow for TwinSync Spot.

Two-step flow:
1. Pick name, camera, spot type, voice
2. Edit definition (pre-filled from template), set frequency, enter API key
"""
from __future__ import annotations

from typing import Any
import logging
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, selector
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_CAMERA_ENTITY,
    CONF_API_KEY,
    CONF_SPOT_TYPE,
    CONF_DEFINITION,
    CONF_VOICE,
    CONF_CUSTOM_VOICE_PROMPT,
    CONF_CHECK_FREQUENCY,
    SpotType,
    SPOT_TYPE_LABELS,
    SPOT_TEMPLATES,
    VOICE_OPTIONS,
    DEFAULT_VOICE,
    FREQUENCY_OPTIONS,
    FREQUENCY_MANUAL,
)
from .gemini_client import GeminiClient

_LOGGER = logging.getLogger(__name__)

# Global API key storage
STORAGE_KEY_CONFIG = "cleanme.config"
STORAGE_VERSION_CONFIG = 1


async def async_get_stored_api_key(hass) -> str | None:
    """Get stored API key from global storage."""
    store = Store(hass, STORAGE_VERSION_CONFIG, STORAGE_KEY_CONFIG)
    data = await store.async_load()
    return data.get("api_key") if data else None


async def async_store_api_key(hass, api_key: str) -> None:
    """Store API key for future spots."""
    store = Store(hass, STORAGE_VERSION_CONFIG, STORAGE_KEY_CONFIG)
    data = await store.async_load() or {}
    data["api_key"] = api_key
    await store.async_save(data)


class TwinSyncSpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TwinSync Spot."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: Pick name, camera, spot type, voice."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store data and move to step 2
            self._data = user_input
            return await self.async_step_definition()

        # Build spot type options (value -> label)
        spot_type_options = {t.value: SPOT_TYPE_LABELS[t] for t in SpotType}

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_CAMERA_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="camera")
                ),
                vol.Required(CONF_SPOT_TYPE, default=SpotType.CUSTOM.value): vol.In(
                    spot_type_options
                ),
                vol.Required(CONF_VOICE, default=DEFAULT_VOICE): vol.In(VOICE_OPTIONS),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "1/2",
            },
        )

    async def async_step_definition(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2: Edit definition, set frequency, enter API key."""
        errors: dict[str, str] = {}

        # Get stored API key for pre-filling
        stored_api_key = await async_get_stored_api_key(self.hass)

        if user_input is not None:
            # Merge with step 1 data
            self._data.update(user_input)

            # Validate API key
            api_key = self._data[CONF_API_KEY]
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = GeminiClient(api_key)

            _LOGGER.info("Validating Gemini API key...")
            is_valid = await client.validate_api_key(session)

            if not is_valid:
                _LOGGER.error("API key validation failed")
                errors["base"] = "invalid_api_key"
            else:
                _LOGGER.info("API key validated successfully")

                # Store API key for future spots
                await async_store_api_key(self.hass, api_key)

                # Create unique ID
                name = self._data[CONF_NAME]
                unique_id = f"{DOMAIN}_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                _LOGGER.info("Creating spot '%s'", name)

                return self.async_create_entry(
                    title=name,
                    data=self._data,
                )

        # Get template for selected spot type
        spot_type_str = self._data.get(CONF_SPOT_TYPE, SpotType.CUSTOM.value)
        try:
            spot_type = SpotType(spot_type_str)
        except ValueError:
            spot_type = SpotType.CUSTOM

        template = SPOT_TEMPLATES.get(spot_type, SPOT_TEMPLATES[SpotType.CUSTOM])

        # Check if custom voice was selected
        show_custom_prompt = self._data.get(CONF_VOICE) == "custom"

        schema_dict: dict[vol.Marker, Any] = {
            vol.Required(CONF_DEFINITION, default=template): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True, type="text")
            ),
            vol.Required(CONF_CHECK_FREQUENCY, default=FREQUENCY_MANUAL): vol.In(
                FREQUENCY_OPTIONS
            ),
            vol.Required(CONF_API_KEY, default=stored_api_key or ""): str,
        }

        # Only show custom voice prompt field if custom voice selected
        if show_custom_prompt:
            schema_dict[vol.Optional(CONF_CUSTOM_VOICE_PROMPT, default="")] = selector.TextSelector(
                selector.TextSelectorConfig(multiline=True, type="text")
            )

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="definition",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "step": "2/2",
                "spot_name": self._data.get(CONF_NAME, "Spot"),
                "spot_type": SPOT_TYPE_LABELS.get(spot_type, "Custom"),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return TwinSyncSpotOptionsFlow(config_entry)


class TwinSyncSpotOptionsFlow(config_entries.OptionsFlow):
    """Handle options for existing spot."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle options flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate API key if changed
            api_key = user_input.get(CONF_API_KEY, "")
            old_api_key = self._entry.data.get(CONF_API_KEY, "")

            if api_key and api_key != old_api_key:
                session = aiohttp_client.async_get_clientsession(self.hass)
                client = GeminiClient(api_key)
                is_valid = await client.validate_api_key(session)

                if not is_valid:
                    errors["base"] = "invalid_api_key"

            if not errors:
                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, **user_input},
                )
                # Reload to apply changes
                await self.hass.config_entries.async_reload(self._entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        data = {**self._entry.data, **self._entry.options}

        # Build spot type options
        spot_type_options = {t.value: SPOT_TYPE_LABELS[t] for t in SpotType}

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=data.get(CONF_NAME, self._entry.title)): str,
                vol.Required(
                    CONF_CAMERA_ENTITY,
                    default=data.get(CONF_CAMERA_ENTITY, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="camera")
                ),
                vol.Required(
                    CONF_SPOT_TYPE,
                    default=data.get(CONF_SPOT_TYPE, SpotType.CUSTOM.value),
                ): vol.In(spot_type_options),
                vol.Required(
                    CONF_VOICE,
                    default=data.get(CONF_VOICE, DEFAULT_VOICE),
                ): vol.In(VOICE_OPTIONS),
                vol.Required(
                    CONF_DEFINITION,
                    default=data.get(CONF_DEFINITION, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True, type="text")
                ),
                vol.Required(
                    CONF_CHECK_FREQUENCY,
                    default=data.get(CONF_CHECK_FREQUENCY, FREQUENCY_MANUAL),
                ): vol.In(FREQUENCY_OPTIONS),
                vol.Required(
                    CONF_API_KEY,
                    default=data.get(CONF_API_KEY, ""),
                ): str,
                vol.Optional(
                    CONF_CUSTOM_VOICE_PROMPT,
                    default=data.get(CONF_CUSTOM_VOICE_PROMPT, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True, type="text")
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
