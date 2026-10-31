"""Coalesce automated azimuth changes before reloading a forecast."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.service import async_register_admin_service

from . import _normalize_option, _resolve_array_count
from .const import CONF_AZIMUTH, CONF_TRACKING, DOMAIN

MIN_UPDATE_SECONDS = 30 * 60
BATCH_SECONDS = 5


def _azimuth(value: Any) -> float:
    value = vol.Coerce(float)(value)
    if not 0 <= value <= 360:
        raise vol.Invalid("Azimuth must be between 0 and 360 degrees")
    return value % 360


def _array_number(value: Any) -> int:
    number = cv.positive_int(value)
    if number < 1 or number != vol.Coerce(float)(value):
        raise vol.Invalid("Array number must be a positive integer")
    return number


@dataclass
class PendingAzimuth:
    """Snapshot settings so queued changes cannot overwrite later edits."""

    data: dict[str, Any]
    options: dict[str, Any]
    values: dict[int, float] = field(default_factory=dict)


class AzimuthUpdates:
    """Keep one pending batch and one reload limit per integration entry."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.pending: dict[str, PendingAzimuth] = {}
        self.timers: dict[str, Callable[[], None]] = {}
        self.last_applied: dict[str, float] = {}
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stop)

    @callback
    def _stop(self, _event: Any) -> None:
        for entry_id in list(self.pending):
            self._discard(entry_id)

    @callback
    def _discard(self, entry_id: str) -> None:
        if cancel := self.timers.pop(entry_id, None):
            cancel()
        self.pending.pop(entry_id, None)

    def _entry(self, entry_id: str) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state != ConfigEntryState.LOADED
        ):
            return None
        return entry

    @callback
    def handle(self, call: ServiceCall) -> None:
        """Queue the latest angle without fetching or reloading immediately."""
        entry_id = call.data["config_entry_id"]
        entry = self._entry(entry_id)
        if entry is None:
            raise ServiceValidationError(
                "Select a loaded Open-Meteo Solar Forecast entry"
            )
        count = _resolve_array_count(entry)
        number = call.data.get("array_number")
        if number is None:
            if count != 1:
                raise ServiceValidationError("Select an array_number for this entry")
            number = 1
        if number > count:
            raise ServiceValidationError(
                "array_number exceeds the configured array count"
            )
        index = number - 1
        tracking = _normalize_option(entry.options.get(CONF_TRACKING), count, "none")
        if tracking[index] in ("azimuth", "dual"):
            raise ServiceValidationError("This tracker ignores the configured azimuth")

        pending = self.pending.get(entry_id)
        if pending and (pending.data != entry.data or pending.options != entry.options):
            self._discard(entry_id)
            pending = None
        if pending is None:
            pending = PendingAzimuth(dict(entry.data), dict(entry.options))
            self.pending[entry_id] = pending
        angles = _normalize_option(entry.options.get(CONF_AZIMUTH), count, 180)
        angle = call.data[CONF_AZIMUTH]
        if angle == angles[index] % 360:
            pending.values.pop(index, None)
        else:
            pending.values[index] = angle
        if not pending.values:
            self._discard(entry_id)
            return
        if entry_id in self.timers:
            return

        coordinator = self.hass.data.get(DOMAIN, {}).get(entry_id)
        interval = getattr(coordinator, "update_interval", None)
        minimum = max(MIN_UPDATE_SECONDS, interval.total_seconds() if interval else 0)
        elapsed = monotonic() - self.last_applied.get(entry_id, float("-inf"))

        @callback
        def apply(_now: Any) -> None:
            self._apply(entry_id)

        self.timers[entry_id] = async_call_later(
            self.hass, max(BATCH_SECONDS, minimum - elapsed), apply
        )

    @callback
    def _apply(self, entry_id: str) -> None:
        pending = self.pending.get(entry_id)
        self._discard(entry_id)
        entry = self._entry(entry_id)
        if pending is None or entry is None:
            return
        if pending.data != entry.data or pending.options != entry.options:
            return
        count = _resolve_array_count(entry)
        angles = _normalize_option(entry.options.get(CONF_AZIMUTH), count, 180)
        for index, angle in pending.values.items():
            angles[index] = angle
        options = {**entry.options, CONF_AZIMUTH: angles[0] if count == 1 else angles}
        if self.hass.config_entries.async_update_entry(entry, options=options):
            self.last_applied[entry_id] = monotonic()


@callback
def async_setup_azimuth_service(hass: HomeAssistant) -> None:
    """Register one administrator-only action for all integration entries."""
    updates = AzimuthUpdates(hass)
    async_register_admin_service(
        hass,
        DOMAIN,
        "update_array_azimuth",
        updates.handle,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): cv.string,
                vol.Optional("array_number"): _array_number,
                vol.Required(CONF_AZIMUTH): _azimuth,
            }
        ),
    )
