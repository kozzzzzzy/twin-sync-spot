"""TwinSync Spot - Does this match YOUR definition?

A Home Assistant integration that compares camera snapshots to your
own description of how a spot should look when it's ready.
"""
from __future__ import annotations

from typing import Any
import logging
from logging.handlers import RotatingFileHandler
import os

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_COMPONENT_LOADED
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util.dt import utcnow

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_CHECK,
    SERVICE_RESET,
    SERVICE_SNOOZE,
    SERVICE_UNSNOOZE,
    SERVICE_CHECK_ALL,
    ATTR_SPOT,
    ATTR_DURATION_MINUTES,
    ATTR_DASHBOARD_LAST_ERROR,
    ATTR_DASHBOARD_LAST_GENERATED,
    ATTR_DASHBOARD_PATH,
    ATTR_DASHBOARD_STATUS,
    SIGNAL_SYSTEM_STATE_UPDATED,
)
from .coordinator import TwinSyncSpot
from .memory import MemoryManager
from . import dashboard as spot_dashboard

LOGGER = logging.getLogger(__name__)

# Check if PyYAML is available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    LOGGER.warning("TwinSync Spot: PyYAML not available, dashboard export disabled")


def _get_dashboard_state(hass: HomeAssistant) -> dict[str, Any]:
    """Return mutable dashboard state dict."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    return domain_data.setdefault(
        "dashboard_state",
        {
            ATTR_DASHBOARD_PATH: None,
            ATTR_DASHBOARD_LAST_GENERATED: None,
            ATTR_DASHBOARD_LAST_ERROR: None,
            ATTR_DASHBOARD_STATUS: "pending",
            "panel_registered": False,
        },
    )


async def async_setup_spot_logger(hass: HomeAssistant):
    """Set up dedicated log file."""
    logger = logging.getLogger("custom_components.cleanme")

    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return logger

    logger.setLevel(logging.DEBUG)
    log_file = hass.config.path("twinsync_spot.log")

    def _create_handler():
        handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
        )
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        return handler

    file_handler = await hass.async_add_executor_job(_create_handler)
    logger.addHandler(file_handler)
    logger.info("=" * 50)
    logger.info("TwinSync Spot logging initialized")
    logger.info("=" * 50)

    return logger


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TwinSync Spot config entry."""
    hass.data.setdefault(DOMAIN, {})

    await async_setup_spot_logger(hass)
    LOGGER.info("Setting up spot '%s' (entry_id: %s)", entry.title, entry.entry_id)

    # Initialize shared memory manager
    if "memory_manager" not in hass.data[DOMAIN]:
        memory_manager = MemoryManager(hass)
        await memory_manager.async_load()
        hass.data[DOMAIN]["memory_manager"] = memory_manager
    else:
        memory_manager = hass.data[DOMAIN]["memory_manager"]

    # Create spot coordinator
    spot = TwinSyncSpot(
        hass=hass,
        entry_id=entry.entry_id,
        name=entry.data.get("name") or entry.title,
        data=entry.data,
        memory_manager=memory_manager,
    )

    hass.data[DOMAIN][entry.entry_id] = spot

    await spot.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services if not already done
    if not hass.services.has_service(DOMAIN, SERVICE_CHECK):
        _register_services(hass)

    # Generate dashboard
    LOGGER.info("Generating dashboard for spot '%s'", entry.title)
    dashboard_state = _get_dashboard_state(hass)

    try:
        dashboard_config = spot_dashboard.generate_dashboard_config(hass)
        hass.data[DOMAIN]["dashboard_config"] = dashboard_config
        dashboard_state[ATTR_DASHBOARD_STATUS] = "generated"
        LOGGER.info("Dashboard generated with %d cards", len(dashboard_config.get("cards", [])))

        await _regenerate_dashboard_yaml(hass)
    except Exception as e:
        dashboard_state[ATTR_DASHBOARD_STATUS] = "error"
        dashboard_state[ATTR_DASHBOARD_LAST_ERROR] = str(e)
        async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)
        LOGGER.error("Failed to generate dashboard: %s", e)

    async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)

    # Trigger initial check
    hass.async_create_task(
        spot.async_check(reason="initial"),
        f"twinsync_initial_check_{entry.entry_id}",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    spot: TwinSyncSpot = hass.data[DOMAIN].pop(entry.entry_id, None)
    if spot:
        await spot.async_unload()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Check if any spots remain
    remaining_spots = [
        s for s in hass.data[DOMAIN].values()
        if isinstance(s, TwinSyncSpot)
    ]

    if not remaining_spots:
        # Remove services
        for service in [SERVICE_CHECK, SERVICE_RESET, SERVICE_SNOOZE, SERVICE_UNSNOOZE,
                        SERVICE_CHECK_ALL, "regenerate_dashboard", "export_basic_dashboard"]:
            hass.services.async_remove(DOMAIN, service)
    else:
        # Regenerate dashboard
        try:
            dashboard_config = spot_dashboard.generate_dashboard_config(hass)
            hass.data[DOMAIN]["dashboard_config"] = dashboard_config
            await _regenerate_dashboard_yaml(hass)
        except Exception as e:
            LOGGER.error("Failed to update dashboard: %s", e)

    async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)
    return unload_ok


