"""DataUpdateCoordinator for the Open-Meteo Solar Forecast integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from open_meteo_solar_forecast import Estimate, OpenMeteoSolarForecast

from .const import (
    CONF_AZIMUTH,
    CONF_BASE_URL,
    CONF_DAMPING_EVENING,
    CONF_DAMPING_MORNING,
    CONF_DECLINATION,
    CONF_EFFICIENCY_FACTOR,
    CONF_INCLUDE_IN_CUMULATIVE,
    CONF_INSTANCE_TYPE,
    CONF_INVERTER_POWER,
    CONF_MODEL,
    CONF_MODULES_POWER,
    DOMAIN,
    INSTANCE_TYPE_CUMULATIVE,
    INSTANCE_TYPE_NORMAL,
    LOGGER,
)


class OpenMeteoSolarForecastDataUpdateCoordinator(DataUpdateCoordinator[Estimate]):
    """The Solar Forecast Data Update Coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Solar Forecast coordinator."""
        self.config_entry = entry

        # Our option flow may cause it to be an empty string,
        # this if statement is here to catch that.
        api_key = entry.options.get(CONF_API_KEY) or None

        # Handle new options that were added after the initial release
        ac_kwp = entry.options.get(CONF_INVERTER_POWER, 0)
        ac_kwp = ac_kwp / 1000 if ac_kwp else None

        self.forecast = OpenMeteoSolarForecast(
            api_key=api_key,
            session=async_get_clientsession(hass),
            latitude=entry.data[CONF_LATITUDE],
            longitude=entry.data[CONF_LONGITUDE],
            azimuth=entry.options[CONF_AZIMUTH] - 180,
            base_url=entry.options[CONF_BASE_URL],
            ac_kwp=ac_kwp,
            dc_kwp=(entry.options[CONF_MODULES_POWER] / 1000),
            declination=entry.options[CONF_DECLINATION],
            efficiency_factor=entry.options[CONF_EFFICIENCY_FACTOR],
            damping_morning=entry.options.get(CONF_DAMPING_MORNING, 0.0),
            damping_evening=entry.options.get(CONF_DAMPING_EVENING, 0.0),
            weather_model=entry.options.get(CONF_MODEL, "best_match"),
        )

        update_interval = timedelta(minutes=30)

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self) -> Estimate:
        """Fetch Open-Meteo Solar Forecast estimates."""
        return await self.forecast.estimate()


class CumulativeEstimate(Estimate):
    """Cumulative estimate that sums data from multiple instances."""

    def __init__(self, estimates: list[Estimate]) -> None:
        """Initialize cumulative estimate from multiple estimates."""
        if not estimates:
            # Create empty estimate
            super().__init__(
                watts={},
                wh_days={},
                wh_period={},
            )
            return

        # Use the first estimate as base
        first = estimates[0]
        
        # Sum up all watts
        all_watts: dict[datetime, int] = {}
        for estimate in estimates:
            for dt, value in estimate.watts.items():
                all_watts[dt] = all_watts.get(dt, 0) + value

        # Sum up all wh_days
        all_wh_days: dict[Any, int] = {}
        for estimate in estimates:
            for day, value in estimate.wh_days.items():
                all_wh_days[day] = all_wh_days.get(day, 0) + value

        # Sum up all wh_period
        all_wh_period: dict[datetime, int] = {}
        for estimate in estimates:
            for dt, value in estimate.wh_period.items():
                all_wh_period[dt] = all_wh_period.get(dt, 0) + value

        # Initialize with summed data
        super().__init__(
            watts=all_watts,
            wh_days=all_wh_days,
            wh_period=all_wh_period,
        )


class OpenMeteoSolarForecastCumulativeCoordinator(DataUpdateCoordinator[Estimate]):
    """Coordinator that aggregates data from multiple instances."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the cumulative coordinator."""
        self.config_entry = entry
        update_interval = timedelta(minutes=1)  # Update more frequently to pick up changes

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self) -> Estimate:
        """Aggregate data from all instances marked for cumulation."""
        estimates: list[Estimate] = []
        
        # Find all instances marked for cumulation
        for entry_id, coordinator in self.hass.data.get(DOMAIN, {}).items():
            if entry_id == self.config_entry.entry_id:
                # Skip self
                continue
            
            if not isinstance(coordinator, OpenMeteoSolarForecastDataUpdateCoordinator):
                # Skip non-standard coordinators
                continue
            
            # Check if this instance is marked for cumulation
            if coordinator.config_entry.options.get(CONF_INCLUDE_IN_CUMULATIVE, False):
                if coordinator.data:
                    estimates.append(coordinator.data)
        
        return CumulativeEstimate(estimates)
