"""DataUpdateCoordinator for the Open-Meteo Solar Forecast integration."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from open_meteo_solar_forecast import Estimate, OpenMeteoSolarForecast

from .const import (
    CONF_ARRAY_INVERTER_POWER,
    CONF_AZIMUTH,
    CONF_BASE_URL,
    CONF_DAMPING_EVENING,
    CONF_DAMPING_MORNING,
    CONF_DECLINATION,
    CONF_EFFICIENCY_FACTOR,
    CONF_INVERTER_POWER,
    CONF_USE_HORIZON,
    CONF_PARTIAL_SHADING,
    CONF_MAX_SNOWCOVER_DEPTH_CM,
    CONF_MODEL,
    CONF_MODULES_POWER,
    CONF_TRACKING,
    DOMAIN,
    LOGGER,
)

STORAGE_VERSION = 2


class RetainedForecastStore(Store[dict[str, Any]]):
    """Store that discards retained forecasts from older storage versions."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        return None

# The upstream library performs the API request without any timeout, so an
# unreachable API can hang a refresh (and config entry setup) indefinitely.
API_TIMEOUT_SECONDS = 60


def storage_key(entry_id: str) -> str:
    """Return the storage key for the retained forecast of a config entry."""
    return f"{DOMAIN}.{entry_id}"


def _config_fingerprint(entry: ConfigEntry) -> str:
    """Fingerprint the settings that affect forecast values.

    A retained forecast computed with a different configuration (e.g. changed
    azimuth or panel power) must not be served after an options reload.
    """
    values = {**entry.data, **entry.options}
    return json.dumps(values, sort_keys=True, default=str)


def _datetime_dict_to_json(data: dict[datetime, int]) -> dict[str, int]:
    return {timestamp.isoformat(): value for timestamp, value in data.items()}


def _datetime_dict_from_json(data: dict[str, int]) -> dict[datetime, int]:
    return {datetime.fromisoformat(timestamp): value for timestamp, value in data.items()}


def _date_dict_from_json(data: dict[str, int]) -> dict[date, int]:
    return {date.fromisoformat(day): value for day, value in data.items()}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _normalize_array_value(value: Any, array_count: int, transform: Any = None) -> Any:
    """Normalize scalar or sequence values to scalar or list for the forecast API."""
    if _is_sequence(value):
        normalized = list(value)
        if len(normalized) == 1 and array_count > 1:
            normalized = normalized * array_count
        elif len(normalized) != array_count:
            raise ValueError(
                "Multi-array configuration has inconsistent list lengths "
                f"({len(normalized)} vs {array_count})."
            )
        if transform is not None:
            normalized = [transform(item) for item in normalized]
        return normalized

    if transform is not None:
        value = transform(value)

    if array_count > 1:
        return [value] * array_count
    return value


def _resolve_array_count(*values: Any) -> int:
    lengths = [len(value) for value in values if _is_sequence(value)]
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


def _entry_value(entry: ConfigEntry, key: str) -> Any:
    """Get config value from options with fallback to entry data."""
    return entry.options.get(key, entry.data.get(key))

def checkHorizonFile(horizon_filepath):
    """Read a tab-separated horizon profile and validate its angles."""
    horizon = []
    try:
        with open(horizon_filepath, encoding="utf-8") as horizon_file:
            for line_number, line in enumerate(horizon_file, start=1):
                line = line.partition("#")[0].strip()
                if not line:
                    continue
                columns = line.split("\t")
                if len(columns) != 2:
                    return None, (
                        f"Invalid horizon file: Line {line_number} must contain "
                        "exactly two tab-separated numbers."
                    )
                try:
                    azimuth, elevation = (float(value) for value in columns)
                except ValueError:
                    return None, (
                        f"Invalid horizon file: Line {line_number} must contain "
                        "numbers with decimal points."
                    )
                if not (isfinite(azimuth) and isfinite(elevation)):
                    return None, (
                        f"Invalid horizon file: Line {line_number} contains "
                        "a non-finite angle."
                    )
                if not 0 <= azimuth <= 360 or not -90 <= elevation <= 90:
                    return None, (
                        f"Invalid horizon file: Line {line_number} must have "
                        "azimuth from 0 to 360 and elevation from -90 to 90 degrees."
                    )
                horizon.append((azimuth, elevation))
    except FileNotFoundError:
        return None, (
            f"Invalid horizon file: Horizon file '{horizon_filepath}' not found! "
            "Specify a path outside the integration directory, e.g. '/config/www/horizon.txt'."
        )
    except (OSError, UnicodeError) as err:
        return None, (
            f"Invalid horizon file: Cannot read '{horizon_filepath}' "
            f"as UTF-8 text ({type(err).__name__})."
        )

    if len(horizon) < 2:
        return None, "Invalid horizon file: At least two rows are required."
    if horizon[0][0] != 0 or horizon[-1][0] != 360:
        return None, "Invalid horizon file: Azimuth must start at 0 and end at 360 degrees."
    if any(right[0] <= left[0] for left, right in zip(horizon, horizon[1:])):
        return None, "Invalid horizon file: Azimuth values must be strictly increasing."
    return tuple(horizon), ""

