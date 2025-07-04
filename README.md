# HA Open-Meteo Solar Forecast Integration

This custom component integrates the [open-meteo-solar-forecast](https://github.com/rany2/open-meteo-solar-forecast) with Home Assistant. It allows you to see what your solar panels may produce in the future.

## Installation

### HACS

1. Go to the HACS page in your Home Assistant instance.
1. Search for `Open-Meteo Solar Forecast`.
   - If it doesn't immediately show up, check that the `Type` filter has `Integrations` ticked.
1. Install it.
1. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/rany2/ha-open-meteo-solar-forecast/releases/latest).
2. Unpack the release and copy the `custom_components/open_meteo_solar_forecast` directory to the `custom_components` directory in your Home Assistant configuration directory.
3. Restart Home Assistant.

## Configuration

To use this integration in your installation, head to "Settings" in the Home Assistant UI, then "Integrations". Click on the plus button and search for "Open-Meteo Solar Forecast" and follow the instructions.

## Common Mistakes

### API Key

This should be left blank as the Open-Meteo API does not require an API key. An API key is required for commercial use only per-Open-Meteo's [terms of service](https://open-meteo.com/en/terms).

### Azimuth

The azimuth range for this integration is 0 to 360 degrees, with 0 being North, 90 being East, 180 being South, and 270 being West. If you have a negative azimuth, add 360 to it to get the correct value. For example, -90 degrees should be entered as 270 degrees.

### DC Efficiency

The DC efficiency is the efficiency of the DC wiring and should not be confused with the cell efficiency. The DC efficiency is typically around 0.93. The cell efficiency is accounted for in the cell temperature calculation and is assumed to be 0.12.

### Dampening of Values

The damping factor is a number between 0.0 and 1.0.

A lower damping factor means higher solar panel power. At 0.0, there’s no damping and the panels produce maximum power.
A higher damping factor means lower power. At 1.0, damping is full and the power is at its minimum.

If a damping factor of 1.0 is applied for damping_morning, the power starts at 0 and increases steadily until midday `(sunrise + (sunset - sunrise) / 2)`.
If a damping factor is applied for damping_evening, the same happens in reverse and power decreases steadily as the sun sets.

### Confusing Power Sensors with Energy Sensors

The power sensors start with "Solar production forecast Estimated power" and the energy sensors start with "Solar production forecast Estimated energy". The power sensors show the power expected to be available at that time, and the energy sensors show the energy expected to be produced as an average over an hour.

### Confusion between "Open-Meteo" and "Open-Meteo Solar Forecast" Integrations

The "Open-Meteo" integration is for weather data, and the "Open-Meteo Solar Forecast" integration is for solar production data. They are separate integrations and should not be confused with each other.

### Disabled Sensors

Some sensors are disabled by default to reduce load on the recorder database. If you want one of these sensors, you can enable it and wait about a minute for sensor data to appear.

### Power Sensor Update Frequency

The power sensors update every 15 minutes, so you may not see immediate changes in the power sensors. They are not interpolated every minute. For example, consider that the integration knows that the power values will be as follows for the given instants:

- `12:00`: `100` W
- `12:15`: `200` W
- `12:30`: `300` W

If you check the "Power Now" sensor at:

- `12:00`, it will show `100` W (data taken from `12:00`)
- `12:15`, it will show `200` W (data taken from `12:15`)
- `12:22`, it will show `200` W (data taken from `12:15`)
- `12:37`, it will show `300` W (data taken from `12:30`)

Notice that the power sensor picks the last known value until the next update, not necessarily the closest value. Also, the power sensors are not interpolated, so the "Power Now" sensor will not show ~`150` W at `12:07`.

## Credits

The [forecast_solar component code](https://github.com/home-assistant/core/tree/dev/homeassistant/components/forecast_solar) was used as a base for this integration. Thanks for such a clean starting point!
