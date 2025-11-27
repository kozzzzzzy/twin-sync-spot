"""Select platform for TwinSync Spot."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    VOICES,
    DEFAULT_VOICE,
)
from .coordinator import TwinSyncSpot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up select entities for a spot."""
    spot: TwinSyncSpot = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Creating select entities for spot '%s'", spot.name)

    entities = [
        SpotVoiceSelect(spot, entry),
    ]

    async_add_entities(entities)


class SpotVoiceSelect(SelectEntity):
    """Select entity for choosing the voice style.

    Changes how the AI communicates about the spot.
    """

    _attr_has_entity_name = True
    _attr_name = "Voice"
    _attr_icon = "mdi:account-voice"

    def __init__(self, spot: TwinSyncSpot, entry: ConfigEntry) -> None:
        self._spot = spot
        self._entry_id = entry.entry_id

        # Build options from VOICES dict
        self._attr_options = list(VOICES.keys())

    async def async_added_to_hass(self) -> None:
        self._spot.add_listener(self.async_write_ha_state)

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_voice"

    @property
    def device_info(self) -> DeviceInfo:
        return self._spot.device_info

    @property
    def current_option(self) -> str:
        """Return current voice."""
        return self._spot.voice

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return voice details."""
        voice_config = VOICES.get(self._spot.voice, VOICES[DEFAULT_VOICE])
        return {
            "voice_name": voice_config["name"],
            "voice_description": voice_config["description"],
        }

    async def async_select_option(self, option: str) -> None:
        """Set new voice."""
        if option not in VOICES:
            _LOGGER.warning("Invalid voice '%s' for spot '%s'", option, self._spot.name)
            return

        _LOGGER.info("Setting voice for '%s' to '%s'", self._spot.name, option)
        await self._spot.async_set_voice(option)
