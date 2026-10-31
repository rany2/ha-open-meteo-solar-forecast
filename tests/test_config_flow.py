"""Regression coverage for the multi-step configuration wizard (issue #108).

Run with Home Assistant and the integration's manifest requirements installed:
    python -m unittest discover -s tests
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from homeassistant.helpers.config_validation import custom_serializer, to_field_list
import voluptuous as vol

from custom_components.open_meteo_solar_forecast.config_flow import (
    OpenMeteoSolarForecastFlowHandler,
    OpenMeteoSolarForecastOptionFlowHandler,
)

ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components/open_meteo_solar_forecast"
)


class WizardTests(unittest.IsolatedAsyncioTestCase):
    """The first page must lead to editable array settings in both flows."""

    async def test_setup_next_opens_array_settings(self):
        flow = OpenMeteoSolarForecastFlowHandler()
        flow.hass = SimpleNamespace(
            config=SimpleNamespace(
                location_name="Home",
                latitude=50.0,
                longitude=10.0,
            )
        )
        first = await flow.async_step_user()
        self.assertIs(first["last_step"], False)
        result = await flow.async_step_user(first["data_schema"]({}))
        self.assertEqual(result["step_id"], "array")
        fields = to_field_list(
            result["data_schema"], custom_serializer=custom_serializer
        )
        self.assertTrue(
            {
                "latitude",
                "longitude",
                "modules_power",
                "array_inverter_power",
                "add_another",
            }
            <= {field["name"] for field in fields}
        )
        result = await flow.async_step_array(
            result["data_schema"]({"modules_power": 800})
        )
        self.assertEqual(result["step_id"], "orientation")
        result = await flow.async_step_orientation(result["data_schema"]({}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["options"]["modules_power"], 800)

    async def test_tracker_setup_only_asks_for_fixed_angles(self):
        for tracking, expected in (
            ("none", {"azimuth", "declination"}),
            ("azimuth", {"declination"}),
            ("tilt", {"azimuth"}),
            ("dual", set()),
        ):
            with self.subTest(tracking=tracking):
                flow = OpenMeteoSolarForecastFlowHandler()
                flow.hass = SimpleNamespace(
                    config=SimpleNamespace(
                        location_name="Home", latitude=50.0, longitude=10.0
                    )
                )
                first = await flow.async_step_user()
                array = await flow.async_step_user(first["data_schema"]({}))
                fields = {
                    field["name"]: field
                    for field in to_field_list(
                        array["data_schema"], custom_serializer=custom_serializer
                    )
                }
                for angle in ("azimuth", "declination"):
                    self.assertNotIn(angle, fields)
                result = await flow.async_step_array(
                    array["data_schema"]({"modules_power": 800, "tracking": tracking})
                )
                if expected:
                    self.assertEqual(result["step_id"], "orientation")
                    fields = to_field_list(
                        result["data_schema"], custom_serializer=custom_serializer
                    )
                    self.assertEqual({field["name"] for field in fields}, expected)
                    self.assertTrue(all(field["required"] for field in fields))
                    values = {
                        key: {"azimuth": 220.5, "declination": 35.5}[key]
                        for key in expected
                    }
                    result = await flow.async_step_orientation(
                        result["data_schema"](values)
                    )
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(result["options"]["tracking"], tracking)
                self.assertEqual(
                    result["options"]["azimuth"],
                    220.5 if "azimuth" in expected else 180,
                )
                self.assertEqual(
                    result["options"]["declination"],
                    35.5 if "declination" in expected else 25,
                )

    async def test_dual_array_can_be_followed_by_a_single_axis_tracker(self):
        flow = OpenMeteoSolarForecastFlowHandler()
        flow.hass = SimpleNamespace(
            config=SimpleNamespace(location_name="Home", latitude=50.0, longitude=10.0)
        )
        form = await flow.async_step_user()
        form = await flow.async_step_user(form["data_schema"]({}))
        form = await flow.async_step_array(
            form["data_schema"](
                {
                    "modules_power": 1000,
                    "tracking": "dual",
                    "add_another": True,
                }
            )
        )
        self.assertEqual(form["step_id"], "array")
        self.assertEqual(form["description_placeholders"]["array_number"], "2")
        form = await flow.async_step_array(
            form["data_schema"](
                {
                    "modules_power": 2000,
                    "tracking": "azimuth",
                }
            )
        )
        self.assertEqual(form["step_id"], "orientation")
        for angle in (-1, 91):
            with self.subTest(angle=angle), self.assertRaises(vol.Invalid):
                form["data_schema"]({"declination": angle})
        result = await flow.async_step_orientation(
            form["data_schema"]({"declination": 31.5})
        )
        self.assertEqual(result["options"]["tracking"], ["dual", "azimuth"])
        self.assertEqual(result["options"]["declination"], [25, 31.5])
        self.assertEqual(result["options"]["modules_power"], [1000, 2000])

    async def test_changing_tracker_type_preserves_existing_array_angles(self):
        entry = SimpleNamespace(
            update_listeners=[object()],
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "modules_power": [800, 1200],
                "azimuth": [90.5, 270.5],
                "declination": [22.5, 35.5],
                "tracking": ["none", "dual"],
            },
        )
        flow = OpenMeteoSolarForecastOptionFlowHandler()
        with patch.object(
            type(flow), "config_entry", new_callable=PropertyMock, return_value=entry
        ):
            first = await flow.async_step_init()
            array = await flow.async_step_init(first["data_schema"]({}))
            array = await flow.async_step_array(
                array["data_schema"]({"tracking": "dual"})
            )
            result = await flow.async_step_array(
                array["data_schema"]({"tracking": "none"})
            )
            self.assertEqual(result["step_id"], "orientation")
            result = await flow.async_step_orientation(result["data_schema"]({}))
        self.assertEqual(result["data"]["tracking"], ["dual", "none"])
        self.assertEqual(result["data"]["azimuth"], [90.5, 270.5])
        self.assertEqual(result["data"]["declination"], [22.5, 35.5])

    async def test_options_next_preserves_and_edits_existing_arrays(self):
        entry = SimpleNamespace(
            update_listeners=[object()],
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "modules_power": [800, 1200],
                "azimuth": [90, 270],
            },
        )
        flow = OpenMeteoSolarForecastOptionFlowHandler()
        with patch.object(
            type(flow), "config_entry", new_callable=PropertyMock, return_value=entry
        ):
            first = await flow.async_step_init()
            self.assertIs(first["last_step"], False)
            array = await flow.async_step_init(first["data_schema"]({}))
            self.assertEqual(array["step_id"], "array")
            values = array["data_schema"]({})
            self.assertEqual(values["modules_power"], 800)
            self.assertTrue(values["add_another"])
            array = await flow.async_step_array(values)
            array = await flow.async_step_orientation(array["data_schema"]({}))
            values = array["data_schema"]({"modules_power": 1500})
            self.assertFalse(values["add_another"])
            result = await flow.async_step_array(values)
            result = await flow.async_step_orientation(result["data_schema"]({}))
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"]["modules_power"], [800, 1500])
            self.assertEqual(result["data"]["azimuth"], [90, 270])

    async def test_options_finish_fixed_angles_before_dropping_later_arrays(self):
        entry = SimpleNamespace(
            update_listeners=[object()],
            data={"latitude": 50.0, "longitude": 10.0},
            options={
                "base_url": "https://api.open-meteo.com",
                "modules_power": [1000, 2000],
                "azimuth": [90, 270],
                "declination": [21, 32],
                "tracking": ["none", "dual"],
            },
        )
        original = dict(entry.options)
        flow = OpenMeteoSolarForecastOptionFlowHandler()
        with patch.object(
            type(flow), "config_entry", new_callable=PropertyMock, return_value=entry
        ):
            form = await flow.async_step_init()
            form = await flow.async_step_init(form["data_schema"]({}))
            form = await flow.async_step_array(
                form["data_schema"](
                    {
                        "tracking": "tilt",
                        "add_another": False,
                    }
                )
            )
            self.assertEqual(form["step_id"], "orientation")
            self.assertEqual(entry.options, original)
            self.assertEqual(set(form["data_schema"]({})), {"azimuth"})
            result = await flow.async_step_orientation(
                form["data_schema"]({"azimuth": 91})
            )
        self.assertEqual(result["data"]["modules_power"], 1000)
        self.assertEqual(result["data"]["tracking"], "tilt")
        self.assertEqual(result["data"]["azimuth"], 91)
        self.assertEqual(result["data"]["declination"], 21)


class TranslationTests(unittest.TestCase):
    def test_translated_fields_belong_to_current_wizard_steps(self):
        reference = json.loads((ROOT / "strings.json").read_text())
        for path in (ROOT / "translations").glob("*.json"):
            translation = json.loads(path.read_text())
            for category in ("config", "options"):
                for step, content in (
                    translation.get(category, {}).get("step", {}).items()
                ):
                    with self.subTest(language=path.stem, category=category, step=step):
                        expected = reference[category]["step"][step]
                        for section in ("data", "data_description"):
                            self.assertLessEqual(
                                set(content.get(section, {})),
                                set(expected.get(section, {})),
                            )
                        if step in ("user", "init"):
                            self.assertNotIn("submit", content)


if __name__ == "__main__":
    unittest.main()