class OpenMeteoSolarForecastDataUpdateCoordinator(DataUpdateCoordinator[Estimate]):
    """The Solar Forecast Data Update Coordinator."""

    config_entry: ConfigEntry
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        horizon_map: tuple[tuple[float, float], ...] | list[tuple[tuple[float, float], ...]],
    ) -> None:
        """Initialize the Solar Forecast coordinator."""
        self.config_entry = entry

        # Our option flow may cause it to be an empty string,
        # this if statement is here to catch that.
        api_key = entry.options.get(CONF_API_KEY) or None

        # Handle new options that were added after the initial release
        ac_kwp = entry.options.get(CONF_INVERTER_POWER, 0)
        ac_kwp = ac_kwp / 1000 if ac_kwp else None
        self._last_successful_update: datetime | None = None
        self._store: Store[dict[str, Any]] = RetainedForecastStore(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        self._config_fingerprint = _config_fingerprint(entry)

        array_count = _resolve_array_count(
            _entry_value(entry, CONF_LATITUDE),
            _entry_value(entry, CONF_LONGITUDE),
            entry.options[CONF_DECLINATION],
            entry.options[CONF_AZIMUTH],
            entry.options[CONF_MODULES_POWER],
            entry.options.get(CONF_ARRAY_INVERTER_POWER, 0),
            entry.options.get(CONF_EFFICIENCY_FACTOR, 1.0),
            entry.options.get(CONF_TRACKING, "none"),
            entry.options.get(CONF_USE_HORIZON, False),
            entry.options.get(CONF_PARTIAL_SHADING, False),
        )

        latitude = _normalize_array_value(
            _entry_value(entry, CONF_LATITUDE), array_count
        )
        longitude = _normalize_array_value(
            _entry_value(entry, CONF_LONGITUDE), array_count
        )
        azimuth = _normalize_array_value(
            entry.options[CONF_AZIMUTH],
            array_count,
            transform=lambda value: value - 180,
        )
        dc_kwp = _normalize_array_value(
            entry.options[CONF_MODULES_POWER],
            array_count,
            transform=lambda value: value / 1000,
        )
        declination = _normalize_array_value(
            entry.options[CONF_DECLINATION],
            array_count,
        )
        efficiency_factor = _normalize_array_value(
            entry.options.get(CONF_EFFICIENCY_FACTOR, 1.0),
            array_count,
        )
        tracking = _normalize_array_value(
            entry.options.get(CONF_TRACKING, "none"),
            array_count,
        )
        use_horizon = _normalize_array_value(
            entry.options.get(CONF_USE_HORIZON, False),
            array_count,
        )
        partial_shading = _normalize_array_value(
            entry.options.get(CONF_PARTIAL_SHADING, False),
            array_count,
        )

        # Per-array inverter capacities (0 = no dedicated inverter for that
        # array). If any array has its own inverter, pass a list to the
        # library so each array's output is clamped individually; this
        # overrides the shared inverter capacity configured above.
        array_ac_kwp = _normalize_array_value(
            entry.options.get(CONF_ARRAY_INVERTER_POWER, 0),
            array_count,
            transform=lambda value: value / 1000 if value else None,
        )
        if _is_sequence(array_ac_kwp):
            if any(value is not None for value in array_ac_kwp):
                ac_kwp = list(array_ac_kwp)
        elif array_ac_kwp is not None:
            # Single array with its own inverter: behaves like a shared one.
            ac_kwp = array_ac_kwp

        self.forecast = OpenMeteoSolarForecast(
            api_key=api_key,
            session=async_get_clientsession(hass),
            latitude=latitude,
            longitude=longitude,
            azimuth=azimuth,
            base_url=entry.options[CONF_BASE_URL],
            ac_kwp=ac_kwp,
            dc_kwp=dc_kwp,
            declination=declination,
            efficiency_factor=efficiency_factor,
            tracking=tracking,
            damping_morning=entry.options.get(CONF_DAMPING_MORNING, 0.0),
            damping_evening=entry.options.get(CONF_DAMPING_EVENING, 0.0),
            use_horizon=use_horizon,
            partial_shading=partial_shading,
            horizon_map=horizon_map,
            max_snowcover_depth_cm=entry.options.get(CONF_MAX_SNOWCOVER_DEPTH_CM, 0.0),
            weather_model=entry.options.get(CONF_MODEL, "best_match"),
        )

        update_interval = timedelta(minutes=30)

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_load_retained_estimate(self) -> Estimate | None:
        """Load the retained forecast persisted across restarts."""
        stored = await self._store.async_load()
        if not stored:
            return None

        if stored.get("config_fingerprint") != self._config_fingerprint:
            LOGGER.debug(
                "Discarding retained forecast computed with a different configuration"
            )
            return None

        try:
            last_update = stored["last_successful_update"]
            estimate = Estimate(
                watts=_datetime_dict_from_json(stored["watts"]),
                wh_period_15m=_datetime_dict_from_json(stored["wh_period_15m"]),
                wh_period=_datetime_dict_from_json(stored["wh_period"]),
                wh_days=_date_dict_from_json(stored["wh_days"]),
                api_timezone=timezone(
                    timedelta(seconds=stored["api_timezone_offset"])
                ),
            )
        except (KeyError, TypeError, ValueError):
            LOGGER.warning("Discarding malformed retained forecast data")
            return None

        self._last_successful_update = dt_util.parse_datetime(last_update)
        return estimate

    def _save_retained_estimate(self, estimate: Estimate) -> None:
        """Persist the forecast so retention survives restarts and reloads."""
        data = {
            "config_fingerprint": self._config_fingerprint,
            "last_successful_update": self._last_successful_update.isoformat(),
            "watts": _datetime_dict_to_json(estimate.watts),
            "wh_period": _datetime_dict_to_json(estimate.wh_period),
            "wh_days": _datetime_dict_to_json(estimate.wh_days),
            "wh_period_15m": _datetime_dict_to_json(estimate.wh_period_15m),
            "api_timezone_offset": estimate.api_timezone.utcoffset(
                None
            ).total_seconds(),
        }
        self._store.async_delay_save(lambda: data, 60)

    async def _async_update_data(self) -> Estimate:
        """Fetch Open-Meteo Solar Forecast estimates."""
        # On the first refresh after a restart or reload, reuse the stored
        # forecast if it is younger than the update interval instead of
        # hitting the API again.
        if self.data is None:
            retained = await self._async_load_retained_estimate()
            if (
                retained is not None
                and self._last_successful_update is not None
                and dt_util.utcnow() - self._last_successful_update
                < self.update_interval
            ):
                LOGGER.debug(
                    "Using stored forecast from %s, skipping fetch",
                    self._last_successful_update,
                )
                return retained

        try:
            async with asyncio.timeout(API_TIMEOUT_SECONDS):
                estimate = await self.forecast.estimate()
        except Exception as err:
            retained = self.data
            if retained is None:
                retained = await self._async_load_retained_estimate()
            if retained is None:
                raise UpdateFailed(f"Error communicating with API: {err}") from err

            LOGGER.warning(
                "Unable to refresh forecast data, using retained forecast",
                exc_info=err,
            )
            return retained

        self._last_successful_update = dt_util.utcnow()
        self._save_retained_estimate(estimate)
        return estimate
    
    
