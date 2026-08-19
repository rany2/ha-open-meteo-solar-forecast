# HA Open-Meteo Solar Forecast Integration

This custom component integrates the [open-meteo-solar-forecast](https://github.com/rany2/open-meteo-solar-forecast) with Home Assistant. It allows you to see what your solar panels may produce in the future.

## Installation

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rany2&repository=ha-open-meteo-solar-forecast&category=integration)

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

### Multiple PV Arrays

The setup wizard first asks for general settings (name, API details, inverter capacity), then shows one page per PV array with its location, orientation, power, tracking and shading settings. Tick "Add another array" to configure an additional array; repeat for as many arrays as you have.

To change the configuration later, open the integration's options: after the general settings you are walked through each configured array. Untick "Add another array" on an array page to drop the arrays after it.

Declination and azimuth accept fractional degrees (e.g. a declination of `22.5`).

### Azimuth

Azimuth ranges from 0° to 360°: North (0°), East (90°), South (180°), West (270°). For negative values, add 360° (e.g., -90° becomes 270°).

### Solar Tracking

The `tracking` option models panels that follow the sun instead of being fixed:

- `none` (default): fixed panels
- `azimuth`: vertical-axis (east-west) tracker; the configured azimuth is ignored
- `tilt`: tilt-axis tracker; the configured declination is ignored
- `dual`: dual-axis tracker; both azimuth and declination are ignored

The tracker type is set per array.

### Multiple Inverters

The "Inverter capacity" field in the general settings models a single inverter shared by all arrays: the combined output of all arrays is clamped to it (0 = no limit).

If each array is connected to its own inverter, set the "Array inverter capacity" field on the corresponding array pages instead. Each array's output is then clamped to its own inverter before the outputs are combined. Use 0 for arrays without a dedicated inverter (no limit for that array). As soon as any array has its own inverter capacity set, the shared inverter capacity from the general settings is ignored.

### DC Efficiency

The DC efficiency is the efficiency of the DC wiring and should not be confused with the cell efficiency. The DC efficiency is typically around 0.93. The cell efficiency is accounted for in the cell temperature calculation and is assumed to be 0.12.

### Damping Factor

The damping factor is a number between 0.0 and 1.0, where:
- **0.0:** No damping; panels produce maximum power
- **1.0:** Full damping; power is at minimum

For `damping_morning`, a factor of 1.0 causes power to start at 0 and increase steadily until midday `(sunrise + (sunset - sunrise) / 2)`.
For `damping_evening`, the same effect occurs in reverse, with power decreasing as the sun sets.

### Horizon Shading

A horizon profile text file accounts for direct sunlight blockage from obstacles (buildings, trees, etc.). The file contains two tab-separated columns of floats: azimuth (0° = north, 180° = south) and elevation angle (0° = flat horizon, 90° = directly overhead). Use a minimum of two lines with azimuth values strictly increasing from 0° to 360°; intermediate values are interpolated linearly.

**Note:** Store the file outside the custom_component directory to avoid overwriting during updates.

Use horizon enables/disables shading and takes effect immediately. It can be combined with damping factors.

Partial shading controls shadow estimation:
- **Disabled:** Only diffuse irradiation is used when a shadow is detected (suitable for far-away objects)
- **Enabled:** Shadows are treated as partial (suitable for close-by objects). An experimental calculation accounts for conditions by comparing diffuse/direct irradiation ratios; cloudy days behave as homogeneously shaded, while sunny days apply additional reductions.

For more information, see the [open-meteo-solar-forecast repository](https://github.com/rany2/open-meteo-solar-forecast).

## Credits

The [forecast_solar component code](https://github.com/home-assistant/core/tree/dev/homeassistant/components/forecast_solar) was used as a base for this integration. Thanks for such a clean starting point!
