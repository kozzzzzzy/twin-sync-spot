"""Button platform for TwinSync Spot."""
from __future__ import annotations

import logging
from typing import Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_SYSTEM_STATE_UPDATED,
    SIGNAL_SPOT_STATE_UPDATED,
)
from .coordinator import TwinSyncSpot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up buttons for a spot."""
    spot: TwinSyncSpot = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Creating buttons for spot '%s'", spot.name)

    entities = [
        SpotCheckButton(spot, entry),
        SpotResetButton(spot, entry),
        SpotSnooze1hButton(spot, entry),
        SpotSnoozeTomorrowButton(spot, entry),
        SpotUnsnoozeButton(spot, entry),
    ]

    # Add global buttons only once
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("global_buttons_added"):
        _LOGGER.info("Creating global TwinSync Spot buttons")
        entities.append(CheckAllButton(hass))
        entities.append(ResetAllButton(hass))
        domain_data["global_buttons_added"] = True

    async_add_entities(entities)


class SpotBaseButton(ButtonEntity):
    """Base class for spot buttons."""

    _attr_has_entity_name = True

    def __init__(self, spot: TwinSyncSpot, entry: ConfigEntry) -> None:
        self._spot = spot
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        self._spot.add_listener(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        return self._spot.device_info


class SpotCheckButton(SpotBaseButton):
    """Button to check the spot now.

    Takes a camera snapshot and compares to the definition.
    """

    _attr_name = "Check"  # Text label, not just icon
    _attr_icon = "mdi:camera-iris"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_check"

    async def async_press(self) -> None:
        _LOGGER.info("Check button pressed for '%s'", self._spot.name)
        await self._spot.async_check(reason="button")


class SpotResetButton(SpotBaseButton):
    """Button to reset (mark as fixed).

    User confirms they've sorted the spot.
    Updates streak and clears to_sort list.
    """

    _attr_name = "Reset"  # "I've fixed it"
    _attr_icon = "mdi:check-bold"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_reset"

    async def async_press(self) -> None:
        _LOGGER.info("Reset button pressed for '%s'", self._spot.name)
        await self._spot.async_reset()


class SpotSnooze1hButton(SpotBaseButton):
    """Button to snooze for 1 hour.

    Pauses auto-checks and hides from "needs attention".
    """

    _attr_name = "Snooze 1h"
    _attr_icon = "mdi:sleep"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_snooze_1h"

    async def async_press(self) -> None:
        _LOGGER.info("Snooze 1h button pressed for '%s'", self._spot.name)
        await self._spot.async_snooze(minutes=60)


class SpotSnoozeTomorrowButton(SpotBaseButton):
    """Button to snooze until tomorrow.

    24-hour snooze for "I'll deal with it later" days.
    """

    _attr_name = "Later"  # Friendly name
    _attr_icon = "mdi:weather-night"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_snooze_tomorrow"

    async def async_press(self) -> None:
        _LOGGER.info("Snooze Tomorrow button pressed for '%s'", self._spot.name)
        await self._spot.async_snooze(minutes=1440)  # 24 hours


class SpotUnsnoozeButton(SpotBaseButton):
    """Button to cancel snooze.

    Re-enables checks and attention tracking.
    """

    _attr_name = "Unsnooze"
    _attr_icon = "mdi:alarm-off"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_unsnooze"

    async def async_press(self) -> None:
        _LOGGER.info("Unsnooze button pressed for '%s'", self._spot.name)
        await self._spot.async_unsnooze()


# =============================================================================
# GLOBAL BUTTONS
# =============================================================================


class GlobalBaseButton(ButtonEntity):
    """Base class for global buttons."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_added_to_hass(self) -> None:
        self._unsubscribers.append(
            async_dispatcher_connect(
                self._hass, SIGNAL_SYSTEM_STATE_UPDATED, self.async_write_ha_state
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        while self._unsubscribers:
            self._unsubscribers.pop()()

    def _get_spots(self) -> list[TwinSyncSpot]:
        return [
            spot
            for spot in self._hass.data.get(DOMAIN, {}).values()
            if isinstance(spot, TwinSyncSpot)
        ]


class CheckAllButton(GlobalBaseButton):
    """Button to check all spots at once."""

    _attr_name = "Check All Spots"
    _attr_icon = "mdi:camera-burst"
    _attr_unique_id = "twinsync_check_all"

    async def async_press(self) -> None:
        spots = self._get_spots()
        _LOGGER.info("Check All button pressed (%d spots)", len(spots))
        for spot in spots:
            await spot.async_check(reason="check_all")


class ResetAllButton(GlobalBaseButton):
    """Button to reset all spots at once."""

    _attr_name = "Reset All Spots"
    _attr_icon = "mdi:check-all"
    _attr_unique_id = "twinsync_reset_all"

    async def async_press(self) -> None:
        spots = self._get_spots()
        _LOGGER.info("Reset All button pressed (%d spots)", len(spots))
        for spot in spots:
            await spot.async_reset()
