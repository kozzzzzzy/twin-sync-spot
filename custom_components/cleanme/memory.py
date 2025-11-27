"""Memory system for TwinSync Spot.

Tracks check history and calculates patterns over time.
This is the killer feature - remembering what keeps showing up.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any
from collections import Counter
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util.dt import utcnow, as_local

from .const import STORAGE_KEY_MEMORY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

# How many days of history to keep
MEMORY_RETENTION_DAYS = 30

# Minimum appearances to be considered "recurring"
RECURRING_THRESHOLD = 3


@dataclass
class CheckRecord:
    """Record of a single check."""

    timestamp: str  # ISO format
    status: str  # "sorted" or "needs_attention"
    to_sort_items: list[str] = field(default_factory=list)
    looking_good_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckRecord":
        return cls(
            timestamp=data.get("timestamp", ""),
            status=data.get("status", "needs_attention"),
            to_sort_items=data.get("to_sort_items", []),
            looking_good_items=data.get("looking_good_items", []),
        )


@dataclass
class SpotPatterns:
    """Calculated patterns from check history."""

    # Items that keep showing up: {"coffee mug": 12, "papers": 8}
    recurring_items: dict[str, int] = field(default_factory=dict)

    # Time patterns
    usually_sorted_by: str | None = None  # "10:00 AM" - most common time spot is sorted
    worst_day: str | None = None  # "Monday" - day with most needs_attention
    best_day: str | None = None  # "Sunday" - day with most sorted

    # Streaks
    current_streak: int = 0  # Consecutive days ending in sorted state
    longest_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpotPatterns":
        return cls(
            recurring_items=data.get("recurring_items", {}),
            usually_sorted_by=data.get("usually_sorted_by"),
            worst_day=data.get("worst_day"),
            best_day=data.get("best_day"),
            current_streak=data.get("current_streak", 0),
            longest_streak=data.get("longest_streak", 0),
        )


@dataclass
class SpotMemory:
    """Complete memory for a spot."""

    spot_id: str
    checks: list[CheckRecord] = field(default_factory=list)
    patterns: SpotPatterns = field(default_factory=SpotPatterns)
    total_resets: int = 0
    last_reset: str | None = None  # ISO format

    def to_dict(self) -> dict[str, Any]:
        return {
            "spot_id": self.spot_id,
            "checks": [c.to_dict() for c in self.checks],
            "patterns": self.patterns.to_dict(),
            "total_resets": self.total_resets,
            "last_reset": self.last_reset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpotMemory":
        checks = [CheckRecord.from_dict(c) for c in data.get("checks", [])]
        patterns = SpotPatterns.from_dict(data.get("patterns", {}))
        return cls(
            spot_id=data.get("spot_id", ""),
            checks=checks,
            patterns=patterns,
            total_resets=data.get("total_resets", 0),
            last_reset=data.get("last_reset"),
        )


class MemoryManager:
    """Manages memory for all spots with persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY_MEMORY)
        self._memories: dict[str, SpotMemory] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load all memories from storage."""
        if self._loaded:
            return

        data = await self._store.async_load()
        if data:
            for spot_id, memory_data in data.get("spots", {}).items():
                self._memories[spot_id] = SpotMemory.from_dict(memory_data)
            _LOGGER.debug("Loaded memory for %d spots", len(self._memories))
        self._loaded = True

    async def async_save(self) -> None:
        """Save all memories to storage."""
        data = {
            "spots": {
                spot_id: memory.to_dict()
                for spot_id, memory in self._memories.items()
            }
        }
        await self._store.async_save(data)

    def get_memory(self, spot_id: str) -> SpotMemory:
        """Get or create memory for a spot."""
        if spot_id not in self._memories:
            self._memories[spot_id] = SpotMemory(spot_id=spot_id)
        return self._memories[spot_id]

    async def async_record_check(
        self,
        spot_id: str,
        status: str,
        to_sort_items: list[str],
        looking_good_items: list[str],
    ) -> None:
        """Record a check result and recalculate patterns."""
        memory = self.get_memory(spot_id)

        # Create check record
        record = CheckRecord(
            timestamp=utcnow().isoformat(),
            status=status,
            to_sort_items=to_sort_items,
            looking_good_items=looking_good_items,
        )

        # Add to history
        memory.checks.append(record)

        # Prune old checks (keep last 30 days)
        cutoff = utcnow() - timedelta(days=MEMORY_RETENTION_DAYS)
        memory.checks = [
            c for c in memory.checks
            if datetime.fromisoformat(c.timestamp) > cutoff
        ]

        # Recalculate patterns
        self._calculate_patterns(memory)

        # Save
        await self.async_save()

        _LOGGER.debug(
            "Recorded check for %s: status=%s, to_sort=%d items, history=%d checks",
            spot_id,
            status,
            len(to_sort_items),
            len(memory.checks),
        )

    async def async_record_reset(self, spot_id: str) -> None:
        """Record that user manually reset (fixed) the spot."""
        memory = self.get_memory(spot_id)
        memory.total_resets += 1
        memory.last_reset = utcnow().isoformat()

        # Update streak
        memory.patterns.current_streak += 1
        if memory.patterns.current_streak > memory.patterns.longest_streak:
            memory.patterns.longest_streak = memory.patterns.current_streak

        await self.async_save()

    def _calculate_patterns(self, memory: SpotMemory) -> None:
        """Calculate patterns from check history."""
        if not memory.checks:
            return

        # Count item occurrences
        item_counter: Counter[str] = Counter()
        for check in memory.checks:
            for item in check.to_sort_items:
                # Normalize item name (lowercase, strip)
                normalized = item.lower().strip()
                item_counter[normalized] += 1

        # Keep items that appear at least RECURRING_THRESHOLD times
        memory.patterns.recurring_items = {
            item: count
            for item, count in item_counter.most_common(10)
            if count >= RECURRING_THRESHOLD
        }

        # Calculate day patterns
        day_status: dict[str, list[str]] = {
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": [],
            "Saturday": [],
            "Sunday": [],
        }

        sorted_times: list[datetime] = []

        for check in memory.checks:
            try:
                dt = datetime.fromisoformat(check.timestamp)
                local_dt = as_local(dt)
                day_name = local_dt.strftime("%A")
                day_status[day_name].append(check.status)

                if check.status == "sorted":
                    sorted_times.append(local_dt)
            except (ValueError, TypeError):
                continue

        # Find worst day (most needs_attention)
        worst_count = 0
        for day, statuses in day_status.items():
            needs_attention_count = statuses.count("needs_attention")
            if needs_attention_count > worst_count:
                worst_count = needs_attention_count
                memory.patterns.worst_day = day

        # Find best day (most sorted)
        best_count = 0
        for day, statuses in day_status.items():
            sorted_count = statuses.count("sorted")
            if sorted_count > best_count:
                best_count = sorted_count
                memory.patterns.best_day = day

        # Find usual sorted time (mode of hours when sorted)
        if sorted_times:
            hour_counter: Counter[int] = Counter()
            for dt in sorted_times:
                hour_counter[dt.hour] += 1

            if hour_counter:
                most_common_hour = hour_counter.most_common(1)[0][0]
                # Format as "10:00 AM"
                from datetime import time

                t = time(hour=most_common_hour)
                memory.patterns.usually_sorted_by = t.strftime("%-I:%M %p")

        # Calculate current streak (consecutive days ending sorted)
        # Group checks by date, take last status of each day
        daily_status: dict[str, str] = {}
        for check in memory.checks:
            try:
                dt = datetime.fromisoformat(check.timestamp)
                date_str = dt.date().isoformat()
                daily_status[date_str] = check.status  # Last status wins
            except (ValueError, TypeError):
                continue

        # Count streak backwards from today
        today = utcnow().date()
        streak = 0
        for i in range(MEMORY_RETENTION_DAYS):
            check_date = (today - timedelta(days=i)).isoformat()
            if check_date in daily_status:
                if daily_status[check_date] == "sorted":
                    streak += 1
                else:
                    break
            else:
                # No check that day - don't break streak, just skip
                continue

        memory.patterns.current_streak = streak
        if streak > memory.patterns.longest_streak:
            memory.patterns.longest_streak = streak

    def build_memory_context(self, spot_id: str) -> str:
        """Build context string for AI prompt."""
        memory = self.get_memory(spot_id)

        if not memory.checks:
            return "First check - no history yet."

        lines = []

        # Last check info
        last_check = memory.checks[-1]
        try:
            last_dt = datetime.fromisoformat(last_check.timestamp)
            local_dt = as_local(last_dt)
            time_ago = utcnow() - last_dt
            if time_ago.days > 0:
                time_str = f"{time_ago.days} days ago"
            elif time_ago.seconds > 3600:
                time_str = f"{time_ago.seconds // 3600} hours ago"
            else:
                time_str = f"{time_ago.seconds // 60} minutes ago"

            lines.append(f"Last check: {last_check.status} ({time_str})")
            if last_check.to_sort_items:
                lines.append(f"  Items that needed sorting: {', '.join(last_check.to_sort_items[:3])}")
        except (ValueError, TypeError):
            pass

        # Recurring items
        if memory.patterns.recurring_items:
            top_items = list(memory.patterns.recurring_items.items())[:3]
            recurring_str = ", ".join(f"{item} ({count}x)" for item, count in top_items)
            lines.append(f"Recurring items: {recurring_str}")

        # Streak
        if memory.patterns.current_streak > 0:
            lines.append(f"Current streak: {memory.patterns.current_streak} days sorted")
            if memory.patterns.longest_streak > memory.patterns.current_streak:
                lines.append(f"Best streak ever: {memory.patterns.longest_streak} days")

        # Day patterns
        if memory.patterns.worst_day:
            lines.append(f"Toughest day: {memory.patterns.worst_day}")
        if memory.patterns.usually_sorted_by:
            lines.append(f"Usually sorted by: {memory.patterns.usually_sorted_by}")

        # Total checks
        lines.append(f"Total checks in last 30 days: {len(memory.checks)}")

        return "\n".join(lines) if lines else "First check - no history yet."

    def is_item_recurring(self, spot_id: str, item: str) -> bool:
        """Check if an item is recurring for this spot."""
        memory = self.get_memory(spot_id)
        normalized = item.lower().strip()
        return normalized in memory.patterns.recurring_items

    def get_recurring_count(self, spot_id: str, item: str) -> int:
        """Get how many times an item has appeared."""
        memory = self.get_memory(spot_id)
        normalized = item.lower().strip()
        return memory.patterns.recurring_items.get(normalized, 0)

    async def async_delete_spot(self, spot_id: str) -> None:
        """Delete memory for a spot."""
        if spot_id in self._memories:
            del self._memories[spot_id]
            await self.async_save()
