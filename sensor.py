"""Diagnostic sensors for Smart Doorbell."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DOORBELL_NAME, DOMAIN

if TYPE_CHECKING:
    from . import DoorbellManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        DoorbellStatusSensor(entry),
        DoorbellTriggerSensor(entry),
    ])


class _DoorbellDiagnosticSensor(SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, suffix: str, label: str) -> None:
        self._entry = entry
        doorbell_name = entry.data[CONF_DOORBELL_NAME]
        self._attr_name = f"{doorbell_name} {label}"
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"

    @property
    def _manager(self) -> DoorbellManager | None:
        if self.hass is None:
            return None
        return self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("manager")

    async def async_added_to_hass(self) -> None:
        manager = self._manager
        if manager:
            self.async_on_remove(manager.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._manager is not None


class DoorbellStatusSensor(_DoorbellDiagnosticSensor):
    _attr_icon = "mdi:bell-badge"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "status", "Status")

    @property
    def native_value(self) -> str:
        manager = self._manager
        if not manager:
            return "unavailable"
        return manager.diagnostics["status"]

    @property
    def extra_state_attributes(self) -> dict:
        manager = self._manager
        if not manager:
            return {}
        diagnostics = manager.diagnostics
        return {
            "last_reason": diagnostics["last_reason"],
            "last_error": diagnostics["last_error"],
            "last_triggered_at": diagnostics["last_triggered_at"],
            "last_trigger_source": diagnostics["last_trigger_source"],
            "dnd_active": diagnostics["dnd_active"],
            "enabled_switches": diagnostics["switches"],
            "last_actions": diagnostics["last_actions"],
            "recent_logs": diagnostics["recent_logs"],
        }


class DoorbellTriggerSensor(_DoorbellDiagnosticSensor):
    _attr_icon = "mdi:motion-sensor"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "trigger", "Trigger")

    @property
    def native_value(self) -> str:
        manager = self._manager
        if not manager:
            return self._entry.data.get("trigger_entity", "unknown")
        return manager.diagnostics["trigger_entity"]

    @property
    def extra_state_attributes(self) -> dict:
        manager = self._manager
        if not manager:
            return {}
        diagnostics = manager.diagnostics
        return {
            "last_event_at": diagnostics["last_trigger_event_at"],
            "last_old_state": diagnostics["last_trigger_old_state"],
            "last_new_state": diagnostics["last_trigger_new_state"],
            "last_reason": diagnostics["last_reason"],
        }
