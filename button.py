"""Test button to manually trigger the doorbell ring."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DOORBELL_NAME


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([DoorbellTestButton(hass, entry)])


class DoorbellTestButton(ButtonEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:bell-ring"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        doorbell_name = entry.data[CONF_DOORBELL_NAME]
        self._attr_name = f"{doorbell_name} Test"
        self._attr_unique_id = f"{entry.entry_id}_test_button"

    async def async_press(self) -> None:
        manager = self.hass.data[DOMAIN][self._entry.entry_id].get("manager")
        if manager:
            await manager._handle_ring()