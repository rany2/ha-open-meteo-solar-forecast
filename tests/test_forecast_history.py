"""Refresh recent weather without downloading the full history each time."""

import unittest
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from open_meteo_solar_forecast import Estimate

from custom_components.open_meteo_solar_forecast.coordinator import (
    LOGGER,
    OpenMeteoSolarForecastDataUpdateCoordinator,
)


class ForecastHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant(".")
        self.now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        self.enterContext(patch.object(Estimate, "now", side_effect=lambda: self.now))
        self.enterContext(
            patch(
                "custom_components.open_meteo_solar_forecast.coordinator.dt_util.utcnow",
                side_effect=lambda: self.now,
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
            },
        )
        self.coordinator = self.make_coordinator()
        self.requests = []

    def make_coordinator(self, stored=None):
        coordinator = OpenMeteoSolarForecastDataUpdateCoordinator(
            self.hass, self.entry, ((0.0, 0.0), (360.0, 0.0))
        )
        coordinator._store = Mock(async_load=AsyncMock(return_value=stored))
        return coordinator

    def estimate(self, offsets=(-5, -1, 0, 1), value=1000, tz=UTC):
        timestamps = [self.now.astimezone(tz) + timedelta(days=day) for day in offsets]
        return Estimate(
            watts=dict.fromkeys(timestamps, value),
            wh_period=dict.fromkeys(timestamps, value / 4),
            wh_period_15m=dict.fromkeys(timestamps, value / 4),
            wh_days=dict.fromkeys((time.date() for time in timestamps), value / 4),
            api_timezone=tz,
        )

    def cached(self, coordinator):
        coordinator._save_retained_estimate(coordinator.data)
        return coordinator._store.async_delay_save.call_args.args[0]()

    def prepare_refresh(self, response=None, last_update=None):
        coordinator = self.coordinator
        coordinator.data = self.estimate()
        coordinator._last_successful_update = last_update or self.now - timedelta(
            hours=1
        )

        async def fetch():
            self.requests.append(coordinator.forecast.past_days)
            return response if response is not None else self.estimate((-1, 0, 1), 200)

        coordinator.forecast.estimate = AsyncMock(side_effect=fetch)

    async def test_first_fetch_and_regular_update_use_actual_library_parameters(self):
        async def weather_request(path, *, params):
            self.requests.append(int(params["past_days"]))
            self.assertEqual(
                params["forecast_days"], str(self.coordinator.forecast.forecast_days)
            )
            start = self.now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=int(params["past_days"]))
            count = (int(params["past_days"]) + int(params["forecast_days"])) * 96
            times = [
                int((start + timedelta(minutes=15 * i)).timestamp())
                for i in range(count)
            ]
            days = [
                int((start + timedelta(days=i)).timestamp()) for i in range(count // 96)
            ]
            return {
                "utc_offset_seconds": 0,
                "minutely_15": {
                    "time": times,
                    "temperature_2m": [20.0] * count,
                    "global_tilted_irradiance": [500.0] * count,
                    "global_tilted_irradiance_instant": [500.0] * count,
                    "diffuse_radiation": [100.0] * count,
                    "diffuse_radiation_instant": [100.0] * count,
                    "direct_radiation": [400.0] * count,
                    "direct_radiation_instant": [400.0] * count,
                    "snow_depth": [0.0] * count,
                },
                "daily": {
                    "time": days,
                    "sunrise": [day + 6 * 3600 for day in days],
                    "sunset": [day + 18 * 3600 for day in days],
                },
            }

        for forecast_days in (16, 7, 2):
            with self.subTest(forecast_days=forecast_days):
                self.entry.options["forecast_days"] = forecast_days
                self.coordinator = self.make_coordinator()
                self.requests.clear()
                self.coordinator.forecast._request = AsyncMock(
                    side_effect=weather_request
                )
                initial = await self.coordinator._async_update_data()
                self.coordinator.data = initial
                self.now += timedelta(minutes=30)
                updated = await self.coordinator._async_update_data()
                self.assertEqual(self.requests, [92, 1])
                # The library may omit instantaneous power at the first raw
                # timestamp because it also needs a preceding temperature.
                # Check the interior and older history independently of that edge.
                edge = self.now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(days=1)
                self.assertEqual(
                    {
                        time: power
                        for time, power in updated.watts.items()
                        if time != edge
                    },
                    {
                        time: power
                        for time, power in initial.watts.items()
                        if time != edge
                    },
                )
                self.assertEqual(updated.wh_period, initial.wh_period)
                self.assertEqual(updated.wh_days, initial.wh_days)
                self.assertEqual(updated.wh_period_15m, initial.wh_period_15m)

    async def test_longer_refresh_interval_reuses_existing_history(self):
        self.prepare_refresh(last_update=self.now - timedelta(minutes=45))
        stored = self.cached(self.coordinator)
        self.entry.options["update_interval"] = 120
        restarted = self.make_coordinator(stored)
        restarted.forecast.estimate = AsyncMock()
        restored = await restarted._async_update_data()
        restarted.forecast.estimate.assert_not_awaited()
        self.assertEqual(restored.wh_period_15m, self.coordinator.data.wh_period_15m)

    async def test_shorter_horizon_discards_old_future_data(self):
        self.prepare_refresh()
        self.coordinator.data = self.estimate((-5, -1, 0, 1, 15))
        stored = self.cached(self.coordinator)
        self.entry.options["forecast_days"] = 2
        restarted = self.make_coordinator(stored)
        fresh = self.estimate((-5, -1, 0, 1), 200)
        restarted.forecast.estimate = AsyncMock(return_value=fresh)
        result = await restarted._async_update_data()
        restarted.forecast.estimate.assert_awaited_once()
        self.assertEqual(restarted.forecast.forecast_days, 2)
        self.assertEqual(result.wh_days, fresh.wh_days)

    async def test_merge_prunes_history_and_replaces_missing_forecast_intervals(self):
        self.prepare_refresh()
        self.coordinator.data = self.estimate((-93, -92, -5, -1, 0, 1, 15))
        result = await self.coordinator._async_update_data()
        expected = self.estimate((-92, -5))
        fresh = self.estimate((-1, 0, 1), 200)
        for field in ("watts", "wh_period", "wh_period_15m", "wh_days"):
            with self.subTest(field=field):
                values = getattr(result, field)
                self.assertEqual(
                    values, getattr(expected, field) | getattr(fresh, field)
                )
                self.assertEqual(list(values), sorted(values))

    async def test_restart_preserves_history_and_fetches_only_missing_days(self):
        self.prepare_refresh(last_update=self.now - timedelta(days=2))
        self.coordinator = self.make_coordinator(self.cached(self.coordinator))
        self.coordinator.forecast.estimate = AsyncMock(
            return_value=self.estimate((-3, -1, 0), 200)
        )
        result = await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.forecast.past_days, 3)
        self.assertEqual(result.watts[self.now - timedelta(days=5)], 1000)
        self.assertEqual(result.watts[self.now], 200)
        stored = self.coordinator._store.async_delay_save.call_args.args[0]()
        restarted = self.make_coordinator(stored)
        restarted.forecast.estimate = AsyncMock()
        restored = await restarted._async_update_data()
        self.assertEqual(restored.watts, result.watts)
        restarted.forecast.estimate.assert_not_awaited()

    async def test_changed_settings_fetch_full_history(self):
        self.prepare_refresh()
        stored = self.cached(self.coordinator)
        self.entry.options["azimuth"] = 90
        self.coordinator = self.make_coordinator(stored)
        self.coordinator.forecast.estimate = AsyncMock(return_value=self.estimate())
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.forecast.past_days, 92)
        self.coordinator.forecast.estimate.assert_awaited_once()

    async def test_failed_update_keeps_history_and_does_not_advance_checkpoint(self):
        self.prepare_refresh()
        retained = self.coordinator.data
        last_update = self.coordinator._last_successful_update
        self.coordinator.forecast.estimate.side_effect = TimeoutError()
        with self.assertLogs(LOGGER, level="WARNING"):
            result = await self.coordinator._async_update_data()
        self.assertIs(result, retained)
        self.assertEqual(self.coordinator._last_successful_update, last_update)
        self.coordinator._store.async_delay_save.assert_not_called()
        self.now += timedelta(days=2)
        self.coordinator.forecast.estimate.side_effect = None
        self.coordinator.forecast.estimate.return_value = self.estimate()
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.forecast.past_days, 3)

    async def test_local_midnight_and_long_outages_expand_requested_history(self):
        for offset, elapsed, expected in ((13, 1, 2), (0, 72, 4), (0, 2400, 92)):
            with self.subTest(offset=offset, elapsed=elapsed):
                tz = timezone(timedelta(hours=offset))
                self.now = datetime(2026, 6, 2, 0, 30, tzinfo=tz).astimezone(UTC)
                self.coordinator = self.make_coordinator()
                self.prepare_refresh(
                    response=self.estimate(tz=tz),
                    last_update=self.now - timedelta(hours=elapsed),
                )
                self.coordinator.data = self.estimate(tz=tz)
                await self.coordinator._async_update_data()
                self.assertEqual(self.coordinator.forecast.past_days, expected)

    async def test_timezone_offset_change_rebuilds_full_history(self):
        tz = timezone(timedelta(hours=1))
        self.prepare_refresh(response=self.estimate((-1, 0, 1), 200, tz))
        result = await self.coordinator._async_update_data()
        self.assertEqual(self.requests, [1, 92])
        self.assertEqual(result.api_timezone, tz)
        self.assertEqual(result.watts, self.estimate((-1, 0, 1), 200, tz).watts)

    async def test_future_cache_timestamp_does_not_skip_full_refresh(self):
        self.prepare_refresh(last_update=self.now + timedelta(hours=1))
        self.coordinator = self.make_coordinator(self.cached(self.coordinator))
        self.coordinator.forecast.estimate = AsyncMock(return_value=self.estimate())
        await self.coordinator._async_update_data()
        self.assertEqual(self.coordinator.forecast.past_days, 92)
        self.coordinator.forecast.estimate.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
