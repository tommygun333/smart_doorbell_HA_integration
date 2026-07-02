"""Enable/disable switches for each notification type + manual DND."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *

_SWITCH_DEFS = [
    (SWITCH_LIGHT_FLASH, "💡 Light Flash",  True),
    (SWITCH_TELEGRAM,    "📱 Telegram",      True),
    (SWITCH_SPEAKER,     "🔊 Speaker",       True),
    (SWITCH_DND_MANUAL,  "🌙 Do Not Disturb",False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        DoorbellSwitch(hass, entry, key, label, default)
        for key, label, default in _SWITCH_DEFS
    ])


class DoorbellSwitch(SwitchEntity):
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        key: str,
        label: str,
        default: bool,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._key = key
        doorbell_name = entry.data[CONF_DOORBELL_NAME]
        self._attr_name = f"{doorbell_name} {label}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        # Seed runtime state from defaults (already set in __init__.py)
        runtime = hass.data[DOMAIN][entry.entry_id]["switches"]
        runtime.setdefault(key, default)

    @property
    def is_on(self) -> bool:
        return self.hass.data[DOMAIN][self._entry.entry_id]["switches"][self._key]

    async def async_turn_on(self, **kwargs) -> None:
        self.hass.data[DOMAIN][self._entry.entry_id]["switches"][self._key] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.hass.data[DOMAIN][self._entry.entry_id]["switches"][self._key] = False
        self.async_write_ha_state()