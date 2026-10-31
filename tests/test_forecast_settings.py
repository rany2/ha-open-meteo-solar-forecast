"""Configure request frequency and forecast length (library issue #52)."""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from homeassistant.core import HomeAssistant
import voluptuous as vol
from open_meteo_solar_forecast import Estimate

from custom_components.open_meteo_solar_forecast.config_flow import (
    OpenMeteoSolarForecastFlowHandler,
    OpenMeteoSolarForecastOptionFlowHandler,
)
from custom_components.open_meteo_solar_forecast.coordinator import (
    OpenMeteoSolarForecastDataUpdateCoordinator,
)
from custom_components.open_meteo_solar_forecast.sensor import (
    SENSORS,
    OpenMeteoSolarForecastSensorEntity,
)


class ForecastSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant(".")
        self.hass.config.latitude = 50.0
        self.hass.config.longitude = 10.0
        self.entry = SimpleNamespace(
            entry_id="test",
            title="Test",
            update_listeners=[object()],
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "modules_power": 1000,
                "azimuth": 180,
                "declination": 25,
            },
        )
        self.enterContext(patch("homeassistant.helpers.frame.report_usage"))
        self.enterContext(
            patch(
                "custom_components.open_meteo_solar_forecast.coordinator.async_get_clientsession",
                return_value=Mock(),
            )
        )

    def coordinator(self):
        coordinator = OpenMeteoSolarForecastDataUpdateCoordinator(
            self.hass, self.entry, ((0.0, 0.0), (360.0, 0.0))
        )
        coordinator.config_entry = self.entry
        return coordinator

    async def test_setup_persists_custom_request_settings(self):
        flow = OpenMeteoSolarForecastFlowHandler()
        flow.hass = self.hass
        form = await flow.async_step_user()
        array = await flow.async_step_user(
            form["data_schema"](
                {
                    "update_interval": 120,
                    "forecast_days": 7,
                }
            )
        )
        result = await flow.async_step_array(
            array["data_schema"]({"modules_power": 1000})
        )
        self.assertEqual(result["options"]["update_interval"], 120)
        self.assertEqual(result["options"]["forecast_days"], 7)

    async def test_options_show_and_preserve_stored_request_settings(self):
        self.entry.options.update(update_interval=180, forecast_days=5)
        flow = OpenMeteoSolarForecastOptionFlowHandler()
        flow.hass = self.hass
        with patch.object(
            type(flow),
            "config_entry",
            new_callable=PropertyMock,
            return_value=self.entry,
        ):
            form = await flow.async_step_init()
            common = form["data_schema"]({})
            self.assertEqual(common["update_interval"], 180)
            self.assertEqual(common["forecast_days"], 5)
            array = await flow.async_step_init(common)
            result = await flow.async_step_array(array["data_schema"]({}))
        self.assertEqual(result["data"]["update_interval"], 180)
        self.assertEqual(result["data"]["forecast_days"], 5)

    async def test_defaults_and_bounds(self):
        flow = OpenMeteoSolarForecastFlowHandler()
        flow.hass = self.hass
        schema = (await flow.async_step_user())["data_schema"]
        defaults = schema({})
        self.assertEqual(defaults["update_interval"], 30)
        self.assertEqual(defaults["forecast_days"], 16)
        for values in (
            {"update_interval": 29},
            {"update_interval": 1441},
            {"forecast_days": 1},
            {"forecast_days": 17},
        ):
            with self.subTest(values=values), self.assertRaises(vol.Invalid):
                schema(values)
        for values in (
            {"update_interval": 30, "forecast_days": 2},
            {"update_interval": 1440, "forecast_days": 16},
        ):
            self.assertEqual({key: schema(values)[key] for key in values}, values)

    async def test_coordinator_uses_settings_and_legacy_defaults(self):
        default = self.coordinator()
        self.assertEqual(default.update_interval, timedelta(minutes=30))
        self.assertEqual(default.forecast.forecast_days, 16)
        self.entry.options.update(update_interval=120, forecast_days=7)
        changed = self.coordinator()
        self.assertEqual(changed.update_interval, timedelta(hours=2))
        self.assertEqual(changed.forecast.forecast_days, 7)

    async def test_short_forecast_marks_missing_days_and_power_unavailable(self):
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        tomorrow = now + timedelta(days=1)
        coordinator = self.coordinator()
        coordinator.data = Estimate(
            {now: 1000, tomorrow: 1000},
            {now: 250},
            {now.date(): 250, tomorrow.date(): 250},
            UTC,
        )
        for key, expected in (
            ("energy_production_today", True),
            ("energy_production_tomorrow", True),
            ("energy_production_d2", False),
            ("energy_production_d7", False),
            ("power_highest_peak_time_tomorrow", True),
            ("power_production_next_hour", False),
            ("power_production_next_24hours", True),
            ("energy_next_hour", False),
        ):
            with self.subTest(key=key), patch.object(Estimate, "now", return_value=now):
                sensor = OpenMeteoSolarForecastSensorEntity(
                    entry_id="test",
                    coordinator=coordinator,
                    entity_description=next(
                        item for item in SENSORS if item.key == key
                    ),
                )
                self.assertEqual(sensor.available, expected)
