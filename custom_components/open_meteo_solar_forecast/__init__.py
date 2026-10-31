"""The Open-Meteo Solar Forecast integration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_AZIMUTH,
    CONF_DECLINATION,
    CONF_EFFICIENCY_FACTOR,
    CONF_HORIZON_FILEPATH,
    CONF_MODULES_POWER,
    CONF_PARTIAL_SHADING,
    CONF_TRACKING,
    CONF_USE_HORIZON,
    CONF_MAX_SNOWCOVER_DEPTH_CM,
    DOMAIN,
)
from .coordinator import (
    STORAGE_VERSION,
    OpenMeteoSolarForecastDataUpdateCoordinator,
    checkHorizonFile,
    storage_key,
)

PLATFORMS = [Platform.SENSOR]


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _entry_value(entry: ConfigEntry, key: str) -> Any:
    """Get config value from options with fallback to entry data."""
    return entry.options.get(key, entry.data.get(key))


def _resolve_array_count(entry: ConfigEntry) -> int:
    """Determine number of arrays from all array-capable values."""
    candidates = (
        _entry_value(entry, CONF_LATITUDE),
        _entry_value(entry, CONF_LONGITUDE),
        entry.options.get(CONF_DECLINATION),
        entry.options.get(CONF_AZIMUTH),
        entry.options.get(CONF_MODULES_POWER),
        entry.options.get(CONF_EFFICIENCY_FACTOR, 1.0),
        entry.options.get(CONF_TRACKING, "none"),
        entry.options.get(CONF_USE_HORIZON, False),
        entry.options.get(CONF_PARTIAL_SHADING, False),
        entry.options.get(CONF_HORIZON_FILEPATH),
        entry.options.get(CONF_MAX_SNOWCOVER_DEPTH_CM),
    )
    lengths = [len(value) for value in candidates if _is_sequence(value)]
    if not lengths:
        return 1

    array_count = max(lengths)
    for length in lengths:
        if length not in (1, array_count):
            raise ValueError(
                "Multi-array configuration has inconsistent list lengths "
                f"({length} vs {array_count})."
            )

    return array_count


def _normalize_option(value: Any, array_count: int, default: Any) -> list[Any]:
    """Normalize scalar or sequence option to list with array_count items."""
    if value is None:
        value = default

    if _is_sequence(value):
        normalized = list(value)
        if len(normalized) == 1 and array_count > 1:
            return normalized * array_count
        if len(normalized) != array_count:
            raise ValueError(
                "Multi-array configuration has inconsistent list lengths "
                f"({len(normalized)} vs {array_count})."
            )
        return normalized

    return [value] * array_count


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the location service once for all config entries."""

    async def async_update_array_location(call: ServiceCall) -> None:
        entries = {
            entry.entry_id: entry
            for entry in hass.config_entries.async_entries(DOMAIN)
        }
        entry_id = call.data.get("config_entry_id")
        if entry_id is None:
            if len(entries) != 1:
                raise ServiceValidationError("Select a config_entry_id to update")
            entry = next(iter(entries.values()))
        elif entry_id not in entries:
            raise ServiceValidationError(
                "Unknown Open-Meteo Solar Forecast config entry"
            )
        else:
            entry = entries[entry_id]

        array_count = _resolve_array_count(entry)
        array_number = call.data.get("array_number")
        if array_number is None:
            if array_count != 1:
                raise ServiceValidationError("Select an array_number to update")
            array_number = 1
        if array_number > array_count:
            raise ServiceValidationError(
                "array_number exceeds the configured array count"
            )

        location = call.data.get(
            "location_override",
            {
                CONF_LATITUDE: hass.config.latitude,
                CONF_LONGITUDE: hass.config.longitude,
            },
        )
        coordinates = {}
        for key in (CONF_LATITUDE, CONF_LONGITUDE):
            values = _normalize_option(_entry_value(entry, key), array_count, None)
            values[array_number - 1] = location[key]
            coordinates[key] = values[0] if array_count == 1 else values

        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **coordinates},
            options={**entry.options, **coordinates},
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        "update_array_location",
        async_update_array_location,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Optional("array_number"): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional("location_override"): vol.Schema(
                    {
                        vol.Required(CONF_LATITUDE): cv.latitude,
                        vol.Required(CONF_LONGITUDE): cv.longitude,
                        vol.Optional("radius"): vol.All(
                            vol.Coerce(float), vol.Range(min=0)
                        ),
                    }
                ),
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Forecast from a config entry."""
    default_horizon_map: tuple[tuple[float, float], ...] = ((0.0, 0.0), (360.0, 0.0))
    default_horizon_path = "/config/custom_components/open_meteo_solar_forecast/horizon.txt"

    array_count = _resolve_array_count(entry)
    use_horizon_values = _normalize_option(
        entry.options.get(CONF_USE_HORIZON, False),
        array_count,
        default=False,
    )
    horizon_paths = _normalize_option(
        entry.options.get(CONF_HORIZON_FILEPATH, default_horizon_path),
        array_count,
        default=default_horizon_path,
    )

    checked_horizon_by_path: dict[str, tuple[tuple[float, float], ...]] = {}
    horizon_maps: list[tuple[tuple[float, float], ...]] = []

    for use_horizon, horizon_path in zip(use_horizon_values, horizon_paths, strict=True):
        if not use_horizon:
            horizon_maps.append(default_horizon_map)
            continue

        if horizon_path not in checked_horizon_by_path:
            checked_map, message = await hass.async_add_executor_job(
                checkHorizonFile, horizon_path
            )
            if checked_map is None:
                raise ValueError(message)
            checked_horizon_by_path[horizon_path] = checked_map

        horizon_maps.append(checked_horizon_by_path[horizon_path])

    horizon_map: tuple[tuple[float, float], ...] | list[tuple[tuple[float, float], ...]]
    if array_count == 1:
        horizon_map = horizon_maps[0]
    else:
        horizon_map = horizon_maps

    coordinator = OpenMeteoSolarForecastDataUpdateCoordinator(
        hass, entry, horizon_map
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the retained forecast storage for a removed config entry."""
    await Store(hass, STORAGE_VERSION, storage_key(entry.entry_id)).async_remove()


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
