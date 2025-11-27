"""Sensor platform for TwinSync Spot."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util.dt import as_local

from .const import (
    DOMAIN,
    ATTR_TO_SORT,
    ATTR_LOOKING_GOOD,
    ATTR_RECURRING_ITEMS,
    ATTR_STATUS,
    ATTR_ERROR_MESSAGE,
    ATTR_IMAGE_SIZE,
    ATTR_API_RESPONSE_TIME,
    ATTR_SPOT_COUNT,
    ATTR_SPOTS_NEEDING_ATTENTION,
    ATTR_ALL_SORTED,
    ATTR_DASHBOARD_PATH,
    ATTR_DASHBOARD_LAST_GENERATED,
    ATTR_DASHBOARD_LAST_ERROR,
    ATTR_DASHBOARD_STATUS,
    ATTR_READY,
    ATTR_CURRENT_STREAK,
    ATTR_LONGEST_STREAK,
    ATTR_SNOOZED_UNTIL,
    ATTR_DEFINITION,
    ATTR_VOICE,
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
    """Set up sensors for a spot."""
    spot: TwinSyncSpot = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Creating sensors for spot '%s'", spot.name)

    entities: list[SensorEntity] = [
        SpotToSortSensor(spot, entry),
        SpotLookingGoodSensor(spot, entry),
        SpotNotesSensor(spot, entry),
        SpotStreakSensor(spot, entry),
        SpotLastCheckSensor(spot, entry),
    ]

    # Add global sensors only once
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("global_sensors_added"):
        _LOGGER.info("Creating global TwinSync Spot sensors")
        entities.append(SystemStatusSensor(hass))
        entities.append(TotalSpotsSensor(hass))
        entities.append(SpotsNeedingAttentionSensor(hass))
        entities.append(NextScheduledCheckSensor(hass))
        domain_data["global_sensors_added"] = True

    async_add_entities(entities)


class SpotBaseSensor(SensorEntity):
    """Base class for spot sensors."""

    _attr_has_entity_name = True

    def __init__(self, spot: TwinSyncSpot, entry: ConfigEntry) -> None:
        self._spot = spot
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        self._spot.add_listener(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        return self._spot.device_info


class SpotToSortSensor(SpotBaseSensor):
    """Sensor showing items that need sorting.

    State: Count of items to sort
    Attributes: Full list with details
    """

    _attr_name = "To sort"
    _attr_icon = "mdi:clipboard-list"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_to_sort"

    @property
    def native_value(self) -> int:
        """Return count of items to sort."""
        return self._spot.state.to_sort_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed item list."""
        items = []
        recurring = []

        for item in self._spot.state.to_sort:
            item_dict = {
                "item": item.item,
                "location": item.location,
            }
            if item.recurring:
                item_dict["recurring"] = True
                item_dict["times_seen"] = item.recurring_count
                recurring.append(f"{item.item} ({item.recurring_count}x)")
            items.append(item_dict)

        return {
            ATTR_TO_SORT: items,
            ATTR_RECURRING_ITEMS: recurring,
            ATTR_STATUS: self._spot.state.status,
        }


class SpotLookingGoodSensor(SpotBaseSensor):
    """Sensor showing items that match the definition.

    State: Count of items looking good
    Attributes: Full list
    """

    _attr_name = "Looking good"
    _attr_icon = "mdi:check-circle"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_looking_good"

    @property
    def native_value(self) -> int:
        """Return count of items looking good."""
        return self._spot.state.looking_good_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return item list."""
        return {
            ATTR_LOOKING_GOOD: self._spot.state.looking_good,
        }


class SpotNotesSensor(SpotBaseSensor):
    """Sensor showing notes from the check.

    State: Main note (truncated to 255 chars)
    Attributes: All note fields, full text
    """

    _attr_name = "Notes"
    _attr_icon = "mdi:note-text"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_notes"

    @property
    def native_value(self) -> str | None:
        """Return main note, truncated for state."""
        note = self._spot.state.notes_main or "No notes yet"
        if len(note) > 250:
            return note[:247] + "..."
        return note

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all note fields."""
        return {
            "main": self._spot.state.notes_main,
            "pattern": self._spot.state.notes_pattern,
            "encouragement": self._spot.state.notes_encouragement,
            "full_text": self._spot.state.notes_main,  # For dashboard to read
        }


