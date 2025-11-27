"""Coordinator for TwinSync Spot.

Manages spot state, scheduling, and integrates with memory system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client, event
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.helpers.storage import Store
from homeassistant.util.dt import utcnow
from homeassistant.components.camera import async_get_image
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    CONF_CAMERA_ENTITY,
    CONF_API_KEY,
    CONF_VOICE,
    CONF_DEFINITION,
    CONF_SPOT_TYPE,
    CONF_CHECK_FREQUENCY,
    CONF_CUSTOM_VOICE_PROMPT,
    FREQUENCY_TO_RUNS,
    DEFAULT_VOICE,
    DEFAULT_CHECK_INTERVAL_HOURS,
    DEFAULT_OVERDUE_THRESHOLD_HOURS,
    SIGNAL_SPOT_STATE_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    SpotType,
)
from .gemini_client import GeminiClient, GeminiClientError
from .memory import MemoryManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class ToSortItem:
    """An item that needs sorting."""

    item: str
    location: str | None = None
    recurring: bool = False
    recurring_count: int = 0


@dataclass
class SpotState:
    """State data for a TwinSync Spot."""

    # Status
    sorted: bool = False  # True = matches ready state
    status: str = "unknown"  # "sorted" or "needs_attention"

    # Items
    to_sort: list[ToSortItem] = field(default_factory=list)
    looking_good: list[str] = field(default_factory=list)

    # Notes from AI
    notes_main: str | None = None
    notes_pattern: str | None = None
    notes_encouragement: str | None = None

    # Metadata
    last_error: str | None = None
    last_checked: datetime | None = None
    image_size: int = 0
    api_response_time: float = 0.0
    full_response: dict[str, Any] = field(default_factory=dict)

    # Streak (from memory)
    current_streak: int = 0
    longest_streak: int = 0

    @property
    def to_sort_count(self) -> int:
        return len(self.to_sort)

    @property
    def looking_good_count(self) -> int:
        return len(self.looking_good)

    @property
    def needs_attention(self) -> bool:
        return not self.sorted and self.to_sort_count > 0


class TwinSyncSpot:
    """One spot being tracked."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        name: str,
        data: dict[str, Any],
        memory_manager: MemoryManager,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._name = name
        self._memory_manager = memory_manager

        # Configuration
        self._camera_entity_id: str = data[CONF_CAMERA_ENTITY]
        self._voice: str = data.get(CONF_VOICE, DEFAULT_VOICE)
        self._custom_voice_prompt: str | None = data.get(CONF_CUSTOM_VOICE_PROMPT)
        self._definition: str = data.get(CONF_DEFINITION, "")
        self._spot_type: str = data.get(CONF_SPOT_TYPE, SpotType.CUSTOM.value)
        self._check_frequency: str = data.get(CONF_CHECK_FREQUENCY, "manual")

        # Calculate runs per day
        self._runs_per_day: int = FREQUENCY_TO_RUNS.get(self._check_frequency, 0)

        # API client
        api_key = data.get(CONF_API_KEY) or ""
        self._gemini_client = GeminiClient(api_key)

        # State
        self._state = SpotState()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_timer: Callable[[], None] | None = None
        self._snooze_until: datetime | None = None

        # Scheduling
        self._check_interval_hours: float = DEFAULT_CHECK_INTERVAL_HOURS
        self._next_scheduled_check: datetime | None = None

        # Persistence
        self._store: Store | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def camera_entity_id(self) -> str:
        return self._camera_entity_id

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def definition(self) -> str:
        return self._definition

    @property
    def spot_type(self) -> str:
        return self._spot_type

    @property
    def state(self) -> SpotState:
        return self._state

    @property
    def snooze_until(self) -> datetime | None:
        return self._snooze_until

    @property
    def is_snoozed(self) -> bool:
        if self._snooze_until is None:
            return False
        return utcnow() < self._snooze_until

    @property
    def needs_attention(self) -> bool:
        if self.is_snoozed:
            return False
        return self._state.needs_attention

    @property
    def is_overdue(self) -> bool:
        """Return True if spot hasn't been checked in too long."""
        if self._state.last_checked is None:
            return False
        hours_since = (utcnow() - self._state.last_checked).total_seconds() / 3600
        return hours_since > DEFAULT_OVERDUE_THRESHOLD_HOURS

    @property
    def next_scheduled_check(self) -> datetime | None:
        return self._next_scheduled_check

    @property
    def check_interval_hours(self) -> float:
        return self._check_interval_hours

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name=self._name,
            manufacturer="TwinSync",
            model="Spot Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_setup(self) -> None:
        """Set up the spot - load memory, start timers."""
        # Ensure memory is loaded
        await self._memory_manager.async_load()

        # Load streak from memory
        memory = self._memory_manager.get_memory(self.entry_id)
        self._state.current_streak = memory.patterns.current_streak
        self._state.longest_streak = memory.patterns.longest_streak

        # Set up auto timer if configured
        if self._runs_per_day > 0:
            self._setup_auto_timer()

    def _setup_auto_timer(self) -> None:
        """Set up periodic checks."""
        if self._unsub_timer:
            self._unsub_timer()

        interval_hours = 24 / float(self._runs_per_day)
        interval = timedelta(hours=interval_hours)
        self._next_scheduled_check = utcnow() + interval

        async def _handle(now: datetime) -> None:
            await self.async_check(reason="auto")
            self._next_scheduled_check = utcnow() + interval

        self._unsub_timer = event.async_track_time_interval(
            self.hass, _handle, interval
        )

    async def async_unload(self) -> None:
        """Clean up on unload."""
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        self._listeners.clear()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> None:
        """Register an entity listener."""
        self._listeners.append(listener)

    @callback
    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as err:
                _LOGGER.error("Error notifying listener: %s", err)
        async_dispatcher_send(self.hass, SIGNAL_SPOT_STATE_UPDATED)

    async def async_snooze(self, minutes: int) -> None:
        """Snooze checks for some minutes."""
        self._snooze_until = utcnow() + timedelta(minutes=minutes)
        _LOGGER.info("Spot '%s' snoozed for %d minutes", self._name, minutes)
        self._notify_listeners()

    async def async_unsnooze(self) -> None:
        """Cancel snooze."""
        self._snooze_until = None
        _LOGGER.info("Spot '%s' unsnoozed", self._name)
        self._notify_listeners()

    async def async_reset(self) -> None:
        """User marks spot as fixed/sorted."""
        self._state.sorted = True
        self._state.status = "sorted"
        self._state.to_sort = []
        self._state.notes_main = "Reset by user."
        self._state.notes_pattern = None
        self._state.notes_encouragement = None
        self._state.last_error = None

        # Record in memory
        await self._memory_manager.async_record_reset(self.entry_id)

        # Update streak from memory
        memory = self._memory_manager.get_memory(self.entry_id)
        self._state.current_streak = memory.patterns.current_streak
        self._state.longest_streak = memory.patterns.longest_streak

        _LOGGER.info(
            "Spot '%s' reset. Streak: %d (best: %d)",
            self._name,
            self._state.current_streak,
            self._state.longest_streak,
        )
        self._notify_listeners()

    async def async_set_voice(self, voice: str) -> None:
        """Change the voice."""
        self._voice = voice
        self._notify_listeners()

    async def async_set_check_interval(self, hours: float) -> None:
        """Set check interval."""
        hours = max(1.0, min(168.0, hours))  # 1 hour to 1 week
        self._check_interval_hours = hours
        self._notify_listeners()

    async def async_check(self, reason: str = "manual") -> None:
        """Run a check on this spot."""
        now = utcnow()

        # Skip if snoozed (for auto checks)
        if reason == "auto" and self.is_snoozed:
            _LOGGER.debug("Spot '%s' is snoozed, skipping auto check", self._name)
            return

        _LOGGER.info("Checking spot '%s' (reason: %s)", self._name, reason)

        # Capture camera image
        try:
            image = await async_get_image(self.hass, self._camera_entity_id)
            image_bytes = image.content
        except Exception as err:
            _LOGGER.error("Failed to capture image for '%s': %s", self._name, err)
            self._state.last_error = f"Camera error: {err}"
            self._state.sorted = False
            self._state.last_checked = now
            self._notify_listeners()
            return

        # Build memory context
        memory_context = self._memory_manager.build_memory_context(self.entry_id)

        # Get voice prompt
        if self._voice == "custom" and self._custom_voice_prompt:
            voice_prompt = self._custom_voice_prompt
        else:
            from .const import VOICES
            voice_config = VOICES.get(self._voice, VOICES[DEFAULT_VOICE])
            voice_prompt = voice_config["prompt"] or ""

        # Call Gemini
        session = aiohttp_client.async_get_clientsession(self.hass)

        try:
            result = await self._gemini_client.analyze_spot(
                session=session,
                image_bytes=image_bytes,
                spot_name=self._name,
                definition=self._definition,
                voice_prompt=voice_prompt,
                memory_context=memory_context,
            )
        except GeminiClientError as err:
            _LOGGER.error("Gemini error for '%s': %s", self._name, err)
            self._state.last_error = str(err)
            self._state.sorted = False
            self._state.last_checked = now
            self._notify_listeners()
            return
        except Exception as err:
            _LOGGER.exception("Unexpected error for '%s': %s", self._name, err)
            self._state.last_error = f"Unexpected error: {err}"
            self._state.sorted = False
            self._state.last_checked = now
            self._notify_listeners()
            return

        # Parse result and add recurring info
        status = result.get("status", "needs_attention")
        to_sort_raw = result.get("to_sort", [])
        looking_good = result.get("looking_good", [])
        notes = result.get("notes", {})

        # Build to_sort items with recurring flag from memory
        to_sort_items: list[ToSortItem] = []
        for item_data in to_sort_raw:
            if isinstance(item_data, dict):
                item_name = item_data.get("item", "")
                location = item_data.get("location")
            else:
                item_name = str(item_data)
                location = None

            # Check if recurring from memory (NOT from AI)
            recurring = self._memory_manager.is_item_recurring(self.entry_id, item_name)
            recurring_count = self._memory_manager.get_recurring_count(self.entry_id, item_name)

            to_sort_items.append(ToSortItem(
                item=item_name,
                location=location,
                recurring=recurring,
                recurring_count=recurring_count,
            ))

        # Update state
        self._state.sorted = status == "sorted"
        self._state.status = status
        self._state.to_sort = to_sort_items
        self._state.looking_good = looking_good
        self._state.notes_main = notes.get("main")
        self._state.notes_pattern = notes.get("pattern")
        self._state.notes_encouragement = notes.get("encouragement")
        self._state.last_error = None
        self._state.last_checked = now
        self._state.image_size = result.get("image_size", 0)
        self._state.api_response_time = result.get("api_response_time", 0.0)
        self._state.full_response = result

        # Record in memory
        item_names = [i.item for i in to_sort_items]
        await self._memory_manager.async_record_check(
            spot_id=self.entry_id,
            status=status,
            to_sort_items=item_names,
            looking_good_items=looking_good,
        )

        # Update streak from memory
        memory = self._memory_manager.get_memory(self.entry_id)
        self._state.current_streak = memory.patterns.current_streak
        self._state.longest_streak = memory.patterns.longest_streak

        _LOGGER.info(
            "Spot '%s' checked: status=%s, to_sort=%d, looking_good=%d",
            self._name,
            status,
            len(to_sort_items),
            len(looking_good),
        )

        self._notify_listeners()
