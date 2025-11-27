"""Dashboard generator for TwinSync Spot.

Generates a Lovelace dashboard that matches the mockup:
┌─────────────────────────────────────────────┐
│ 📍 My Work Desk           ⚠ Needs Attention │
│─────────────────────────────────────────────│
│ To sort:                                    │
│ • Coffee mug on left side (again!)          │
│ • Papers by keyboard                        │
│                                             │
│ Looking good:                               │
│ • Laptop on stand ✓                         │
│ • Cables tidy ✓                             │
│─────────────────────────────────────────────│
│ That mug's been there 4 days now.           │
│─────────────────────────────────────────────│
│ [📷 Check]  [✓ I've Reset It]  [💤 Later]   │
│                                             │
│ 🔥 Streak: 0 days (best: 5)                 │
└─────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DASHBOARD_TITLE = "TwinSync Spot"
DASHBOARD_ICON = "mdi:map-marker-check"
DASHBOARD_PATH = "twinsync-spot"


def generate_dashboard_config(hass: HomeAssistant) -> dict[str, Any]:
    """Generate complete Lovelace dashboard config."""
    spots_data = hass.data.get(DOMAIN, {})

    # Get all spot names
    spot_names = []
    for spot in spots_data.values():
        if hasattr(spot, "name"):
            spot_names.append(spot.name)

    cards = []

    # Header
    cards.append(_create_header())

    # Status overview
    cards.append(_create_status_overview())

    # Alert section (conditional)
    cards.append(_create_alert_section())

    # Spot cards
    if spot_names:
        for spot_name in spot_names:
            cards.append(_create_spot_card(spot_name))
    else:
        cards.append(_create_no_spots_card())

    # Quick actions
    cards.append(_create_quick_actions())

    return {
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "path": DASHBOARD_PATH,
        "badges": [],
        "cards": cards,
    }


def _create_header() -> dict[str, Any]:
    """Create dashboard header."""
    return {
        "type": "markdown",
        "content": "# 📍 TwinSync Spot\n*Does this match YOUR definition?*",
    }


def _create_status_overview() -> dict[str, Any]:
    """Create status overview row."""
    return {
        "type": "horizontal-stack",
        "cards": [
            {
                "type": "entity",
                "entity": "sensor.twinsync_total_spots",
                "name": "Spots",
                "icon": "mdi:map-marker-multiple",
            },
            {
                "type": "entity",
                "entity": "sensor.twinsync_spots_needing_attention",
                "name": "Need Attention",
                "icon": "mdi:alert-circle",
            },
            {
                "type": "entity",
                "entity": "binary_sensor.twinsync_all_sorted",
                "name": "All Sorted",
                "icon": "mdi:check-circle",
            },
        ],
    }


def _create_alert_section() -> dict[str, Any]:
    """Create conditional alert for spots needing attention."""
    return {
        "type": "conditional",
        "conditions": [
            {
                "entity": "sensor.twinsync_spots_needing_attention",
                "state_not": "0",
            }
        ],
        "card": {
            "type": "markdown",
            "content": (
                "{% set spots = state_attr('sensor.twinsync_spots_needing_attention', 'spots') %}\n"
                "{% if spots %}\n"
                "## ⚠️ Needs Attention\n"
                "{% for spot in spots %}\n"
                "- **{{ spot }}**\n"
                "{% endfor %}\n"
                "{% endif %}"
            ),
        },
    }


def _create_spot_card(spot_name: str) -> dict[str, Any]:
    """Create a complete card for one spot, matching the mockup."""
    spot_slug = slugify(spot_name)

    return {
        "type": "vertical-stack",
        "cards": [
            # Header with status
            {
                "type": "markdown",
                "content": (
                    f"## 📍 {spot_name}\n"
                    f"{{% if is_state('binary_sensor.{spot_slug}_sorted', 'on') %}}"
                    "✅ **Sorted**"
                    "{% else %}"
                    "⚠️ **Needs Attention**"
                    "{% endif %}"
                ),
            },
            # To sort section
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": f"sensor.{spot_slug}_to_sort",
                        "state_not": "0",
                    }
                ],
                "card": {
                    "type": "markdown",
                    "content": (
                        f"{{% set items = state_attr('sensor.{spot_slug}_to_sort', 'to_sort') %}}\n"
                        "{% if items %}\n"
                        "### To sort:\n"
                        "{% for item in items %}\n"
                        "- **{{ item.item }}**"
                        "{% if item.location %} *({{ item.location }})*{% endif %}"
                        "{% if item.recurring %} 🔄{% endif %}\n"
                        "{% endfor %}\n"
                        "{% endif %}"
                    ),
                },
            },
            # Looking good section
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": f"sensor.{spot_slug}_looking_good",
                        "state_not": "0",
                    }
                ],
                "card": {
                    "type": "markdown",
                    "content": (
                        f"{{% set items = state_attr('sensor.{spot_slug}_looking_good', 'looking_good') %}}\n"
                        "{% if items %}\n"
                        "### Looking good:\n"
                        "{% for item in items %}\n"
                        "- {{ item }} ✓\n"
                        "{% endfor %}\n"
                        "{% endif %}"
                    ),
                },
            },
            # Notes section
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": f"sensor.{spot_slug}_notes",
                        "state_not": "No notes yet",
                    },
                    {
                        "entity": f"sensor.{spot_slug}_notes",
                        "state_not": "unavailable",
                    },
                ],
                "card": {
                    "type": "markdown",
                    "content": (
                        f"{{% set main = state_attr('sensor.{spot_slug}_notes', 'main') %}}\n"
                        f"{{% set pattern = state_attr('sensor.{spot_slug}_notes', 'pattern') %}}\n"
                        "{% if main %}\n"
                        "---\n"
                        "*{{ main }}*\n"
                        "{% if pattern %}\n"
                        "\n📊 {{ pattern }}\n"
                        "{% endif %}\n"
                        "{% endif %}"
                    ),
                },
            },
            # Action buttons with TEXT LABELS (not just icons!)
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "button",
                        "name": "📷 Check",
                        "tap_action": {
                            "action": "call-service",
                            "service": "cleanme.check",
                            "data": {"spot": spot_name},
                        },
                        "show_icon": False,
                        "show_name": True,
                    },
                    {
                        "type": "button",
                        "name": "✓ Reset",
                        "tap_action": {
                            "action": "call-service",
                            "service": "cleanme.reset",
                            "data": {"spot": spot_name},
                        },
                        "show_icon": False,
                        "show_name": True,
                    },
                    {
                        "type": "button",
                        "name": "💤 Later",
                        "tap_action": {
                            "action": "call-service",
                            "service": "cleanme.snooze",
                            "data": {"spot": spot_name, "duration_minutes": 1440},
                        },
                        "show_icon": False,
                        "show_name": True,
                    },
                ],
            },
            # Streak info
            {
                "type": "markdown",
                "content": (
                    f"{{% set current = states('sensor.{spot_slug}_streak') | int %}}\n"
                    f"{{% set best = state_attr('sensor.{spot_slug}_streak', 'longest_streak') | int %}}\n"
                    "🔥 **Streak:** {{ current }} day{% if current != 1 %}s{% endif %}"
                    "{% if best > current %} *(best: {{ best }})*{% endif %}"
                ),
            },
        ],
    }


def _create_no_spots_card() -> dict[str, Any]:
    """Card shown when no spots are configured."""
    return {
        "type": "markdown",
        "content": (
            "## 👋 Welcome to TwinSync Spot!\n\n"
            "No spots configured yet.\n\n"
            "1. Go to **Settings** → **Devices & Services**\n"
            "2. Click **Add Integration**\n"
            "3. Search for **CleanMe**\n"
            "4. Define your first spot!\n"
        ),
    }


def _create_quick_actions() -> dict[str, Any]:
    """Create quick action buttons at bottom."""
    return {
        "type": "horizontal-stack",
        "cards": [
            {
                "type": "button",
                "name": "Check All",
                "icon": "mdi:camera-burst",
                "tap_action": {
                    "action": "call-service",
                    "service": "cleanme.check_all",
                },
            },
            {
                "type": "button",
                "name": "Add Spot",
                "icon": "mdi:plus-circle",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": "/config/integrations/integration/cleanme",
                },
            },
            {
                "type": "button",
                "name": "Refresh Dashboard",
                "icon": "mdi:refresh",
                "tap_action": {
                    "action": "call-service",
                    "service": "cleanme.regenerate_dashboard",
                },
            },
        ],
    }


def generate_basic_dashboard_config(hass: HomeAssistant) -> dict[str, Any]:
    """Generate basic dashboard without custom cards.

    Fallback for users who haven't installed custom cards.
    """
    spots_data = hass.data.get(DOMAIN, {})

    spot_names = []
    for spot in spots_data.values():
        if hasattr(spot, "name"):
            spot_names.append(spot.name)

    cards = []

    # Simple header
    cards.append({
        "type": "markdown",
        "content": "# 📍 TwinSync Spot",
    })

    # Spot cards
    for spot_name in spot_names:
        spot_slug = slugify(spot_name)
        cards.append({
            "type": "entities",
            "title": f"📍 {spot_name}",
            "entities": [
                {"entity": f"binary_sensor.{spot_slug}_sorted", "name": "Status"},
                {"entity": f"sensor.{spot_slug}_to_sort", "name": "To Sort"},
                {"entity": f"sensor.{spot_slug}_looking_good", "name": "Looking Good"},
                {"entity": f"sensor.{spot_slug}_streak", "name": "Streak"},
                {"entity": f"sensor.{spot_slug}_last_check", "name": "Last Check"},
            ],
        })

    return {
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "path": DASHBOARD_PATH,
        "badges": [],
        "cards": cards,
    }


def get_required_custom_cards() -> list[str]:
    """Return list of required custom cards.

    Actually, we use standard cards only now! No custom cards required.
    """
    return []  # We only use standard HA cards


def create_simple_cards_list(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Create simple list of cards for manual dashboard integration."""
    config = generate_dashboard_config(hass)
    return config.get("cards", [])