def _find_spot_by_name(hass: HomeAssistant, spot_name: str) -> TwinSyncSpot | None:
    """Find a spot by its name."""
    for spot in hass.data.get(DOMAIN, {}).values():
        if isinstance(spot, TwinSyncSpot) and spot.name == spot_name:
            return spot
    return None


async def _regenerate_dashboard_yaml(hass: HomeAssistant) -> None:
    """Generate/update dashboard YAML and auto-register."""
    dashboard_state = _get_dashboard_state(hass)

    if not YAML_AVAILABLE:
        dashboard_state[ATTR_DASHBOARD_LAST_ERROR] = "PyYAML not available"
        dashboard_state[ATTR_DASHBOARD_STATUS] = "unavailable"
        dashboard_state[ATTR_DASHBOARD_LAST_GENERATED] = utcnow()
        async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)
        return

    try:
        dashboard_config = spot_dashboard.generate_dashboard_config(hass)

        lovelace_config = {
            "title": "TwinSync Spot",
            "views": [
                {
                    "title": dashboard_config.get("title", "TwinSync Spot"),
                    "path": dashboard_config.get("path", "twinsync-spot"),
                    "icon": dashboard_config.get("icon", "mdi:map-marker-check"),
                    "badges": [],
                    "cards": dashboard_config.get("cards", []),
                }
            ],
        }

        dashboards_dir = hass.config.path("dashboards")

        def _write_yaml() -> str:
            os.makedirs(dashboards_dir, mode=0o755, exist_ok=True)
            yaml_file = os.path.join(dashboards_dir, "twinsync_spot.yaml")
            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    lovelace_config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            return yaml_file

        yaml_file = await hass.async_add_executor_job(_write_yaml)

        dashboard_state[ATTR_DASHBOARD_PATH] = yaml_file
        dashboard_state[ATTR_DASHBOARD_LAST_GENERATED] = utcnow()
        dashboard_state[ATTR_DASHBOARD_LAST_ERROR] = None
        dashboard_state[ATTR_DASHBOARD_STATUS] = "written"
        async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)
        LOGGER.info("Dashboard YAML written to %s", yaml_file)

        await _auto_register_dashboard(hass, lovelace_config)

    except Exception as e:
        LOGGER.error("Failed to write dashboard: %s", e)
        dashboard_state[ATTR_DASHBOARD_LAST_ERROR] = str(e)
        dashboard_state[ATTR_DASHBOARD_LAST_GENERATED] = utcnow()
        dashboard_state[ATTR_DASHBOARD_STATUS] = "error"
        async_dispatcher_send(hass, SIGNAL_SYSTEM_STATE_UPDATED)


