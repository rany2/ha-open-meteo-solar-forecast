"""Verify tracker options reach the weather request without fixed-axis overrides."""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from open_meteo_solar_forecast import OpenMeteoSolarForecast

from custom_components.open_meteo_solar_forecast.coordinator import (
    OpenMeteoSolarForecastDataUpdateCoordinator,
)


def weather():
    """Constant synthetic weather isolates orientation handling from the model."""
    noon = datetime(2026, 6, 1, 12, tzinfo=UTC)
    return {
        "utc_offset_seconds": 0,
        "minutely_15": {
            "time": [
                int((noon + timedelta(minutes=15 * i)).timestamp()) for i in range(4)
            ],
            "temperature_2m": [25] * 4,
            "global_tilted_irradiance": [1000] * 4,
            "global_tilted_irradiance_instant": [1000] * 4,
            "diffuse_radiation": [100] * 4,
            "diffuse_radiation_instant": [100] * 4,
            "direct_radiation": [900] * 4,
            "direct_radiation_instant": [900] * 4,
            "snow_depth": [0] * 4,
        },
        "daily": {
            "time": [int(noon.replace(hour=0).timestamp())],
            "sunrise": [int(noon.replace(hour=6).timestamp())],
            "sunset": [int(noon.replace(hour=18).timestamp())],
        },
    }


class TrackerRequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant(".")
        self.enterContext(patch("homeassistant.helpers.frame.report_usage"))
        self.enterContext(
            patch(
                "custom_components.open_meteo_solar_forecast.coordinator.async_get_clientsession",
                return_value=Mock(),
            )
        )

    def coordinator(self, **options):
        entry = SimpleNamespace(
            entry_id="test",
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "modules_power": 1000,
                "declination": 25,
                "azimuth": 180,
                "efficiency_factor": 1,
                **options,
            },
        )
        return OpenMeteoSolarForecastDataUpdateCoordinator(
            self.hass, entry, ((0.0, 0.0), (360.0, 0.0))
        )

    async def test_each_array_passes_the_correct_fixed_and_tracked_axes(self):
        coordinator = self.coordinator(
            modules_power=[1000] * 4,
            tracking=["none", "azimuth", "tilt", "dual"],
            azimuth=[90, 180, 270, 360],
            declination=[20, 30, 40, 50],
        )
        with patch.object(
            OpenMeteoSolarForecast, "_request", AsyncMock(return_value=weather())
        ) as request:
            await coordinator.forecast.estimate()
        actual = [
            (call.kwargs["params"]["azimuth"], call.kwargs["params"]["tilt"])
            for call in request.await_args_list
        ]
        self.assertEqual(
            actual, [("-90", "20"), ("nan", "30"), ("90", "nan"), ("nan", "nan")]
        )

    async def test_dual_axis_ignores_stored_angles_and_keeps_temperature_correction(
        self,
    ):
        results = []
        for azimuth, declination in ((0, 0), (180, 40), (360, 90)):
            coordinator = self.coordinator(
                tracking="dual", azimuth=azimuth, declination=declination
            )
            with patch.object(
                OpenMeteoSolarForecast, "_request", AsyncMock(return_value=weather())
            ):
                results.append(await coordinator.forecast.estimate())
        self.assertTrue(results[0].watts)
        for result in results:
            self.assertEqual(result.watts, results[0].watts)
            self.assertEqual(result.wh_days, results[0].wh_days)
            # At 25°C ambient and 1000 W/m², the current library models
            # 59.2°C cells and a 13.68% reduction even with DC efficiency 1.
            self.assertEqual(set(result.watts.values()), {863})
