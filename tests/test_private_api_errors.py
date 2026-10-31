"""API errors must not expose request parameters or response bodies."""

import traceback
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientResponseError, RequestInfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.open_meteo_solar_forecast.coordinator import (
    LOGGER,
    OpenMeteoSolarForecastDataUpdateCoordinator,
)
from open_meteo_solar_forecast.exceptions import OpenMeteoSolarForecastError
from open_meteo_solar_forecast import Estimate


class PrivateApiErrorTests(unittest.IsolatedAsyncioTestCase):
    """Check both first-refresh errors and retained-forecast warnings."""

    def coordinator(self, error, retained=None):
        coordinator = object.__new__(OpenMeteoSolarForecastDataUpdateCoordinator)
        DataUpdateCoordinator.__init__(
            coordinator,
            HomeAssistant("."),
            LOGGER,
            name="test",
            config_entry=None,
            update_interval=timedelta(minutes=30),
        )
        coordinator.data = retained
        coordinator.forecast = Mock(estimate=AsyncMock(side_effect=error))
        coordinator._store = Mock(async_load=AsyncMock(return_value=None))
        return coordinator

    def errors(self):
        url = URL(
            "https://example.test/forecast?apikey=private-test-key&latitude=12.345678&longitude=23.456789"
        )
        request = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
        return (
            ClientResponseError(request, (), status=500, message="Server error"),
            OpenMeteoSolarForecastError(
                "Unexpected response", {"response": "private-test-key 12.345678"}
            ),
        )

    def assert_private(self, text):
        for value in ("private-test-key", "12.345678", "23.456789", "example.test"):
            self.assertNotIn(value, text)

    async def test_initial_failure_has_no_sensitive_exception_chain(self):
        for error in self.errors():
            with self.subTest(error=type(error).__name__):
                coordinator = self.coordinator(error)
                try:
                    await coordinator._async_update_data()
                except UpdateFailed as failure:
                    self.assert_private("".join(traceback.format_exception(failure)))
                    self.assertIn(type(error).__name__, str(failure))
                else:
                    self.fail("Expected UpdateFailed")

    async def test_retained_warning_does_not_log_raw_exception(self):
        for error in self.errors():
            with self.subTest(error=type(error).__name__):
                now = datetime(2026, 6, 1, 12, tzinfo=UTC)
                retained = Estimate({now: 1000}, {now: 1000}, {now.date(): 1000}, UTC)
                coordinator = self.coordinator(error, retained)
                with patch.object(Estimate, "now", return_value=now):
                    with self.assertLogs(LOGGER, level="WARNING") as logs:
                        result = await coordinator._async_update_data()
                self.assertIs(result, retained)
                self.assert_private("\n".join(logs.output))
                self.assertIn(type(error).__name__, logs.output[0])
                self.assertIsNone(logs.records[0].exc_info)
