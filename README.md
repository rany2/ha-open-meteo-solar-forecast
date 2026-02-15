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

### Horizon shading

A horizon profile can be provided as a text file to take into account when direct sunlight is blocked out by surrounding obstacles (buildings, trees, ...). The file location can be specified, a default one is located in the custom_components directory. (It is recommended to use a location outside of the custom_component in order to avoid accidentally overwriting on subsequent updates.) It contains two columns of floats (decimal point, separated by tab) giving the azimuth (0° = north, 180° = south) and the elevation angle of the obstacle contour (0° = flat horizon, 90° = in the sky directly above). You can use as many lines as you want (minimum of two, the first azimuth 0°, and the last one 360°), and the azimuth angles have to be strictly increasing. Intermediate values are interpolated linearly. Some checks are run on the horizon file during initialisation; if errors are detected the integration will show an issue (see the logs for further details then).

In the integration settings, the first checkbox use_horizon enables the feature. Enabling/disabling will have a effect on the forecast immediately. The horizon profile can be used together with the damping factors, if necessary.

The second checkbox will enable/disable partial shading estimation. If partial_shading is disabled and a shadow is detected on the module, only the diffuse irradiation will be used to calculate the power output. This is useful if the shading is predominantly from far-away objects, which can be treated as shading the whole module at once or not. If partial_shading is enabled and a shadow is detected on the module, the shadow is treated as partial. This is useful if the shading arises from close-by objects, which cast 'hard' contoured shadows on the module. In this case, an experimental calculation is used taking into account the 'sunniness' of the conditions (inspired by [this](https://pvlib-python.readthedocs.io/en/stable/gallery/shading/plot_partial_module_shading_simple.html#calculating-shading-loss-across-shading-scenarios)). This is done via the ratio of diffuse and direct irradiation. A large share of diffuse irradiation (cloudy day) will let the module run as homogeneously shaded at diffuse power. A small share of diffuse irradiation (sunny) day will reduce the diffuse power even more, since hard partial shadows can shut down the module completely.

Also see the Readme for https://github.com/rany2/open-meteo-solar-forecast on more information.

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
