"""Options changes must recover entries that could not finish setup."""

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components import open_meteo_solar_forecast as integration
from custom_components.open_meteo_solar_forecast.config_flow import (
    OpenMeteoSolarForecastOptionFlowHandler,
)


class OptionsReloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.hass = HomeAssistant(directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.entry = ConfigEntry(
            domain=integration.DOMAIN,
            entry_id="test",
            title="Test",
            version=1,
            minor_version=1,
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "api_key": None,
                "base_url": "https://api.open-meteo.com",
                "model": "best_match",
                "inverter_power": 0,
                "max_snowcover_depth_cm": 0.0,
                "latitude": [50.0, 50.0],
                "longitude": [10.0, 10.0],
                "declination": [25, 35],
                "azimuth": [90, 270],
                "modules_power": [1000, 2000],
                "array_inverter_power": [0, 0],
                "efficiency_factor": [1.0, 1.0],
                "tracking": ["none", "none"],
                "damping_morning": [0.0, 0.0],
                "damping_evening": [0.0, 0.0],
                "use_horizon": [True, True],
                "partial_shading": [False, False],
                "horizon_filepath": [
                    str(self.directory / "missing-east.txt"),
                    str(self.directory / "missing-west.txt"),
                ],
            },
            source="user",
            unique_id=None,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
            state=ConfigEntryState.SETUP_ERROR,
        )
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
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
        self.coordinator = self.enterContext(
            patch.object(
                integration,
                "OpenMeteoSolarForecastDataUpdateCoordinator",
                return_value=SimpleNamespace(
                    async_config_entry_first_refresh=AsyncMock()
                ),
            )
        )
        self.paths = []
        for name, elevation in (("east", 10), ("west", 20)):
            path = self.directory / f"{name}.txt"
            path.write_text(f"0\t{elevation}\n360\t{elevation}\n")
            self.paths.append(str(path))

    async def save_options(self, changes=None):
        flow = OpenMeteoSolarForecastOptionFlowHandler()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        common = await flow.async_step_init()
        array = await flow.async_step_init(common["data_schema"]({}))
        for change in changes or ({}, {}):
            self.reload.assert_not_awaited()
            array = await flow.async_step_array(array["data_schema"](change))
        self.assertEqual(array["type"], "create_entry")
        await self.hass.config_entries.options.async_finish_flow(flow, array)
        await self.hass.async_block_till_done()

    async def fail_setup(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            await integration.async_setup_entry(self.hass, self.entry)
        self.assertEqual(self.entry.update_listeners, [])
        self.coordinator.assert_not_called()

    async def test_corrected_horizon_paths_retry_setup_with_saved_options(self):
        await self.fail_setup()

        async def reload_entry(entry_id):
            self.assertEqual(entry_id, self.entry.entry_id)
            self.assertEqual(self.entry.options["horizon_filepath"], self.paths)
            return await integration.async_setup_entry(self.hass, self.entry)

        self.reload.side_effect = reload_entry
        await self.save_options([{"horizon_filepath": path} for path in self.paths])
        self.reload.assert_awaited_once_with(self.entry.entry_id)
        self.assertEqual(
            self.coordinator.call_args.args[2],
            [((0.0, 10.0), (360.0, 10.0)), ((0.0, 20.0), (360.0, 20.0))],
        )
        self.assertEqual(self.entry.options["modules_power"], [1000, 2000])

    async def test_disabling_horizon_recovers_from_missing_file(self):
        await self.fail_setup()

        async def reload_entry(entry_id):
            return await integration.async_setup_entry(self.hass, self.entry)

        self.reload.side_effect = reload_entry
        await self.save_options([{"use_horizon": False}] * 2)
        self.reload.assert_awaited_once_with(self.entry.entry_id)
        self.assertEqual(
            self.coordinator.call_args.args[2],
            [((0.0, 0.0), (360.0, 0.0))] * 2,
        )

    async def test_loaded_entry_uses_existing_listener_once(self):
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, "horizon_filepath": self.paths},
        )
        await integration.async_setup_entry(self.hass, self.entry)
        self.assertEqual(len(self.entry.update_listeners), 1)
        await self.save_options([{"modules_power": 1500}, {}])
        self.reload.assert_awaited_once_with(self.entry.entry_id)

    async def test_unchanged_options_do_not_retry_failed_setup(self):
        await self.fail_setup()
        await self.save_options()
        self.reload.assert_not_awaited()

    async def test_unchanged_options_do_not_reload_loaded_entry(self):
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, "horizon_filepath": self.paths},
        )
        await integration.async_setup_entry(self.hass, self.entry)
        await self.save_options()
        self.reload.assert_not_awaited()
