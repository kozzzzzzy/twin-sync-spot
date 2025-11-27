"""Constants for TwinSync Spot (CleanMe rewrite)."""

from enum import Enum

DOMAIN = "cleanme"  # Keep for HACS compatibility

PLATFORMS = ["sensor", "binary_sensor", "button", "number", "select"]

# ============================================================================
# CONFIGURATION KEYS
# ============================================================================

CONF_NAME = "name"
CONF_CAMERA_ENTITY = "camera_entity"
CONF_API_KEY = "api_key"
CONF_SPOT_TYPE = "spot_type"
CONF_DEFINITION = "definition"
CONF_VOICE = "voice"
CONF_CUSTOM_VOICE_PROMPT = "custom_voice_prompt"
CONF_CHECK_FREQUENCY = "check_frequency"

# ============================================================================
# SPOT TYPES (for config flow templates)
# ============================================================================


class SpotType(str, Enum):
    """Types of spots with pre-filled definition templates."""

    WORK = "work"
    CHILL = "chill"
    SLEEP = "sleep"
    KITCHEN = "kitchen"
    ENTRYWAY = "entryway"
    STORAGE = "storage"
    CUSTOM = "custom"


SPOT_TYPE_LABELS = {
    SpotType.WORK: "💼 Work / Focus Desk",
    SpotType.CHILL: "🛋️ Chill / Relaxing Area",
    SpotType.SLEEP: "🛏️ Sleep Zone",
    SpotType.KITCHEN: "🍳 Cooking / Kitchen",
    SpotType.ENTRYWAY: "🚪 Entryway / Hallway",
    SpotType.STORAGE: "📦 Storage Area",
    SpotType.CUSTOM: "✨ Something else",
}

SPOT_TEMPLATES = {
    SpotType.WORK: """This is my work area. I need a clear surface to focus.

Things that should be here:
- Laptop/monitor
- Notebook and pen
- Water bottle

Things that shouldn't be here:
- Dirty dishes or cups
- Random papers or mail
- Clothes""",
    SpotType.CHILL: """This is where I relax. Should feel calm and uncluttered.

Things that are fine here:
- Remote controls in their spot
- A book or two
- Throw blanket folded

Things that shouldn't pile up:
- Empty glasses or plates
- Random stuff from pockets
- Laundry""",
    SpotType.SLEEP: """This is my sleep space. Should be calm and ready for rest.

Ready state:
- Bed made (or at least neat)
- Nightstand clear except lamp/phone charger
- No clothes on floor
- Blinds/curtains in position""",
    SpotType.KITCHEN: """This is my kitchen area. Should be clear and ready to use.

Ready state:
- Counters wiped and clear
- Dishes washed or in dishwasher
- No food left out
- Sink empty""",
    SpotType.ENTRYWAY: """This is my entryway. First thing I see coming home.

Ready state:
- Shoes in rack or lined up
- Keys/wallet in their spot
- No bags dumped on floor
- Coat hung up""",
    SpotType.STORAGE: """This is a storage area. Things should be organised.

What belongs here:
- [List your items]

Signs it needs sorting:
- Things not in their containers
- Items blocking access
- Stuff that doesn't belong here""",
    SpotType.CUSTOM: """Describe this spot in your own words.

What is it for?

What should it look like when ready?

What are signs it needs attention?""",
}

# ============================================================================
# VOICES (replacing old "personalities")
# ============================================================================

VOICE_DIRECT = "direct"
VOICE_SUPPORTIVE = "supportive"
VOICE_ANALYTICAL = "analytical"
VOICE_MINIMAL = "minimal"
VOICE_GENTLE_NUDGE = "gentle_nudge"
VOICE_CUSTOM = "custom"

VOICES = {
    VOICE_DIRECT: {
        "name": "Direct",
        "description": "Just the facts, no fluff",
        "prompt": """Be direct and factual. State what you see clearly.
No emojis. No encouragement. No sugar-coating.
Just tell them what matches and what doesn't.""",
    },
    VOICE_SUPPORTIVE: {
        "name": "Supportive",
        "description": "Encouraging, acknowledges effort",
        "prompt": """Be warm and encouraging. Acknowledge progress and effort.
Frame things positively - what's working, then what needs attention.
Celebrate small wins. Use occasional emojis sparingly.""",
    },
    VOICE_ANALYTICAL: {
        "name": "Analytical",
        "description": "Spots patterns, references history",
        "prompt": """Focus on patterns and data. Reference the history provided.
Help the user see trends over time. Be observational, not judgmental.
Point out what's recurring and what's improving.""",
    },
    VOICE_MINIMAL: {
        "name": "Minimal",
        "description": "List only, no commentary",
        "prompt": """Just the list. No commentary, no observations, no advice.
Keep notes to a single short sentence if absolutely necessary.
Prefer silence over filler.""",
    },
    VOICE_GENTLE_NUDGE: {
        "name": "Gentle Nudge",
        "description": "Soft suggestions for tough days",
        "prompt": """Be gentle and low-pressure. Suggest rather than state.
Acknowledge that some days are harder than others.
Frame everything as optional, not demands. Be kind.""",
    },
    VOICE_CUSTOM: {
        "name": "Custom",
        "description": "Your own voice",
        "prompt": None,  # User provides
    },
}

