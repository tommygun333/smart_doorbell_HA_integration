"""Smart Doorbell — core setup and notification logic."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import time as dt_time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN, PLATFORMS,
    CONF_TRIGGER_ENTITY, CONF_DOORBELL_NAME,
    CONF_LIGHT_ENTITIES, CONF_LIGHT_FLASH_DURATION, CONF_DND_AFFECTS_LIGHTS,
    CONF_TELEGRAM_MESSAGE, CONF_DND_AFFECTS_TELEGRAM,
    CONF_OVERALL_VOLUME, CONF_DND_AFFECTS_SPEAKER,
    CONF_SPEAKER_CONFIGS, CONF_SPEAKER_ENTITY, CONF_SPEAKER_VOLUME, CONF_SPEAKER_STARTUP_DELAY,
    CONF_SPEAKER_SET_VOLUME, CONF_MEDIA_CONTENT_TYPE,
    CONF_RINGTONE_PATH, CONF_RINGTONE_DURATION,
    CONF_TTS_ENABLED, CONF_TTS_REALTIME, CONF_TTS_REALTIME_TEXT,
    CONF_TTS_ENGINE, CONF_TTS_FILE_PATH,
    CONF_DND_ENABLED, CONF_DND_START, CONF_DND_END,
    SWITCH_LIGHT_FLASH, SWITCH_TELEGRAM, SWITCH_SPEAKER, SWITCH_DND_MANUAL,
    DEFAULT_SWITCHES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "switches": dict(DEFAULT_SWITCHES),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    manager = DoorbellManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id]["manager"] = manager
    await manager.async_setup()

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager: DoorbellManager = hass.data[DOMAIN][entry.entry_id].get("manager")
    if manager:
        await manager.async_unload()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


class DoorbellManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._unsub_listener = None

    async def async_setup(self) -> None:
        trigger = self.entry.data[CONF_TRIGGER_ENTITY]

        @callback
        def _event_filter(event_data) -> bool:
            return event_data.get("entity_id") == trigger

        @callback
        def _state_changed(event):
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if old is None or new is None:
                return
            if old.state != "on" and new.state == "on":
                self.hass.async_create_task(self._handle_ring())

        self._unsub_listener = self.hass.bus.async_listen(
            "state_changed",
            _state_changed,
            event_filter=_event_filter,
        )
        _LOGGER.debug("Smart Doorbell '%s' listening on %s", self._name, trigger)

    async def async_unload(self) -> None:
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

    @property
    def _name(self) -> str:
        return self.entry.data[CONF_DOORBELL_NAME]

    def _switch_on(self, key: str) -> bool:
        return self.hass.data[DOMAIN][self.entry.entry_id]["switches"].get(key, False)

    def _dnd_active(self) -> bool:
        if self._switch_on(SWITCH_DND_MANUAL):
            return True
        opts = self.entry.options
        if not opts.get(CONF_DND_ENABLED, False):
            return False
        try:
            now = datetime.now().time().replace(second=0, microsecond=0)
            start = dt_time.fromisoformat(opts[CONF_DND_START][:5])
            end   = dt_time.fromisoformat(opts[CONF_DND_END][:5])
            if start <= end:
                return start <= now <= end
            return now >= start or now <= end
        except Exception:
            return False

    async def _handle_ring(self) -> None:
        _LOGGER.info("Doorbell '%s' rang!", self._name)
        opts = self.entry.options
        dnd = self._dnd_active()
        tasks = []

        if self._switch_on(SWITCH_LIGHT_FLASH):
            if not (dnd and opts.get(CONF_DND_AFFECTS_LIGHTS, True)):
                tasks.append(self._flash_lights())

        if self._switch_on(SWITCH_TELEGRAM):
            if not (dnd and opts.get(CONF_DND_AFFECTS_TELEGRAM, True)):
                tasks.append(self._send_telegram())

        if self._switch_on(SWITCH_SPEAKER):
            if not (dnd and opts.get(CONF_DND_AFFECTS_SPEAKER, True)):
                tasks.append(self._announce_all_speakers())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                _LOGGER.error("Doorbell notification error: %s", r)

    async def _flash_lights(self) -> None:
        opts = self.entry.options
        entities: list[str] = opts.get(CONF_LIGHT_ENTITIES, [])
        duration: float = opts.get(CONF_LIGHT_FLASH_DURATION, 1.0)
        if not entities:
            return

        # Snapshot current state
        snapshots: dict[str, dict] = {}
        for eid in entities:
            state = self.hass.states.get(eid)
            if state:
                snapshots[eid] = {
                    "domain": eid.split(".")[0],
                    "state": state.state,
                    "brightness": state.attributes.get("brightness"),
                    "color_temp": state.attributes.get("color_temp"),
                    "rgb_color": state.attributes.get("rgb_color"),
                }

        lights  = [e for e in entities if e.split(".")[0] == "light"]
        switches = [e for e in entities if e.split(".")[0] == "switch"]

        # Always toggle opposite of current state to guarantee a visible blink
        lights_on  = [e for e in lights  if snapshots.get(e, {}).get("state") == "on"]
        lights_off = [e for e in lights  if snapshots.get(e, {}).get("state") != "on"]
        sw_on      = [e for e in switches if snapshots.get(e, {}).get("state") == "on"]
        sw_off     = [e for e in switches if snapshots.get(e, {}).get("state") != "on"]

        # Lights that are ON → turn OFF to blink. Lights that are OFF → turn ON to blink.
        if lights_on:
            await self.hass.services.async_call(
                "light", "turn_off", {"entity_id": lights_on}, blocking=True
            )
        if lights_off:
            await self.hass.services.async_call(
                "light", "turn_on", {"entity_id": lights_off}, blocking=True
            )
        if sw_on:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": sw_on}, blocking=True
            )
        if sw_off:
            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": sw_off}, blocking=True
            )

        await asyncio.sleep(duration)

        # Restore every entity back to its original state
        for eid, snap in snapshots.items():
            domain = snap["domain"]
            if snap["state"] == "off":
                await self.hass.services.async_call(
                    domain, "turn_off", {"entity_id": eid}, blocking=True
                )
            else:
                if domain == "light":
                    svc_data: dict = {"entity_id": eid}
                    if snap["brightness"] is not None:
                        svc_data["brightness"] = snap["brightness"]
                    if snap["color_temp"] is not None:
                        svc_data["color_temp"] = snap["color_temp"]
                    if snap["rgb_color"] is not None:
                        svc_data["rgb_color"] = snap["rgb_color"]
                    await self.hass.services.async_call(
                        "light", "turn_on", svc_data, blocking=True
                    )
                else:
                    await self.hass.services.async_call(
                        "switch", "turn_on", {"entity_id": eid}, blocking=True
                    )

    async def _send_telegram(self) -> None:
        opts = self.entry.options
        message: str = opts.get(CONF_TELEGRAM_MESSAGE, "Doorbell rang!")
        await self.hass.services.async_call(
            "telegram_bot", "send_message", {"message": message}, blocking=True,
        )

    async def _announce_all_speakers(self) -> None:
        opts = self.entry.options
        speaker_configs: list[dict] = opts.get(CONF_SPEAKER_CONFIGS, [])
        overall_volume: float = opts.get(CONF_OVERALL_VOLUME, 80) / 100.0
        await asyncio.gather(
            *(self._announce_speaker(cfg, overall_volume) for cfg in speaker_configs),
            return_exceptions=True,
        )

    async def _announce_speaker(self, cfg: dict, overall_volume: float) -> None:
        entity_id: str = cfg.get(CONF_SPEAKER_ENTITY, "")
        if not entity_id:
            return

        set_volume: bool = cfg.get(CONF_SPEAKER_SET_VOLUME, True)
        vol_pct: float = cfg.get(CONF_SPEAKER_VOLUME, 80) / 100.0
        effective_volume = round(min(vol_pct * overall_volume, 1.0), 2)
        content_type: str = cfg.get(CONF_MEDIA_CONTENT_TYPE, "audio/mpeg")

        ringtone: str = cfg.get(CONF_RINGTONE_PATH, "")
        ringtone_dur: int = cfg.get(CONF_RINGTONE_DURATION, 3)
        tts_enabled: bool = cfg.get(CONF_TTS_ENABLED, False)
        tts_realtime: bool = cfg.get(CONF_TTS_REALTIME, False)
        tts_text: str = cfg.get(CONF_TTS_REALTIME_TEXT, "")
        tts_engine: str = cfg.get(CONF_TTS_ENGINE, "")
        tts_file: str = cfg.get(CONF_TTS_FILE_PATH, "")

        if set_volume:
            await self.hass.services.async_call(
                "media_player", "volume_set",
                {"entity_id": entity_id, "volume_level": effective_volume},
                blocking=True,
            )

        # Step 1 — play ringtone (no blocking, exactly like the working automation)
        if ringtone:
            await self.hass.services.async_call(
                "media_player", "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_id": ringtone,
                    "media_content_type": content_type,
                },
                blocking=False,
            )

        # Step 2 — fixed delay (exactly like the working automation's delay: seconds: X)
        if ringtone:
            await asyncio.sleep(ringtone_dur)

        # Step 3 — TTS after delay (exactly like the working automation)
        if tts_enabled:
            if tts_realtime and tts_text and tts_engine:
                await self.hass.services.async_call(
                    "tts", "speak",
                    {
                        "entity_id": tts_engine,
                        "media_player_entity_id": entity_id,
                        "message": tts_text,
                    },
                    blocking=True,
                )
            elif tts_file:
                await self.hass.services.async_call(
                    "media_player", "play_media",
                    {
                        "entity_id": entity_id,
                        "media_content_id": tts_file,
                        "media_content_type": content_type,
                    },
                    blocking=False,
                )