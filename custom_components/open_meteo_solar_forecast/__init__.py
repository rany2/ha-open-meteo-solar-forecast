"""The Open-Meteo Solar Forecast integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HORIZON_FILEPATH, CONF_USE_HORIZON, DOMAIN
from .coordinator import (
    OpenMeteoSolarForecastDataUpdateCoordinator,
    checkHorizonFile,
)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Forecast from a config entry."""
    horizon_map: tuple[tuple[float, float], ...] = ((0.0, 0.0), (360.0, 0.0))
    if entry.options.get(CONF_USE_HORIZON):
        horizon_filepath = entry.options.get(CONF_HORIZON_FILEPATH)
        horizon_map, message = await hass.async_add_executor_job(
            checkHorizonFile, horizon_filepath
        )
        if horizon_map is None:
            raise ValueError(message)

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


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
