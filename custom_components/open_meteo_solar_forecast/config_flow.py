"""Config flow for Open-Meteo Solar Forecast integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AZIMUTH,
    CONF_BASE_URL,
    CONF_DAMPING_EVENING,
    CONF_DAMPING_MORNING,
    CONF_DECLINATION,
    CONF_EFFICIENCY_FACTOR,
    CONF_INCLUDE_IN_CUMULATIVE,
    CONF_INSTANCE_TYPE,
    CONF_INVERTER_POWER,
    CONF_MODEL,
    CONF_MODULES_POWER,
    DOMAIN,
    INSTANCE_TYPE_CUMULATIVE,
    INSTANCE_TYPE_NORMAL,
)

try:
    from homeassistant.config_entries import ConfigFlowResult  # >=2024.4.0b0
except ImportError:
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult


class OpenMeteoSolarForecastFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open-Meteo Solar Forecast."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OpenMeteoSolarForecastOptionFlowHandler:
        """Get the options flow for this handler."""
        return OpenMeteoSolarForecastOptionFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        if user_input is not None:
            instance_type = user_input.get(CONF_INSTANCE_TYPE, INSTANCE_TYPE_NORMAL)
            
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_INSTANCE_TYPE: instance_type,
                },
                options={
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_AZIMUTH: user_input.get(CONF_AZIMUTH, 180),
                    CONF_BASE_URL: user_input[CONF_BASE_URL],
                    CONF_DAMPING_MORNING: user_input.get(CONF_DAMPING_MORNING, 0.0),
                    CONF_DAMPING_EVENING: user_input.get(CONF_DAMPING_EVENING, 0.0),
                    CONF_DECLINATION: user_input.get(CONF_DECLINATION, 25),
                    CONF_MODULES_POWER: user_input.get(CONF_MODULES_POWER, 0),
                    CONF_INVERTER_POWER: user_input.get(CONF_INVERTER_POWER, 0),
                    CONF_EFFICIENCY_FACTOR: user_input.get(CONF_EFFICIENCY_FACTOR, 1.0),
                    CONF_MODEL: user_input.get(CONF_MODEL, "best_match"),
                    CONF_INCLUDE_IN_CUMULATIVE: user_input.get(CONF_INCLUDE_IN_CUMULATIVE, False),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INSTANCE_TYPE, default=INSTANCE_TYPE_NORMAL
                    ): vol.In([INSTANCE_TYPE_NORMAL, INSTANCE_TYPE_CUMULATIVE]),
                    vol.Optional(CONF_API_KEY, default=""): str,
                    vol.Required(
                        CONF_BASE_URL, default="https://api.open-meteo.com"
                    ): str,
                    vol.Required(
                        CONF_NAME, default=self.hass.config.location_name
                    ): str,
                    vol.Required(
                        CONF_LATITUDE, default=self.hass.config.latitude
                    ): cv.latitude,
                    vol.Required(
                        CONF_LONGITUDE, default=self.hass.config.longitude
                    ): cv.longitude,
                    vol.Optional(CONF_DECLINATION, default=25): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=90)
                    ),
                    vol.Optional(CONF_AZIMUTH, default=180): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=360)
                    ),
                    vol.Optional(CONF_MODULES_POWER, default=0): vol.All(
                        vol.Coerce(int), vol.Range(min=0)
                    ),
                    vol.Optional(CONF_INVERTER_POWER, default=0): vol.All(
                        vol.Coerce(int), vol.Range(min=0)
                    ),
                    vol.Optional(CONF_DAMPING_MORNING, default=0.0): vol.Coerce(float),
                    vol.Optional(CONF_DAMPING_EVENING, default=0.0): vol.Coerce(float),
                    vol.Optional(CONF_EFFICIENCY_FACTOR, default=1.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                    vol.Optional(CONF_MODEL, default="best_match"): str,
                    vol.Optional(CONF_INCLUDE_IN_CUMULATIVE, default=False): bool,
                }
            ),
        )


class OpenMeteoSolarForecastOptionFlowHandler(OptionsFlow):
    """Handle options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title="", data=user_input | {CONF_API_KEY: user_input.get(CONF_API_KEY)}
            )

        # Get the instance type from config data
        instance_type = self.config_entry.data.get(CONF_INSTANCE_TYPE, INSTANCE_TYPE_NORMAL)
        
        # Build schema based on instance type
        if instance_type == INSTANCE_TYPE_CUMULATIVE:
            # Cumulative instances don't need panel-specific settings
            schema = vol.Schema({
                vol.Optional(
                    CONF_API_KEY,
                    description={
                        "suggested_value": self.config_entry.options.get(
                            CONF_API_KEY, ""
                        )
                    },
                ): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=self.config_entry.options.get(CONF_BASE_URL, "https://api.open-meteo.com"),
                ): str,
            })
        else:
            # Normal instances need all panel configuration
            schema = vol.Schema({
                vol.Optional(
                    CONF_API_KEY,
                    description={
                        "suggested_value": self.config_entry.options.get(
                            CONF_API_KEY, ""
                        )
                    },
                ): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=self.config_entry.options.get(CONF_BASE_URL, "https://api.open-meteo.com"),
                ): str,
                vol.Required(
                    CONF_DECLINATION,
                    default=self.config_entry.options.get(CONF_DECLINATION, 25),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=90)),
                vol.Required(
                    CONF_AZIMUTH,
                    default=self.config_entry.options.get(CONF_AZIMUTH, 180),
                ): vol.All(vol.Coerce(int), vol.Range(min=-0, max=360)),
                vol.Required(
                    CONF_MODULES_POWER,
                    default=self.config_entry.options.get(CONF_MODULES_POWER, 0),
                ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional(
                    CONF_DAMPING_MORNING,
                    default=self.config_entry.options.get(
                        CONF_DAMPING_MORNING, 0.0
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_DAMPING_EVENING,
                    default=self.config_entry.options.get(
                        CONF_DAMPING_EVENING, 0.0
                    ),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_INVERTER_POWER,
                    default=self.config_entry.options.get(CONF_INVERTER_POWER, 0),
                ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional(
                    CONF_EFFICIENCY_FACTOR,
                    default=self.config_entry.options.get(
                        CONF_EFFICIENCY_FACTOR, 1.0
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional(
                    CONF_MODEL,
                    default=self.config_entry.options.get(CONF_MODEL, "best_match"),
                ): str,
                vol.Optional(
                    CONF_INCLUDE_IN_CUMULATIVE,
                    default=self.config_entry.options.get(CONF_INCLUDE_IN_CUMULATIVE, False),
                ): bool,
            })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
