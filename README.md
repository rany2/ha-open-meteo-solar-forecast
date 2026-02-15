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

### Multiple PV arrays

The integration supports multiple PV arrays. For array-capable fields, you can enter either:

- a single scalar value (applied to all arrays), or
- a comma-separated list of values (one value per array).

All numeric parameter values must use a decimal point (`.`), even in locales that commonly use a decimal comma (for example German).

Using decimal commas can break parsing in multi-array configurations. For example:

- `damping_factor`: `0,4,0,5` is interpreted as four list items, not two decimals (`0.4,0.5`).
- `dc_efficiency`: `0,9` is interpreted as two arrays (`0` and `9`) instead of a single value (`0.9`).

Use `.` for decimals and `,` only as the list separator between arrays.

Examples:

- Two arrays with different orientations:
   - `latitude`: `52.16, 52.16`
   - `longitude`: `4.47, 4.47`
   - `declination`: `20, 35`
   - `azimuth`: `90, 270`
   - `modules_power`: `2400, 1800`

- Per-array horizon usage:
   - `use_horizon`: `false, true`
   - `horizon_filepath`: `/config/www/horizon_a.txt, /config/www/horizon_b.txt`

When mixed with list inputs, single scalar values are automatically expanded to all arrays.

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

### Horizon shading

A horizon profile text file accounts for direct sunlight blockage from obstacles (buildings, trees, etc.). The file contains two tab-separated columns of floats: azimuth (0° = north, 180° = south) and elevation angle (0° = flat horizon, 90° = directly overhead). Use a minimum of two lines with azimuth values strictly increasing from 0° to 360°; intermediate values are interpolated linearly.

**Note:** Store the file outside the custom_component directory to avoid overwriting during updates.

Use horizon enables/disables shading and takes effect immediately. It can be combined with damping factors.

Partial shading controls shadow estimation:
- **Disabled:** Only diffuse irradiation is used when a shadow is detected (suitable for far-away objects)
- **Enabled:** Shadows are treated as partial (suitable for close-by objects). An experimental calculation accounts for conditions by comparing diffuse/direct irradiation ratios; cloudy days behave as homogeneously shaded, while sunny days apply additional reductions.

For more information, see the [open-meteo-solar-forecast repository](https://github.com/rany2/open-meteo-solar-forecast).

## Credits

The [forecast_solar component code](https://github.com/home-assistant/core/tree/dev/homeassistant/components/forecast_solar) was used as a base for this integration. Thanks for such a clean starting point!
