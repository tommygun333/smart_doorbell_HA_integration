"""Smart Doorbell — core setup and notification logic."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from datetime import time as dt_time
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_DEBOUNCE_DURATION,
    CONF_DEBOUNCE_ENABLED,
    CONF_DND_AFFECTS_LIGHTS,
    CONF_DND_AFFECTS_SPEAKER,
    CONF_DND_AFFECTS_TELEGRAM,
    CONF_DND_ENABLED,
    CONF_DND_END,
    CONF_DND_START,
    CONF_DOORBELL_NAME,
    CONF_LIGHT_ENTITIES,
    CONF_LIGHT_FLASH_DURATION,
    CONF_MEDIA_CONTENT_TYPE,
    CONF_OVERALL_VOLUME,
    CONF_RINGTONE_DURATION,
    CONF_RINGTONE_PATH,
    CONF_SPEAKER_CONFIGS,
    CONF_SPEAKER_ENTITY,
    CONF_SPEAKER_SET_VOLUME,
    CONF_SPEAKER_STARTUP_DELAY,
    CONF_SPEAKER_VOLUME,
    CONF_TELEGRAM_MESSAGE,
    CONF_TRIGGER_ENTITY,
    CONF_TTS_ENABLED,
    CONF_TTS_ENGINE,
    CONF_TTS_FILE_PATH,
    CONF_TTS_REALTIME,
    CONF_TTS_REALTIME_TEXT,
    DEBOUNCE_DEFAULT_DURATION,
    DEFAULT_SWITCHES,
    DOMAIN,
    PLATFORMS,
    SWITCH_DND_MANUAL,
    SWITCH_LIGHT_FLASH,
    SWITCH_SPEAKER,
    SWITCH_TELEGRAM,
)

_LOGGER = logging.getLogger(__name__)
_MAX_RECENT_LOGS = 25


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    manager = DoorbellManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        "switches": dict(DEFAULT_SWITCHES),
        "manager": manager,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
        self._last_ring_time: float = 0.0
        self._listeners: list[Callable[[], None]] = []
        self._recent_logs: deque[str] = deque(maxlen=_MAX_RECENT_LOGS)
        self._diagnostics: dict[str, Any] = {
            "status": "idle",
            "trigger_entity": self.entry.data[CONF_TRIGGER_ENTITY],
            "last_reason": "Waiting for trigger.",
            "last_error": None,
            "last_triggered_at": None,
            "last_trigger_source": None,
            "last_trigger_event_at": None,
            "last_trigger_old_state": None,
            "last_trigger_new_state": None,
            "dnd_active": False,
            "last_actions": {},
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            **self._diagnostics,
            "switches": self._switches_snapshot(),
            "recent_logs": list(self._recent_logs),
        }

    @property
    def _name(self) -> str:
        return self.entry.data[CONF_DOORBELL_NAME]

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        listener()

        def _remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove_listener

    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _switch_on(self, key: str) -> bool:
        return self.hass.data[DOMAIN][self.entry.entry_id]["switches"].get(key, False)

    def _switches_snapshot(self) -> dict[str, bool]:
        return dict(self.hass.data[DOMAIN][self.entry.entry_id]["switches"])

    def _format_exception(self, err: Exception) -> str:
        message = str(err).strip()
        if message:
            return f"{err.__class__.__name__}: {message}"
        return err.__class__.__name__

    def _log_event(
        self,
        level: str,
        message: str,
        *,
        status: str | None = None,
        error: str | None = None,
        **updates: Any,
    ) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        self._recent_logs.append(f"{timestamp} [{level.upper()}] {message}")
        if status is not None:
            updates["status"] = status
        if error is not None or status == "completed":
            updates["last_error"] = error
        if updates:
            self._diagnostics.update(updates)
        getattr(_LOGGER, level, _LOGGER.info)("Smart Doorbell '%s': %s", self._name, message)
        self._notify_listeners()

    async def async_setup(self) -> None:
        trigger = self.entry.data[CONF_TRIGGER_ENTITY]

        @callback
        def _event_filter(event_data) -> bool:
            return event_data.get("entity_id") == trigger

        @callback
        def _state_changed(event):
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            self._diagnostics.update({
                "last_trigger_event_at": datetime.now().isoformat(timespec="seconds"),
                "last_trigger_old_state": old.state if old else None,
                "last_trigger_new_state": new.state if new else None,
            })
            if old is None or new is None:
                self._log_event(
                    "debug",
                    f"Ignored trigger event for {trigger} because the state transition was incomplete.",
                    last_reason="Ignored trigger event with incomplete state data.",
                )
                return
            if old.state != "on" and new.state == "on":
                self._log_event(
                    "debug",
                    f"Accepted trigger transition for {trigger}: {old.state} -> {new.state}.",
                    last_reason=f"Accepted trigger transition {old.state} -> {new.state}.",
                )
                self.hass.async_create_task(self._handle_ring(source="trigger_entity"))
                return
            self._log_event(
                "debug",
                f"Ignored trigger transition for {trigger}: {old.state} -> {new.state}.",
                last_reason=f"Ignored trigger transition {old.state} -> {new.state}.",
            )

        self._unsub_listener = self.hass.bus.async_listen(
            "state_changed",
            _state_changed,
            event_filter=_event_filter,
        )
        self._log_event(
            "info",
            f"Listening for trigger entity {trigger}.",
            last_reason=f"Listening for trigger entity {trigger}.",
        )

    async def async_unload(self) -> None:
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

    def _is_debounced(self) -> bool:
        opts = self.entry.options
        if not opts.get(CONF_DEBOUNCE_ENABLED, False):
            return False

        debounce_duration: float = opts.get(CONF_DEBOUNCE_DURATION, DEBOUNCE_DEFAULT_DURATION)
        current_time = time.time()
        time_since_last_ring = current_time - self._last_ring_time

        if time_since_last_ring < debounce_duration:
            remaining = debounce_duration - time_since_last_ring
            self._log_event(
                "debug",
                f"Ring ignored due to debounce ({remaining:.2f}s remaining).",
                status="debounced",
                last_reason=f"Ring ignored due to debounce ({remaining:.2f}s remaining).",
            )
            return True

        return False

    def _dnd_active(self) -> bool:
        if self._switch_on(SWITCH_DND_MANUAL):
            return True
        opts = self.entry.options
        if not opts.get(CONF_DND_ENABLED, False):
            return False
        try:
            now = datetime.now().time().replace(second=0, microsecond=0)
            start = dt_time.fromisoformat(opts[CONF_DND_START][:5])
            end = dt_time.fromisoformat(opts[CONF_DND_END][:5])
            if start <= end:
                return start <= now <= end
            return now >= start or now <= end
        except Exception as err:
            self._log_event(
                "warning",
                f"Failed to evaluate Do Not Disturb schedule: {self._format_exception(err)}.",
                error=self._format_exception(err),
            )
            return False

    async def _handle_ring(self, source: str = "trigger_entity") -> None:
        if self._is_debounced():
            return

        self._last_ring_time = time.time()
        trigger_time = datetime.now().isoformat(timespec="seconds")
        opts = self.entry.options
        dnd = self._dnd_active()
        action_results: dict[str, str] = {}
        tasks: dict[str, Any] = {}

        self._log_event(
            "info",
            f"Doorbell ring accepted from {source}.",
            status="triggered",
            error=None,
            last_reason=f"Doorbell ring accepted from {source}.",
            last_triggered_at=trigger_time,
            last_trigger_source=source,
            dnd_active=dnd,
            last_actions={},
        )

        if self._switch_on(SWITCH_LIGHT_FLASH):
            if dnd and opts.get(CONF_DND_AFFECTS_LIGHTS, True):
                action_results["light_flash"] = "suppressed_by_dnd"
            else:
                light_entities: list[str] = opts.get(CONF_LIGHT_ENTITIES, [])
                if light_entities:
                    tasks["light_flash"] = self._flash_lights()
                else:
                    action_results["light_flash"] = "not_configured"
        else:
            action_results["light_flash"] = "disabled"

        if self._switch_on(SWITCH_TELEGRAM):
            if dnd and opts.get(CONF_DND_AFFECTS_TELEGRAM, True):
                action_results["telegram"] = "suppressed_by_dnd"
            else:
                tasks["telegram"] = self._send_telegram()
        else:
            action_results["telegram"] = "disabled"

        if self._switch_on(SWITCH_SPEAKER):
            if dnd and opts.get(CONF_DND_AFFECTS_SPEAKER, True):
                action_results["speaker"] = "suppressed_by_dnd"
            else:
                speaker_configs: list[dict] = opts.get(CONF_SPEAKER_CONFIGS, [])
                if speaker_configs:
                    tasks["speaker"] = self._announce_all_speakers()
                else:
                    action_results["speaker"] = "not_configured"
        else:
            action_results["speaker"] = "disabled"

        if not tasks:
            self._log_event(
                "warning",
                "No notification actions were run for this ring.",
                status="skipped",
                last_reason="No notification actions were run for this ring.",
                last_actions=action_results,
                dnd_active=dnd,
            )
            return

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        errors: list[str] = []
        for action_name, result in zip(tasks, results):
            if isinstance(result, Exception):
                error_text = self._format_exception(result)
                action_results[action_name] = f"error: {error_text}"
                errors.append(f"{action_name}: {error_text}")
                self._log_event("error", f"{action_name} failed: {error_text}.")
                continue
            action_results[action_name] = result
            self._log_event("debug", f"{action_name} completed: {result}.")

        if errors:
            combined_error = "; ".join(errors)
            self._log_event(
                "error",
                "Ring processing completed with errors.",
                status="error",
                error=combined_error,
                last_reason="Ring processing completed with errors.",
                last_actions=action_results,
                dnd_active=dnd,
            )
            return

        self._log_event(
            "info",
            "Ring processing completed successfully.",
            status="completed",
            error=None,
            last_reason="Ring processing completed successfully.",
            last_actions=action_results,
            dnd_active=dnd,
        )

    async def _flash_lights(self) -> str:
        opts = self.entry.options
        entities: list[str] = opts.get(CONF_LIGHT_ENTITIES, [])
        duration: float = opts.get(CONF_LIGHT_FLASH_DURATION, 1.0)
        if not entities:
            return "No light entities configured."

        snapshots: dict[str, dict[str, Any]] = {}
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

        lights = [e for e in entities if e.split(".")[0] == "light"]
        switches = [e for e in entities if e.split(".")[0] == "switch"]
        lights_on = [e for e in lights if snapshots.get(e, {}).get("state") == "on"]
        lights_off = [e for e in lights if snapshots.get(e, {}).get("state") != "on"]
        sw_on = [e for e in switches if snapshots.get(e, {}).get("state") == "on"]
        sw_off = [e for e in switches if snapshots.get(e, {}).get("state") != "on"]

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

        for eid, snap in snapshots.items():
            domain = snap["domain"]
            if snap["state"] == "off":
                await self.hass.services.async_call(
                    domain, "turn_off", {"entity_id": eid}, blocking=True
                )
            else:
                if domain == "light":
                    svc_data: dict[str, Any] = {"entity_id": eid}
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

        return f"Flashed {len(entities)} entities for {duration:.1f}s."

    async def _send_telegram(self) -> str:
        opts = self.entry.options
        message: str = opts.get(CONF_TELEGRAM_MESSAGE, "Doorbell rang!")
        await self.hass.services.async_call(
            "telegram_bot",
            "send_message",
            {"message": message},
            blocking=True,
        )
        return "Sent Telegram message."

    async def _announce_all_speakers(self) -> str:
        opts = self.entry.options
        speaker_configs: list[dict] = opts.get(CONF_SPEAKER_CONFIGS, [])
        overall_volume: float = opts.get(CONF_OVERALL_VOLUME, 80) / 100.0
        if not speaker_configs:
            return "No speaker entities configured."

        results = await asyncio.gather(
            *(self._announce_speaker(cfg, overall_volume) for cfg in speaker_configs),
            return_exceptions=True,
        )

        announced: list[str] = []
        errors: list[str] = []
        for cfg, result in zip(speaker_configs, results):
            entity_id = cfg.get(CONF_SPEAKER_ENTITY, "not_configured")
            if isinstance(result, Exception):
                errors.append(f"{entity_id}: {self._format_exception(result)}")
                continue
            announced.append(f"{entity_id} ({result})")

        if errors:
            raise RuntimeError("; ".join(errors))

        return f"Announced on {len(announced)} speaker(s): {', '.join(announced)}."

    async def _announce_speaker(self, cfg: dict, overall_volume: float) -> str:
        entity_id: str = cfg.get(CONF_SPEAKER_ENTITY, "")
        if not entity_id:
            raise ValueError("Missing speaker entity ID.")

        set_volume: bool = cfg.get(CONF_SPEAKER_SET_VOLUME, True)
        vol_pct: float = cfg.get(CONF_SPEAKER_VOLUME, 80) / 100.0
        effective_volume = round(min(vol_pct * overall_volume, 1.0), 2)
        content_type: str = cfg.get(CONF_MEDIA_CONTENT_TYPE, "audio/mpeg")
        startup_delay: float = cfg.get(CONF_SPEAKER_STARTUP_DELAY, 0)

        ringtone: str = cfg.get(CONF_RINGTONE_PATH, "")
        ringtone_dur: int = cfg.get(CONF_RINGTONE_DURATION, 3)
        tts_enabled: bool = cfg.get(CONF_TTS_ENABLED, False)
        tts_realtime: bool = cfg.get(CONF_TTS_REALTIME, False)
        tts_text: str = cfg.get(CONF_TTS_REALTIME_TEXT, "")
        tts_engine: str = cfg.get(CONF_TTS_ENGINE, "")
        tts_file: str = cfg.get(CONF_TTS_FILE_PATH, "")

        if not ringtone and not tts_enabled:
            self._log_event(
                "warning",
                f"Speaker {entity_id} skipped because no ringtone or TTS is configured.",
            )
            return "skipped: no ringtone or TTS configured"

        if set_volume:
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {"entity_id": entity_id, "volume_level": effective_volume},
                blocking=True,
            )

        if startup_delay > 0:
            await asyncio.sleep(startup_delay)

        if ringtone:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_id": ringtone,
                    "media_content_type": content_type,
                },
                blocking=False,
            )
            await asyncio.sleep(ringtone_dur)

        if tts_enabled:
            if tts_realtime and tts_text and tts_engine:
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    {
                        "entity_id": tts_engine,
                        "media_player_entity_id": entity_id,
                        "message": tts_text,
                    },
                    blocking=True,
                )
            elif tts_file:
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": entity_id,
                        "media_content_id": tts_file,
                        "media_content_type": content_type,
                    },
                    blocking=False,
                )
            else:
                self._log_event(
                    "warning",
                    f"Speaker {entity_id} has TTS enabled but no valid TTS source is configured.",
                )
                return "warning: TTS enabled without a valid source"

        details: list[str] = []
        if ringtone:
            details.append("ringtone")
        if tts_enabled:
            details.append("tts")
        return ", ".join(details) or "no audio"