class SpotStreakSensor(SpotBaseSensor):
    """Sensor showing current streak.

    State: Current streak (days sorted)
    Attributes: Longest streak
    """

    _attr_name = "Streak"
    _attr_icon = "mdi:fire"
    _attr_native_unit_of_measurement = "days"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_streak"

    @property
    def native_value(self) -> int:
        """Return current streak."""
        return self._spot.state.current_streak

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return streak details."""
        return {
            ATTR_CURRENT_STREAK: self._spot.state.current_streak,
            ATTR_LONGEST_STREAK: self._spot.state.longest_streak,
        }


class SpotLastCheckSensor(SpotBaseSensor):
    """Sensor showing when spot was last checked.

    State: Timestamp
    Attributes: Check metadata
    """

    _attr_name = "Last check"
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_last_check"

    @property
    def native_value(self):
        """Return last check timestamp."""
        return self._spot.state.last_checked

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return check metadata."""
        attrs: dict[str, Any] = {
            ATTR_STATUS: "success" if not self._spot.state.last_error else "error",
            ATTR_DEFINITION: self._spot.definition,
            ATTR_VOICE: self._spot.voice,
        }

        if self._spot.state.last_error:
            attrs[ATTR_ERROR_MESSAGE] = self._spot.state.last_error

        if self._spot.state.image_size > 0:
            attrs[ATTR_IMAGE_SIZE] = self._spot.state.image_size

        if self._spot.state.api_response_time > 0:
            attrs[ATTR_API_RESPONSE_TIME] = round(self._spot.state.api_response_time, 2)

        if self._spot.snooze_until:
            attrs[ATTR_SNOOZED_UNTIL] = self._spot.snooze_until.isoformat()

        return attrs


# =============================================================================
# GLOBAL SENSORS
# =============================================================================


class GlobalBaseSensor(SensorEntity):
    """Base class for global sensors."""

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


class SystemStatusSensor(GlobalBaseSensor):
    """Overall system status."""

    _attr_name = "TwinSync Status"
    _attr_icon = "mdi:shield-check"
    _attr_unique_id = "twinsync_system_status"

    @property
    def native_value(self) -> str:
        spots = self._get_spots()
        dashboard_state = self._hass.data.get(DOMAIN, {}).get("dashboard_state", {})

        if not spots:
            return "needs_spot"

        if dashboard_state.get(ATTR_DASHBOARD_STATUS) == "error":
            return "dashboard_error"

        needing_attention = sum(1 for s in spots if s.needs_attention)
        if needing_attention > 0:
            return "needs_attention"

        return "all_sorted"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        spots = self._get_spots()
        dashboard_state = self._hass.data.get(DOMAIN, {}).get("dashboard_state", {})

        spots_needing = [s.name for s in spots if s.needs_attention]
        all_sorted = len(spots_needing) == 0 and len(spots) > 0

        last_gen = dashboard_state.get(ATTR_DASHBOARD_LAST_GENERATED)
        if last_gen:
            last_gen = as_local(last_gen).isoformat()

        return {
            ATTR_SPOT_COUNT: len(spots),
            ATTR_SPOTS_NEEDING_ATTENTION: spots_needing,
            ATTR_ALL_SORTED: all_sorted,
            ATTR_DASHBOARD_PATH: dashboard_state.get(ATTR_DASHBOARD_PATH),
            ATTR_DASHBOARD_LAST_GENERATED: last_gen,
            ATTR_DASHBOARD_LAST_ERROR: dashboard_state.get(ATTR_DASHBOARD_LAST_ERROR),
            ATTR_DASHBOARD_STATUS: dashboard_state.get(ATTR_DASHBOARD_STATUS),
            ATTR_READY: bool(spots) and dashboard_state.get(ATTR_DASHBOARD_STATUS) not in {"error", "unavailable"},
        }


class TotalSpotsSensor(GlobalBaseSensor):
    """Total configured spots."""

    _attr_name = "TwinSync Total Spots"
    _attr_icon = "mdi:home-group"
    _attr_unique_id = "twinsync_total_spots"
    _attr_native_unit_of_measurement = "spots"

    @property
    def native_value(self) -> int:
        return len(self._get_spots())


class SpotsNeedingAttentionSensor(GlobalBaseSensor):
    """Count of spots needing attention."""

    _attr_name = "TwinSync Spots Needing Attention"
    _attr_icon = "mdi:alert-circle"
    _attr_unique_id = "twinsync_spots_needing_attention"
    _attr_native_unit_of_measurement = "spots"

    @property
    def native_value(self) -> int:
        return sum(1 for s in self._get_spots() if s.needs_attention)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "spots": [s.name for s in self._get_spots() if s.needs_attention],
        }


class NextScheduledCheckSensor(GlobalBaseSensor):
    """Next scheduled check across all spots."""

    _attr_name = "TwinSync Next Scheduled Check"
    _attr_icon = "mdi:calendar-clock"
    _attr_unique_id = "twinsync_next_scheduled_check"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        next_checks = [
            s.next_scheduled_check
            for s in self._get_spots()
            if s.next_scheduled_check is not None
        ]
        return min(next_checks) if next_checks else None
