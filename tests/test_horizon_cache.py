"""Retained forecasts must use the current horizon profile."""

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from open_meteo_solar_forecast import Estimate

from custom_components.open_meteo_solar_forecast.coordinator import (
    OpenMeteoSolarForecastDataUpdateCoordinator,
    checkHorizonFile,
)


class HorizonCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "horizon.txt"
        self.hass = HomeAssistant(directory.name)
        self.now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        self.enterContext(patch.object(Estimate, "now", return_value=self.now))
        self.enterContext(
            patch(
                "custom_components.open_meteo_solar_forecast.coordinator.dt_util.utcnow",
                return_value=self.now,
            )
        )
        self.enterContext(patch("homeassistant.helpers.frame.report_usage"))
        self.enterContext(
            patch(
                "custom_components.open_meteo_solar_forecast.coordinator.async_get_clientsession",
                return_value=Mock(),
            )
        )
        self.entry = SimpleNamespace(
            entry_id="test",
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "azimuth": 180,
                "declination": 25,
                "modules_power": 1000,
                "use_horizon": True,
                "horizon_filepath": str(self.path),
            },
        )

    def estimate(self, watts):
        return Estimate(
            watts={self.now: watts},
            wh_period={self.now: watts / 4},
            wh_days={self.now.date(): watts / 4},
            wh_period_15m={self.now: watts / 4},
            api_timezone=UTC,
        )

    def coordinator(self, profile, stored=None, multiple=False):
        self.path.write_text(profile)
        horizon, message = checkHorizonFile(str(self.path))
        self.assertIsNotNone(horizon, message)
        if multiple:
            horizon = [((0.0, 0.0), (360.0, 0.0)), horizon]
        coordinator = OpenMeteoSolarForecastDataUpdateCoordinator(
            self.hass, self.entry, horizon
        )
        coordinator._store = Mock(async_load=AsyncMock(return_value=stored))
        coordinator.forecast.estimate = AsyncMock(return_value=self.estimate(100))
        return coordinator

    def cached(self, coordinator):
        coordinator._last_successful_update = self.now
        coordinator._save_retained_estimate(self.estimate(1000))
        return coordinator._store.async_delay_save.call_args.args[0]()

    async def test_editing_profile_at_same_path_fetches_new_forecast(self):
        before = self.coordinator("0\t0\n360\t0\n")
        after = self.coordinator("0\t80\n360\t80\n", self.cached(before))
        result = await after._async_update_data()
        after.forecast.estimate.assert_awaited_once()
        self.assertEqual(result.watts[self.now], 100)

    async def test_changed_second_array_invalidates_combined_forecast(self):
        self.entry.options.update(
            azimuth=[90, 270],
            modules_power=[1000, 2000],
            use_horizon=[False, True],
        )
        before = self.coordinator("0\t0\n360\t0\n", multiple=True)
        after = self.coordinator(
            "0\t80\n360\t80\n", self.cached(before), multiple=True
        )
        await after._async_update_data()
        after.forecast.estimate.assert_awaited_once()

    async def test_equivalent_profile_keeps_recent_cache(self):
        before = self.coordinator("0\t10\n360\t20\n")
        after = self.coordinator("0.0\t10.0\n360.0\t20.0\n", self.cached(before))
        result = await after._async_update_data()
        after.forecast.estimate.assert_not_awaited()
        self.assertEqual(result.watts[self.now], 1000)

    async def test_api_failure_does_not_restore_forecast_for_old_profile(self):
        before = self.coordinator("0\t0\n360\t0\n")
        after = self.coordinator("0\t80\n360\t80\n", self.cached(before))
        after.forecast.estimate.side_effect = TimeoutError()
        with self.assertRaises(UpdateFailed):
            await after._async_update_data()