async def _auto_register_dashboard(
    hass: HomeAssistant,
    lovelace_config: dict[str, Any],
) -> bool:
    """Auto-register dashboard in HA sidebar."""
    from homeassistant.components import frontend
    from homeassistant.components.lovelace import const as lovelace_const
    from homeassistant.components.lovelace import dashboard as lovelace_dashboard

    dashboard_state = _get_dashboard_state(hass)
    url_path = "twinsync-spot"
    title = "TwinSync Spot"
    icon = "mdi:map-marker-check"

    lovelace_data = hass.data.get(lovelace_const.LOVELACE_DATA)
    if lovelace_data is None:
        LOGGER.debug("Lovelace not loaded yet, scheduling registration")

        @callback
        def _on_component_loaded(event) -> None:
            if event.data.get("component") != lovelace_const.DOMAIN:
                return
            unsubscribe()
            hass.async_create_task(_auto_register_dashboard(hass, lovelace_config))

        unsubscribe = hass.bus.async_listen(EVENT_COMPONENT_LOADED, _on_component_loaded)
        return False

    try:
        dashboards_collection = lovelace_dashboard.DashboardsCollection(hass)
        await dashboards_collection.async_load()
    except Exception as err:
        LOGGER.error("Failed to load dashboards collection: %s", err)
        return False

    # Check if exists
    existing_id: str | None = None
    existing_item: dict[str, Any] | None = None
    for item_id, item in dashboards_collection.data.items():
        if item.get(lovelace_const.CONF_URL_PATH) == url_path:
            existing_id = item_id
            existing_item = item
            break

    base_item: dict[str, Any] = {
        lovelace_const.CONF_TITLE: title,
        lovelace_const.CONF_ICON: icon,
        lovelace_const.CONF_URL_PATH: url_path,
        lovelace_const.CONF_REQUIRE_ADMIN: False,
        lovelace_const.CONF_SHOW_IN_SIDEBAR: True,
    }

    if existing_item is None:
        LOGGER.info("Creating Lovelace dashboard '%s'", url_path)
        try:
            item = await dashboards_collection.async_create_item(
                {**base_item, lovelace_const.CONF_MODE: lovelace_const.MODE_STORAGE}
            )
        except Exception as err:
            LOGGER.error("Failed to create dashboard: %s", err)
            return False
    else:
        updates = {}
        for key, value in [
            (lovelace_const.CONF_TITLE, title),
            (lovelace_const.CONF_ICON, icon),
            (lovelace_const.CONF_SHOW_IN_SIDEBAR, True),
        ]:
            if existing_item.get(key) != value:
                updates[key] = value

        if updates:
            try:
                item = await dashboards_collection.async_update_item(existing_id, updates)
            except Exception as err:
                LOGGER.error("Failed to update dashboard: %s", err)
                item = existing_item
        else:
            item = existing_item

    # Register storage
    lovelace_storage = lovelace_data.dashboards.get(url_path)
    if not isinstance(lovelace_storage, lovelace_dashboard.LovelaceStorage):
        lovelace_storage = lovelace_dashboard.LovelaceStorage(hass, item)
        lovelace_data.dashboards[url_path] = lovelace_storage
    else:
        lovelace_storage.config = {**item, lovelace_const.CONF_URL_PATH: url_path}

    try:
        await lovelace_storage.async_save(lovelace_config)
    except Exception as err:
        LOGGER.error("Failed to save dashboard layout: %s", err)
        return False

    # Register panel
    frontend.async_register_built_in_panel(
        hass,
        lovelace_const.DOMAIN,
        frontend_url_path=url_path,
        sidebar_title=title,
        sidebar_icon=icon,
        require_admin=False,
        config={"mode": lovelace_storage.mode},
        update=True,
    )

    dashboard_state["panel_registered"] = True
    LOGGER.info("Dashboard registered at /%s", url_path)
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register TwinSync Spot services."""

    async def handle_check(call: ServiceCall) -> None:
        """Handle check service."""
        spot_name = call.data[ATTR_SPOT]
        spot = _find_spot_by_name(hass, spot_name)
        if spot:
            await spot.async_check(reason="service")
        else:
            LOGGER.warning("Spot '%s' not found", spot_name)

    async def handle_reset(call: ServiceCall) -> None:
        """Handle reset service."""
        spot_name = call.data[ATTR_SPOT]
        spot = _find_spot_by_name(hass, spot_name)
        if spot:
            await spot.async_reset()
        else:
            LOGGER.warning("Spot '%s' not found", spot_name)

    async def handle_snooze(call: ServiceCall) -> None:
        """Handle snooze service."""
        spot_name = call.data[ATTR_SPOT]
        minutes = int(call.data[ATTR_DURATION_MINUTES])
        spot = _find_spot_by_name(hass, spot_name)
        if spot:
            await spot.async_snooze(minutes)
        else:
            LOGGER.warning("Spot '%s' not found", spot_name)

    async def handle_unsnooze(call: ServiceCall) -> None:
        """Handle unsnooze service."""
        spot_name = call.data[ATTR_SPOT]
        spot = _find_spot_by_name(hass, spot_name)
        if spot:
            await spot.async_unsnooze()
        else:
            LOGGER.warning("Spot '%s' not found", spot_name)

    async def handle_check_all(call: ServiceCall) -> None:
        """Handle check_all service."""
        spots = [
            s for s in hass.data.get(DOMAIN, {}).values()
            if isinstance(s, TwinSyncSpot)
        ]
        LOGGER.info("Checking all %d spots", len(spots))
        for spot in spots:
            await spot.async_check(reason="check_all")

    async def handle_regenerate_dashboard(call: ServiceCall) -> None:
        """Handle regenerate_dashboard service."""
        await _regenerate_dashboard_yaml(hass)
        LOGGER.info("Dashboard regenerated")

    async def handle_export_basic_dashboard(call: ServiceCall) -> None:
        """Handle export_basic_dashboard service."""
        if not YAML_AVAILABLE:
            LOGGER.error("PyYAML not available")
            return

        try:
            dashboard_config = spot_dashboard.generate_basic_dashboard_config(hass)
            dashboards_dir = hass.config.path("dashboards")

            def _write() -> str:
                os.makedirs(dashboards_dir, mode=0o755, exist_ok=True)
                yaml_file = os.path.join(dashboards_dir, "twinsync_spot_basic.yaml")
                with open(yaml_file, "w", encoding="utf-8") as f:
                    yaml.dump(dashboard_config, f, default_flow_style=False,
                              allow_unicode=True, sort_keys=False)
                return yaml_file

            yaml_file = await hass.async_add_executor_job(_write)
            LOGGER.info("Basic dashboard written to %s", yaml_file)
        except Exception as e:
            LOGGER.error("Failed to write basic dashboard: %s", e)

    # Register all services
    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK,
        handle_check,
        vol.Schema({vol.Required(ATTR_SPOT): str}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET,
        handle_reset,
        vol.Schema({vol.Required(ATTR_SPOT): str}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SNOOZE,
        handle_snooze,
        vol.Schema({
            vol.Required(ATTR_SPOT): str,
            vol.Required(ATTR_DURATION_MINUTES): vol.All(int, vol.Range(min=1, max=1440)),
        }),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UNSNOOZE,
        handle_unsnooze,
        vol.Schema({vol.Required(ATTR_SPOT): str}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_ALL,
        handle_check_all,
        vol.Schema({}),
    )

    hass.services.async_register(
        DOMAIN,
        "regenerate_dashboard",
        handle_regenerate_dashboard,
        vol.Schema({}),
    )

    hass.services.async_register(
        DOMAIN,
        "export_basic_dashboard",
        handle_export_basic_dashboard,
        vol.Schema({}),
    )
