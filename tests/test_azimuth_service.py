"""Azimuth automations update the intended arrays without reload storms."""

import unittest
from datetime import UTC, datetime, timedelta
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
import voluptuous as vol

from custom_components import open_meteo_solar_forecast as integration
from custom_components.open_meteo_solar_forecast import azimuth
from custom_components.open_meteo_solar_forecast.const import DOMAIN


class AzimuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant(".")
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.clock = 10000.0
        self.timers = []
        self.enterContext(
            patch.object(azimuth, "monotonic", side_effect=lambda: self.clock)
        )
        self.enterContext(
            patch.object(azimuth, "async_call_later", side_effect=self.schedule)
        )
        for method in ("_async_schedule_save", "_async_dispatch"):
            self.enterContext(patch.object(self.hass.config_entries, method))
        self.reload = self.enterContext(
            patch.object(self.hass.config_entries, "async_reload", AsyncMock())
        )
        self.enterContext(
            patch.object(
                self.hass.config_entries, "async_forward_entry_setups", AsyncMock()
            )
        )
        await integration.async_setup(self.hass, {})

    def schedule(self, hass, delay, action):
        timer = {"delay": delay, "action": action, "cancelled": False}
        self.timers.append(timer)
        return lambda: timer.update(cancelled=True)

    async def fire(self, timer=None):
        timer = timer or self.timers[-1]
        self.assertFalse(timer["cancelled"])
        self.clock += timer["delay"]
        timer["action"](datetime(2026, 6, 1, tzinfo=UTC))
        await self.hass.async_block_till_done()

    async def add_entry(self, entry_id="test", **options):
        entry = ConfigEntry(
            domain=DOMAIN,
            entry_id=entry_id,
            title=entry_id,
            version=1,
            minor_version=1,
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "azimuth": 180,
                "declination": 25,
                "modules_power": 1000,
                **options,
            },
            source="user",
            unique_id=None,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
            state=ConfigEntryState.LOADED,
        )
        self.hass.config_entries._entries[entry.entry_id] = entry
        coordinator = SimpleNamespace(
            async_config_entry_first_refresh=AsyncMock(),
            update_interval=timedelta(minutes=30),
        )
        with patch.object(
            integration,
            "OpenMeteoSolarForecastDataUpdateCoordinator",
            return_value=coordinator,
        ):
            await integration.async_setup_entry(self.hass, entry)
        return entry

    async def call(self, angle=90, entry_id="test", context=None, **data):
        await self.hass.services.async_call(
            DOMAIN,
            "update_array_azimuth",
            {"config_entry_id": entry_id, "azimuth": angle, **data},
            blocking=True,
            context=context,
        )
        await self.hass.async_block_till_done()

    async def test_batch_updates_only_selected_arrays_and_reloads_once(self):
        entry = await self.add_entry(azimuth=[90, 270], modules_power=[1000, 2000])
        original = dict(entry.options)
        await self.call(100, array_number=1)
        await self.call(280, array_number=2)
        await self.call(110, array_number=1)
        self.assertEqual(dict(entry.options), original)
        self.assertEqual(len(self.timers), 1)
        self.reload.assert_not_awaited()
        await self.fire()
        self.assertEqual(entry.options["azimuth"], [110, 280])
        self.assertEqual(entry.options["modules_power"], [1000, 2000])
        self.assertEqual(entry.data, {"latitude": 50.0, "longitude": 10.0})
        self.reload.assert_awaited_once_with(entry.entry_id)

    async def test_repeated_calls_keep_latest_value_until_rate_limit_expires(self):
        entry = await self.add_entry()
        await self.call(90)
        await self.fire()
        for angle in (100, 110, 120):
            await self.call(angle)
        self.assertEqual(entry.options["azimuth"], 90)
        self.assertEqual(len(self.timers), 2)
        self.assertEqual(self.timers[-1]["delay"], 1800)
        self.reload.assert_awaited_once()
        await self.fire()
        self.assertEqual(entry.options["azimuth"], 120)
        self.assertEqual(self.reload.await_count, 2)

    async def test_longer_configured_interval_is_respected(self):
        await self.add_entry()
        self.hass.data[DOMAIN]["test"].update_interval = timedelta(hours=2)
        await self.call(90)
        await self.fire()
        self.clock += 600
        await self.call(100)
        self.assertEqual(self.timers[-1]["delay"], 6600)

    async def test_entries_have_independent_batches(self):
        first = await self.add_entry("first")
        second = await self.add_entry("second")
        await self.call(90, "first")
        await self.call(270, "second")
        await self.fire(self.timers[0])
        self.assertEqual(first.options["azimuth"], 90)
        self.assertEqual(second.options["azimuth"], 180)
        await self.fire(self.timers[1])
        self.assertEqual(second.options["azimuth"], 270)

    async def test_noop_and_return_to_current_heading_cancel_pending_change(self):
        await self.add_entry(azimuth=360)
        await self.call(0)
        self.assertEqual(self.timers, [])
        await self.call(90)
        await self.call(360)
        self.assertTrue(self.timers[-1]["cancelled"])
        self.reload.assert_not_awaited()

    async def test_cancelling_one_array_keeps_the_other_pending_change(self):
        entry = await self.add_entry(azimuth=[90, 270])
        await self.call(100, array_number=1)
        await self.call(280, array_number=2)
        await self.call(90, array_number=1)
        await self.fire()
        self.assertEqual(entry.options["azimuth"], [90, 280])
        self.reload.assert_awaited_once()

    async def test_shutdown_cancels_pending_changes(self):
        await self.add_entry()
        await self.call(90)
        self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await self.hass.async_block_till_done()
        self.assertTrue(self.timers[-1]["cancelled"])
        self.reload.assert_not_awaited()

    async def test_broadcast_azimuth_expands_without_changing_other_arrays(self):
        entry = await self.add_entry(modules_power=[1000, 2000])
        await self.call(270, array_number=2)
        await self.fire()
        self.assertEqual(entry.options["azimuth"], [180, 270])

    async def test_manual_edits_are_not_overwritten_by_queued_changes(self):
        entry = await self.add_entry()
        await self.call(90)
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, "azimuth": 45}
        )
        await self.hass.async_block_till_done()
        self.reload.reset_mock()
        await self.fire()
        self.assertEqual(entry.options["azimuth"], 45)
        self.reload.assert_not_awaited()

    async def test_removed_entry_is_not_updated(self):
        entry = await self.add_entry()
        await self.call(90)
        self.hass.config_entries._entries.pop(entry.entry_id)
        await self.fire()
        self.reload.assert_not_awaited()

    async def test_invalid_or_ambiguous_targets_are_rejected(self):
        await self.add_entry(modules_power=[1000, 2000])
        for data in ({}, {"array_number": 3}, {"entry_id": "missing"}):
            with self.subTest(data=data), self.assertRaises(ServiceValidationError):
                await self.call(**data)
        self.assertEqual(self.timers, [])

    async def test_ignored_tracker_azimuth_is_rejected(self):
        for mode in ("azimuth", "dual"):
            with self.subTest(mode=mode):
                await self.add_entry(mode, tracking=mode)
                with self.assertRaises(ServiceValidationError):
                    await self.call(entry_id=mode)
        self.assertEqual(self.timers, [])

    async def test_invalid_angles_and_array_numbers_are_rejected(self):
        await self.add_entry()
        for data in (
            {"angle": -1},
            {"angle": 361},
            {"angle": float("nan")},
            {"angle": float("inf")},
            {"array_number": 0},
            {"array_number": 1.5},
        ):
            with self.subTest(data=data), self.assertRaises(vol.Invalid):
                await self.call(**data)
        self.assertEqual(self.timers, [])

    async def test_non_admin_cannot_queue_updates(self):
        await self.add_entry()
        self.hass.auth = Mock(
            async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=False))
        )
        with self.assertRaises(Unauthorized):
            await self.call(context=Context(user_id="non-admin"))
        self.assertEqual(self.timers, [])
