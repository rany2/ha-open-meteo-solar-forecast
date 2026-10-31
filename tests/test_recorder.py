"""The recorder leaves out every forecast series the day sensors carry.

Run with Home Assistant and the integration's manifest requirements installed:
    python -m unittest discover -s tests
"""

import unittest

from custom_components.open_meteo_solar_forecast.const import (
    ATTR_WATTS,
    ATTR_WH_PERIOD,
    ATTR_WH_PERIOD_15M,
)
from custom_components.open_meteo_solar_forecast.recorder import exclude_attributes


class RecorderTests(unittest.TestCase):
    """Each series holds a whole day of values and would fill the database."""

    def test_all_forecast_series_are_excluded(self) -> None:
        assert exclude_attributes(None) >= {
            ATTR_WATTS,
            ATTR_WH_PERIOD,
            ATTR_WH_PERIOD_15M,
        }


if __name__ == "__main__":
    unittest.main()
