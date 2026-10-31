"""Location updates must have an unambiguous target."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import voluptuous as vol
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized

from custom_components import open_meteo_solar_forecast as integration
from custom_components.open_meteo_solar_forecast.const import DOMAIN


class LocationServiceTests(unittest.IsolatedAsyncioTestCase):
    """Use Home Assistant's service registry and input validation."""

    async def asyncSetUp(self):
        self.hass = HomeAssistant(".")
        self.hass.config.latitude = 50.0
        self.hass.config.longitude = 10.0
        self.entries = []
        self.hass.config_entries = Mock(
            async_entries=Mock(side_effect=lambda domain: list(self.entries)),
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        )
        # The integration loader supports components with and without async_setup.
        if hasattr(integration, "async_setup"):
            await integration.async_setup(self.hass, {})

    async def add_entry(self, entry_id, latitude=51.0, longitude=11.0, options=None):
        entry = SimpleNamespace(
            entry_id=entry_id,
            domain=DOMAIN,
            title=entry_id,
            data={"latitude": latitude, "longitude": longitude},
            options=options or {},
            async_on_unload=Mock(),
            add_update_listener=Mock(),
        )
        self.entries.append(entry)
        coordinator = SimpleNamespace(
            config_entry=entry, async_config_entry_first_refresh=AsyncMock()
        )
        with patch.object(
            integration,
            "OpenMeteoSolarForecastDataUpdateCoordinator",
            return_value=coordinator,
        ):
            await integration.async_setup_entry(self.hass, entry)
        return entry

    async def call(self, data=None, context=None):
        await self.hass.services.async_call(
            DOMAIN,
            "update_array_location",
            data or {},
            blocking=True,
            context=context,
        )

    async def test_single_array_legacy_call_uses_ha_location(self):
        entry = await self.add_entry("one")
        await self.call()
        update = self.hass.config_entries.async_update_entry
        self.assertIs(update.call_args.args[0], entry)
        self.assertEqual(update.call_args.kwargs["data"]["latitude"], 50.0)
        self.assertEqual(update.call_args.kwargs["options"]["longitude"], 10.0)

    async def test_explicit_entry_does_not_depend_on_load_order(self):
        first = await self.add_entry("one")
        await self.add_entry("two")
        await self.call(
            {
                "config_entry_id": "one",
                "location_override": {"latitude": 40.0, "longitude": 20.0},
            }
        )
        update = self.hass.config_entries.async_update_entry
        self.assertIs(update.call_args.args[0], first)
        self.assertEqual(update.call_args.kwargs["options"]["latitude"], 40.0)

    async def test_missing_entry_target_is_rejected(self):
        await self.add_entry("one")
        await self.add_entry("two")
        with self.assertRaises(ServiceValidationError):
            await self.call()
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_other_arrays_and_options_are_preserved(self):
        entry = await self.add_entry(
            "one",
            latitude=[50.0, 51.0],
            longitude=[10.0, 11.0],
            options={
                "latitude": [52.0, 53.0],
                "longitude": [12.0, 13.0],
                "azimuth": [90, 270],
            },
        )
        await self.call(
            {
                "array_number": 2,
                "location_override": {"latitude": 40.0, "longitude": 20.0},
            }
        )
        update = self.hass.config_entries.async_update_entry
        self.assertIs(update.call_args.args[0], entry)
        self.assertEqual(
            update.call_args.kwargs["options"],
            {"latitude": [52.0, 40.0], "longitude": [12.0, 20.0], "azimuth": [90, 270]},
        )
        self.assertEqual(update.call_args.kwargs["data"]["latitude"], [52.0, 40.0])
        self.assertEqual(entry.options["latitude"], [52.0, 53.0])

    async def test_broadcast_coordinates_expand_before_editing_one_array(self):
        await self.add_entry("one", options={"azimuth": [90, 270]})
        await self.call({"array_number": 2})
        options = self.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        self.assertEqual(options["latitude"], [51.0, 50.0])
        self.assertEqual(options["longitude"], [11.0, 10.0])

    async def test_missing_or_invalid_array_target_is_rejected(self):
        await self.add_entry("one", latitude=[50.0, 51.0], longitude=[10.0, 11.0])
        for data in ({}, {"array_number": 3}, {"config_entry_id": "missing"}):
            with self.subTest(data=data):
                with self.assertRaises(ServiceValidationError):
                    await self.call(data)
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_coordinates_and_array_number_are_validated(self):
        await self.add_entry("one")
        for data in (
            {"array_number": 0},
            {"location_override": {"latitude": 91, "longitude": 10}},
            {"location_override": {"latitude": 50}},
        ):
            with self.subTest(data=data):
                with self.assertRaises(vol.Invalid):
                    await self.call(data)
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_removed_entry_is_not_retained_by_handler(self):
        first = await self.add_entry("one")
        second = await self.add_entry("two")
        await integration.async_unload_entry(self.hass, second)
        self.entries.remove(second)
        await self.call()
        self.assertIs(
            self.hass.config_entries.async_update_entry.call_args.args[0], first
        )

    async def test_non_admin_cannot_change_configuration(self):
        await self.add_entry("one")
        self.hass.auth = Mock(
            async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=False))
        )
        with self.assertRaises(Unauthorized):
            await self.call(context=Context(user_id="non-admin"))
        self.hass.config_entries.async_update_entry.assert_not_called()
