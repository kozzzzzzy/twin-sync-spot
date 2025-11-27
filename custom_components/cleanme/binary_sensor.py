"""Binary sensor platform for TwinSync Spot."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    ATTR_DEFINITION,
    ATTR_VOICE,
    ATTR_CAMERA_ENTITY,
    ATTR_LAST_CHECK,
    ATTR_SNOOZED_UNTIL,
    ATTR_SPOT_COUNT,
    ATTR_READY,
    ATTR_CURRENT_STREAK,
    ATTR_TO_SORT_COUNT,
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
    """Set up binary sensors for a spot."""
    spot: TwinSyncSpot = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Creating binary sensors for spot '%s'", spot.name)

    entities = [
        SpotSortedBinarySensor(spot, entry),
        SpotNeedsAttentionBinarySensor(spot, entry),
        SpotSnoozedBinarySensor(spot, entry),
    ]

    # Add global sensors only once
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("global_binary_sensors_added"):
        _LOGGER.info("Creating global TwinSync Spot binary sensors")
        entities.append(SystemReadyBinarySensor(hass))
        entities.append(AllSortedBinarySensor(hass))
        domain_data["global_binary_sensors_added"] = True

    async_add_entities(entities)


class SpotBaseBinarySensor(BinarySensorEntity):
    """Base class for spot binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, spot: TwinSyncSpot, entry: ConfigEntry) -> None:
        self._spot = spot
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        self._spot.add_listener(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        return self._spot.device_info


class SpotSortedBinarySensor(SpotBaseBinarySensor):
    """Binary sensor: is the spot sorted (matching ready state)?

    ON = Sorted (green) - matches the user's definition
    OFF = Needs attention (red) - doesn't match
    """

    _attr_name = "Sorted"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:check-circle"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_sorted"

    @property
    def is_on(self) -> bool:
        """Return True if sorted (matches definition)."""
        return self._spot.state.sorted

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            ATTR_DEFINITION: self._spot.definition,
            ATTR_VOICE: self._spot.voice,
            ATTR_CAMERA_ENTITY: self._spot.camera_entity_id,
            ATTR_TO_SORT_COUNT: self._spot.state.to_sort_count,
            ATTR_CURRENT_STREAK: self._spot.state.current_streak,
        }

        if self._spot.state.last_checked:
            attrs[ATTR_LAST_CHECK] = self._spot.state.last_checked.isoformat()

        if self._spot.snooze_until:
            attrs[ATTR_SNOOZED_UNTIL] = self._spot.snooze_until.isoformat()

        return attrs


class SpotNeedsAttentionBinarySensor(SpotBaseBinarySensor):
    """Binary sensor: does the spot need attention?

    ON = Needs attention (and not snoozed)
    OFF = Either sorted, or snoozed
    """

    _attr_name = "Needs attention"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_needs_attention"

    @property
    def is_on(self) -> bool:
        """Return True if needs attention (not sorted and not snoozed)."""
        return self._spot.needs_attention


class SpotSnoozedBinarySensor(SpotBaseBinarySensor):
    """Binary sensor: is the spot snoozed?

    ON = Currently snoozed (checks paused)
    OFF = Active
    """

    _attr_name = "Snoozed"
    _attr_icon = "mdi:sleep"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_snoozed"

    @property
    def is_on(self) -> bool:
        """Return True if snoozed."""
        return self._spot.is_snoozed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._spot.snooze_until:
            return {ATTR_SNOOZED_UNTIL: self._spot.snooze_until.isoformat()}
        return {}


# =============================================================================
# GLOBAL BINARY SENSORS
# =============================================================================


class GlobalBaseBinarySensor(BinarySensorEntity):
    """Base class for global binary sensors."""

    _attr_has_entity_name = False  # Use full name for entity_id

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_added_to_hass(self) -> None:
        self._unsubscribers.append(
            async_dispatcher_connect(
                self._hass, SIGNAL_SYSTEM_STATE_UPDATED, self.async_write_ha_state
            )
        )
        self._unsubscribers.append(
            async_dispatcher_connect(
                self._hass, SIGNAL_SPOT_STATE_UPDATED, self.async_write_ha_state
            )
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        while self._unsubscribers:
            self._unsubscribers.pop()()

    def _get_spots(self) -> list[TwinSyncSpot]:
        """Get all spots."""
        return [
            spot
            for spot in self._hass.data.get(DOMAIN, {}).values()
            if isinstance(spot, TwinSyncSpot)
        ]


class SystemReadyBinarySensor(GlobalBaseBinarySensor):
    """Binary sensor: is the system ready?

    ON = At least one spot configured, dashboard generated
    OFF = No spots or dashboard error
    """

    _attr_name = "TwinSync Ready"
    _attr_icon = "mdi:check-circle"
    _attr_unique_id = "twinsync_ready"

    @property
    def is_on(self) -> bool:
        spots = self._get_spots()
        dashboard_state = self._hass.data.get(DOMAIN, {}).get("dashboard_state", {})

        has_spots = len(spots) > 0
        dashboard_ok = dashboard_state.get("dashboard_status") not in {"error", "unavailable"}

        return has_spots and dashboard_ok

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dashboard_state = self._hass.data.get(DOMAIN, {}).get("dashboard_state", {})
        return {
            ATTR_SPOT_COUNT: len(self._get_spots()),
            ATTR_READY: self.is_on,
        }


class AllSortedBinarySensor(GlobalBaseBinarySensor):
    """Binary sensor: are all spots sorted?

    ON = Every spot matches its definition
    OFF = At least one spot needs attention
    """

    _attr_name = "TwinSync All Sorted"
    _attr_icon = "mdi:home-heart"
    _attr_unique_id = "twinsync_all_sorted"

    @property
    def is_on(self) -> bool:
        spots = self._get_spots()
        if not spots:
            return False
        return all(s.state.sorted for s in spots)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        spots = self._get_spots()
        sorted_spots = [s.name for s in spots if s.state.sorted]
        needs_attention = [s.name for s in spots if not s.state.sorted]

        return {
            "sorted_spots": sorted_spots,
            "needs_attention": needs_attention,
            ATTR_SPOT_COUNT: len(spots),
        }
