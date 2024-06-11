# Changelog

v0.1.12

- Sort integration's `manifest.json` to pass hassfest validation. This is required for submission to the Home Assistant Community Store's default repo.

v0.1.11

- Fixes a bug where sometimes data is fetched when attempting to update the power sensors.

v0.1.10

- Fix setting of custom Open-Meteo URL
- Add support for capping power to inverter capacity
- Provide detailed forecast in sensor attribute
- Fix config_flow.py for HA <2024.4.0b0
- Write some documentation

v0.1.9

- Switched to using GitHub releases.

v0.1.8

- Fix `TypeError: unsupported operand type(s) for *: ‘NoneType’ and ‘int’` bug.

v0.1.6

- Add D2, D3, D4, D5, D6, D7 energy production sensors.
- Clarify that effiency factor is only for DC wire efficiency not cell efficiency.

v0.1.5

- Fix start time for power sensors.

v0.1.4

- Fix typo in cell temperature calculation.

v0.1.3

- Account for cell efficiency and wind speed for cell temperature calculations.

v0.1.2

- Update to open-meteo-solar-forecast 0.1.8.

v0.1.1

- Update to open-meteo-solar-forecast 0.1.7.

v0.1.0

- Initial release.
