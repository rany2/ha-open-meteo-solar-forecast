"""Expired forecasts must not be presented as valid zero production."""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from open_meteo_solar_forecast import Estimate

from custom_components.open_meteo_solar_forecast.const import DOMAIN
from custom_components.open_meteo_solar_forecast import (
    coordinator as coordinator_module,
)
from custom_components.open_meteo_solar_forecast.coordinator import (
    LOGGER,
    OpenMeteoSolarForecastDataUpdateCoordinator,
)
from custom_components.open_meteo_solar_forecast.energy import async_get_solar_forecast
from custom_components.open_meteo_solar_forecast.sensor import (
    SENSORS,
    OpenMeteoSolarForecastSensorEntity,
)


class ForecastExpiryTests(unittest.IsolatedAsyncioTestCase):
    """Cover startup, runtime expiry and individual sensor periods."""

    async def asyncSetUp(self):
        self.now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        self.clock = patch.object(Estimate, "now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.hass = HomeAssistant(".")
        self.coordinator = object.__new__(OpenMeteoSolarForecastDataUpdateCoordinator)
        DataUpdateCoordinator.__init__(
            self.coordinator,
            self.hass,
            LOGGER,
            name="test",
            config_entry=None,
            update_interval=timedelta(minutes=30),
        )
        self.coordinator.config_entry = SimpleNamespace(title="Test", entry_id="test")
        self.coordinator.forecast = Mock(estimate=AsyncMock(side_effect=TimeoutError()))
        self.coordinator._store = Mock(async_load=AsyncMock(return_value=None))
        self.coordinator._config_fingerprint = "test"
        self.coordinator._last_successful_update = None
        self.hass.data[DOMAIN] = {"test": self.coordinator}

    def estimate(self, start=None):
        start = self.now if start is None else start
        return Estimate(
            watts={start: 0},
            wh_period={start.replace(minute=0): 0},
            wh_days={start.date(): 0},
            api_timezone=UTC,
            wh_period_15m={start: 0},
        )

    def sensor(self, key):
        return OpenMeteoSolarForecastSensorEntity(
            entry_id="test",
            coordinator=self.coordinator,
            entity_description=next(
                description for description in SENSORS if description.key == key
            ),
        )

    async def test_runtime_expiry_marks_coordinator_unavailable(self):
        self.coordinator.data = self.estimate(self.now - timedelta(minutes=15))
        with self.assertLogs(LOGGER, level="ERROR"):
            await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)
        self.assertIsNone(await async_get_solar_forecast(self.hass, "test"))
        self.assertFalse(self.sensor("energy_production_today").available)

    async def test_recent_but_expired_disk_cache_does_not_skip_request(self):
        estimate = self.estimate(self.now - timedelta(minutes=15))
        self.coordinator._last_successful_update = self.now - timedelta(minutes=1)
        self.coordinator._save_retained_estimate(estimate)
        data = self.coordinator._store.async_delay_save.call_args.args[0]()
        self.coordinator._store.async_load.return_value = data
        with patch(
            "custom_components.open_meteo_solar_forecast.coordinator.dt_util.utcnow",
            return_value=self.now,
        ):
            with self.assertLogs(LOGGER, level="ERROR"):
                await self.coordinator.async_refresh()
        self.coordinator.forecast.estimate.assert_awaited_once()
        self.assertFalse(self.coordinator.last_update_success)

    async def test_still_valid_zero_forecast_survives_api_failure(self):
        retained = self.estimate()
        self.coordinator.data = retained
        with self.assertLogs(LOGGER, level="WARNING"):
            await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.assertIs(self.coordinator.data, retained)
        self.assertTrue(self.sensor("power_production_now").available)
        self.assertEqual(self.sensor("power_production_now").native_value, 0)
        self.assertIsNotNone(await async_get_solar_forecast(self.hass, "test"))

    async def test_sensor_periods_outside_forecast_are_unavailable(self):
        self.coordinator.data = self.estimate()
        for key in (
            "energy_production_tomorrow",
            "energy_production_d7",
            "power_highest_peak_time_tomorrow",
            "energy_next_hour",
            "power_production_next_15minutes",
            "power_production_next_24hours",
        ):
            with self.subTest(key=key):
                self.assertFalse(self.sensor(key).available)
        for key in (
            "energy_production_today",
            "power_highest_peak_time_today",
            "energy_current_hour",
        ):
            with self.subTest(key=key):
                self.assertTrue(self.sensor(key).available)

    async def test_timer_detects_expiry_before_next_api_refresh(self):
        self.coordinator.data = self.estimate(self.now - timedelta(minutes=15))
        self.assertTrue(self.coordinator.last_update_success)
        self.assertFalse(self.sensor("power_production_now").available)
        self.assertIsNone(await async_get_solar_forecast(self.hass, "test"))

    async def test_empty_response_is_not_a_successful_forecast(self):
        self.coordinator.forecast.estimate = AsyncMock(
            return_value=Estimate({}, {}, {}, UTC)
        )
        with self.assertLogs(LOGGER, level="ERROR"):
            await self.coordinator.async_refresh()
        self.assertFalse(self.coordinator.last_update_success)

    async def test_valid_response_recovers_after_failure(self):
        self.coordinator.last_update_success = False
        self.coordinator.forecast.estimate = AsyncMock(return_value=self.estimate())
        await self.coordinator.async_refresh()
        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(self.sensor("energy_production_today").available)

    def test_interval_boundaries_and_timezone(self):
        estimate = self.estimate()
        for offset, expected in ((-1, False), (0, True), (899, True), (900, False)):
            with self.subTest(offset=offset):
                self.assertEqual(
                    coordinator_module.forecast_covers_time(
                        estimate, self.now + timedelta(seconds=offset)
                    ),
                    expected,
                )
        self.assertTrue(
            coordinator_module.forecast_covers_time(estimate, self.now.astimezone())
        )
