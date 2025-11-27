"""Number platform for TwinSync Spot."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    DEFAULT_CHECK_INTERVAL_HOURS,
)
from .coordinator import TwinSyncSpot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up number entities for a spot."""
    spot: TwinSyncSpot = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Creating number entities for spot '%s'", spot.name)

    entities = [
        SpotCheckIntervalNumber(spot, entry),
    ]

    async_add_entities(entities)


class SpotCheckIntervalNumber(NumberEntity):
    """Number entity for adjusting check interval.

    How many hours between automatic checks.
    """

    _attr_has_entity_name = True
    _attr_name = "Check interval"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = 168  # 1 week
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "hours"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, spot: TwinSyncSpot, entry: ConfigEntry) -> None:
        self._spot = spot
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        self._spot.add_listener(self.async_write_ha_state)

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_check_interval"

    @property
    def device_info(self) -> DeviceInfo:
        return self._spot.device_info

    @property
    def native_value(self) -> float:
        """Return current check interval."""
        return self._spot.check_interval_hours

    async def async_set_native_value(self, value: float) -> None:
        """Set new check interval."""
        _LOGGER.info("Setting check interval for '%s' to %s hours", self._spot.name, value)
        await self._spot.async_set_check_interval(value)