VOICE_OPTIONS = {key: f"{v['name']} - {v['description']}" for key, v in VOICES.items()}

# ============================================================================
# CHECK FREQUENCY
# ============================================================================

FREQUENCY_MANUAL = "manual"
FREQUENCY_1X = "1x"
FREQUENCY_2X = "2x"
FREQUENCY_4X = "4x"

FREQUENCY_OPTIONS = {
    FREQUENCY_MANUAL: "Manual only",
    FREQUENCY_1X: "1x daily",
    FREQUENCY_2X: "2x daily",
    FREQUENCY_4X: "4x daily",
}

FREQUENCY_TO_RUNS = {
    FREQUENCY_MANUAL: 0,
    FREQUENCY_1X: 1,
    FREQUENCY_2X: 2,
    FREQUENCY_4X: 4,
}

# ============================================================================
# GEMINI CONFIGURATION
# ============================================================================

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ============================================================================
# SENSOR ATTRIBUTES (new terminology)
# ============================================================================

# Status attributes
ATTR_STATUS = "status"
ATTR_SORTED = "sorted"
ATTR_NEEDS_ATTENTION = "needs_attention"

# Items attributes
ATTR_TO_SORT = "to_sort"
ATTR_TO_SORT_COUNT = "to_sort_count"
ATTR_LOOKING_GOOD = "looking_good"
ATTR_LOOKING_GOOD_COUNT = "looking_good_count"

# Notes attributes
ATTR_NOTES = "notes"
ATTR_NOTES_MAIN = "notes_main"
ATTR_NOTES_PATTERN = "notes_pattern"
ATTR_NOTES_ENCOURAGEMENT = "notes_encouragement"

# Spot configuration
ATTR_DEFINITION = "definition"
ATTR_VOICE = "voice"
ATTR_CAMERA_ENTITY = "camera_entity"
ATTR_SPOT_TYPE = "spot_type"

# Check metadata
ATTR_LAST_CHECK = "last_check"
ATTR_IMAGE_SIZE = "image_size"
ATTR_API_RESPONSE_TIME = "api_response_time"
ATTR_ERROR_MESSAGE = "error_message"

# Memory/streak attributes
ATTR_STREAK = "streak"
ATTR_CURRENT_STREAK = "current_streak"
ATTR_LONGEST_STREAK = "longest_streak"
ATTR_LAST_RESET = "last_reset"
ATTR_TOTAL_RESETS = "total_resets"
ATTR_RECURRING_ITEMS = "recurring_items"

# Snooze attributes
ATTR_SNOOZED = "snoozed"
ATTR_SNOOZED_UNTIL = "snoozed_until"

# System attributes
ATTR_SPOT_COUNT = "spot_count"
ATTR_SPOTS_NEEDING_ATTENTION = "spots_needing_attention"
ATTR_ALL_SORTED = "all_sorted"
ATTR_NEXT_SCHEDULED_CHECK = "next_scheduled_check"

# Dashboard attributes
ATTR_DASHBOARD_PATH = "dashboard_path"
ATTR_DASHBOARD_LAST_GENERATED = "dashboard_last_generated"
ATTR_DASHBOARD_LAST_ERROR = "dashboard_last_error"
ATTR_DASHBOARD_STATUS = "dashboard_status"
ATTR_READY = "ready"

# ============================================================================
# SERVICES (new names)
# ============================================================================

SERVICE_CHECK = "check"
SERVICE_RESET = "reset"
SERVICE_SNOOZE = "snooze"
SERVICE_UNSNOOZE = "unsnooze"
SERVICE_CHECK_ALL = "check_all"

# Service parameters
ATTR_SPOT = "spot"
ATTR_DURATION_MINUTES = "duration_minutes"

# ============================================================================
# DEFAULTS
# ============================================================================

DEFAULT_CHECK_INTERVAL_HOURS = 24
DEFAULT_OVERDUE_THRESHOLD_HOURS = 48
DEFAULT_VOICE = VOICE_SUPPORTIVE
DEFAULT_SPOT_TYPE = SpotType.CUSTOM

# ============================================================================
# STORAGE
# ============================================================================

STORAGE_KEY = "cleanme.spots"
STORAGE_KEY_MEMORY = "cleanme.memory"
STORAGE_VERSION = 1

# ============================================================================
# DISPATCHER SIGNALS
# ============================================================================

SIGNAL_SYSTEM_STATE_UPDATED = "cleanme_system_state_updated"
SIGNAL_SPOT_STATE_UPDATED = "cleanme_spot_state_updated"
