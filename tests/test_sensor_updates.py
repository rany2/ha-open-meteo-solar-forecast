"""Daily forecasts should be written only when their forecast day changes."""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.open_meteo_solar_forecast.sensor import (
    OpenMeteoSolarForecastSensorEntity,
)


class SensorUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_forecast_waits_for_api_calendar_rollover(self):
        current = datetime(2026, 10, 12, 23, 59, tzinfo=UTC)
        estimate = SimpleNamespace(now=lambda: current)
        write = Mock()
        entity = SimpleNamespace(
            enabled=True,
            coordinator=SimpleNamespace(data=estimate),
            entity_description=SimpleNamespace(key="energy_production_today"),
            _TIME_DEPENDENT_KEYS=OpenMeteoSolarForecastSensorEntity._TIME_DEPENDENT_KEYS,
            _last_forecast_date=current.date(),
            async_write_ha_state=write,
        )
        callback = OpenMeteoSolarForecastSensorEntity._update_callback

        await callback(entity, current)
        write.assert_not_called()
        current = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
        await callback(entity, current)
        write.assert_called_once_with()
        await callback(entity, current)
        self.assertEqual(write.call_count, 1)

    async def test_rolling_forecast_still_updates_every_minute(self):
        current = datetime(2026, 10, 12, 23, 59, tzinfo=UTC)
        write = Mock()
        entity = SimpleNamespace(
            enabled=True,
            coordinator=SimpleNamespace(data=SimpleNamespace(now=lambda: current)),
            entity_description=SimpleNamespace(key="power_production_now"),
            _TIME_DEPENDENT_KEYS=OpenMeteoSolarForecastSensorEntity._TIME_DEPENDENT_KEYS,
            _last_forecast_date=current.date(),
            async_write_ha_state=write,
        )
        callback = OpenMeteoSolarForecastSensorEntity._update_callback

        await callback(entity, current)
        await callback(entity, current)
        self.assertEqual(write.call_count, 2)
