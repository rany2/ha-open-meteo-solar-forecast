# HA Open-Meteo Solar Forecast Integration

This custom component integrates the [open-meteo-solar-forecast](https://github.com/rany2/open-meteo-solar-forecast) with Home Assistant. It allows you to see what your solar panels may produce in the future.

## Installation

### HACS

1. Go to the HACS page in your Home Assistant instance.
2. Click on `Integrations`.
3. Click on the three dots in the top right corner.
4. Click on `Custom repositories`.
5. Add `rany2/ha-open-meteo-solar-forecast` as the repository URL.
6. Click on `Category` and select `Integration`.
7. Click on `Add`.
8. A new custom integration shows up for installation "Open-Meteo Solar Forecast", install it.
9. Restart Home Assistant.

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

The azimuth range for this integration is 0 to 360 degrees, with 0 being North, 90 being East, 180 being South, and 270 being West. If you have a negative azimuth, add 360 to it to get the correct value.

### DC Efficiency

The DC efficiency is the efficiency of the DC wiring and should not be confused with the cell efficiency. The DC efficiency is typically around 0.93. The cell efficiency is accounted for in the cell temperature calculation and is assumed to be 0.12.

### Confusing Power Sensors with Energy Sensors

The power sensors start with "Solar production forecast Estimated power" and the energy sensors start with "Solar production forecast Estimated energy". The power sensors show the power expected to be available at that time, and the energy sensors show the energy expected to be produced as an average over an hour.

### Disabled Sensors

Some sensors are disabled by default to reduce load on the recorder database. If you want one of these sensors, you can enable it and wait about a minute for sensor data to appear.

## Changes

Changes are documented in the [CHANGELOG.md](/CHANGELOG.md).

## Credits

The [forecast_solar component code](https://github.com/home-assistant/core/tree/dev/homeassistant/components/forecast_solar) was used as a base for this integration. Thanks for such a clean starting point!
