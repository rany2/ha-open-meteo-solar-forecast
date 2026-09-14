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
                "azimuth",
                "declination",
                "modules_power",
                "array_inverter_power",
                "add_another",
            }
            <= {field["name"] for field in fields}
        )
        result = await flow.async_step_array(
            result["data_schema"]({"modules_power": 800})
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["options"]["modules_power"], 800)

    async def test_options_next_preserves_and_edits_existing_arrays(self):
        entry = SimpleNamespace(
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
            values = array["data_schema"]({"modules_power": 1500})
            self.assertFalse(values["add_another"])
            result = await flow.async_step_array(values)
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"]["modules_power"], [800, 1500])
            self.assertEqual(result["data"]["azimuth"], [90, 270])


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
