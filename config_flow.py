"""Config flow and Options flow for Smart Doorbell."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import *


class SmartDoorbellConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TRIGGER_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_DOORBELL_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_DOORBELL_NAME): str,
                vol.Required(CONF_TRIGGER_ENTITY): selector.selector({
                    "entity": {"domain": "binary_sensor"}
                }),
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return SmartDoorbellOptionsFlow(config_entry)


class SmartDoorbellOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)
        self._selected_speakers: list[str] = []
        self._speaker_configs: list[dict] = []
        self._speaker_index: int = 0

    async def async_step_init(self, user_input=None):
        return await self.async_step_trigger()

    # ------------------------------------------------------------------ #
    # Step 1 — Trigger
    # ------------------------------------------------------------------ #
    async def async_step_trigger(self, user_input=None):
        errors = {}
        if user_input is not None:
            trigger_entity = user_input[CONF_TRIGGER_ENTITY]
            if self._is_trigger_configured_elsewhere(trigger_entity):
                errors["base"] = "already_configured"
            else:
                self._data[CONF_TRIGGER_ENTITY] = trigger_entity
                return await self.async_step_light_flash()

        return self.async_show_form(
            step_id="trigger",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(
                    CONF_TRIGGER_ENTITY,
                    default=self._data[CONF_TRIGGER_ENTITY],
                ): selector.selector({
                    "entity": {"domain": "binary_sensor"}
                }),
            }),
        )

    def _is_trigger_configured_elsewhere(self, trigger_entity: str) -> bool:
        return any(
            entry.entry_id != self._entry.entry_id
            and (entry.options.get(CONF_TRIGGER_ENTITY) or entry.data.get(CONF_TRIGGER_ENTITY))
            == trigger_entity
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    # Step 2 — Light Flash
    # ------------------------------------------------------------------ #
    async def async_step_light_flash(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_telegram()

        opts = self._options
        return self.async_show_form(
            step_id="light_flash",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_LIGHT_ENTITIES,
                    default=opts.get(CONF_LIGHT_ENTITIES, []),
                ): selector.selector({
                    "entity": {
                        "domain": ["light", "switch"],
                        "multiple": True,
                    }
                }),
                vol.Optional(
                    CONF_LIGHT_FLASH_DURATION,
                    default=opts.get(CONF_LIGHT_FLASH_DURATION, 1),
                ): selector.selector({
                    "number": {
                        "min": 0.1, "max": 60,
                        "step": 0.1,
                        "unit_of_measurement": "s", "mode": "slider"
                    }
                }),
                vol.Optional(
                    CONF_DND_AFFECTS_LIGHTS,
                    default=opts.get(CONF_DND_AFFECTS_LIGHTS, True),
                ): bool,
            }),
        )

    # ------------------------------------------------------------------ #
    # Step 3 — Telegram
    # ------------------------------------------------------------------ #
    async def async_step_telegram(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_speaker()

        opts = self._options
        return self.async_show_form(
            step_id="telegram",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_TELEGRAM_MESSAGE,
                    default=opts.get(CONF_TELEGRAM_MESSAGE, "🔔 Doorbell rang!"),
                ): str,
                vol.Optional(
                    CONF_DND_AFFECTS_TELEGRAM,
                    default=opts.get(CONF_DND_AFFECTS_TELEGRAM, True),
                ): bool,
            }),
        )

    # ------------------------------------------------------------------ #
    # Step 4 — Speaker global
    # ------------------------------------------------------------------ #
    async def async_step_speaker(self, user_input=None):
        if user_input is not None:
            self._options[CONF_OVERALL_VOLUME] = user_input[CONF_OVERALL_VOLUME]
            self._options[CONF_DND_AFFECTS_SPEAKER] = user_input[CONF_DND_AFFECTS_SPEAKER]
            self._selected_speakers = user_input.get(CONF_SPEAKER_ENTITIES, [])
            self._speaker_configs = []
            self._speaker_index = 0

            if self._selected_speakers:
                return await self.async_step_speaker_detail()
            self._options[CONF_SPEAKER_CONFIGS] = []
            return await self.async_step_debounce()

        opts = self._options
        existing_speakers = [
            cfg.get(CONF_SPEAKER_ENTITY)
            for cfg in opts.get(CONF_SPEAKER_CONFIGS, [])
        ]
        return self.async_show_form(
            step_id="speaker",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SPEAKER_ENTITIES,
                    default=existing_speakers,
                ): selector.selector({
                    "entity": {"domain": "media_player", "multiple": True}
                }),
                vol.Optional(
                    CONF_OVERALL_VOLUME,
                    default=opts.get(CONF_OVERALL_VOLUME, 80),
                ): selector.selector({
                    "number": {
                        "min": 0, "max": 100,
                        "unit_of_measurement": "%", "mode": "slider"
                    }
                }),
                vol.Optional(
                    CONF_DND_AFFECTS_SPEAKER,
                    default=opts.get(CONF_DND_AFFECTS_SPEAKER, True),
                ): bool,
            }),
        )

    # ------------------------------------------------------------------ #
    # Step 5 — Per-speaker detail
    # ------------------------------------------------------------------ #
    async def async_step_speaker_detail(self, user_input=None):
        entity_id = self._selected_speakers[self._speaker_index]

        if user_input is not None:
            self._speaker_configs.append({
                CONF_SPEAKER_ENTITY: entity_id,
                **user_input,
            })
            self._speaker_index += 1
            if self._speaker_index < len(self._selected_speakers):
                return await self.async_step_speaker_detail()
            self._options[CONF_SPEAKER_CONFIGS] = self._speaker_configs
            return await self.async_step_debounce()

        existing = next(
            (
                cfg for cfg in self._options.get(CONF_SPEAKER_CONFIGS, [])
                if cfg.get(CONF_SPEAKER_ENTITY) == entity_id
            ),
            {},
        )

        return self.async_show_form(
            step_id="speaker_detail",
            description_placeholders={"speaker": entity_id},
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SPEAKER_SET_VOLUME,
                    default=existing.get(CONF_SPEAKER_SET_VOLUME, True),
                ): selector.selector({"boolean": {}}),
                vol.Optional(
                    CONF_SPEAKER_VOLUME,
                    default=existing.get(CONF_SPEAKER_VOLUME, 80),
                ): selector.selector({
                    "number": {
                        "min": 0, "max": 100,
                        "unit_of_measurement": "%", "mode": "slider",
                    }
                }),
                vol.Optional(
                    CONF_SPEAKER_STARTUP_DELAY,
                    default=existing.get(CONF_SPEAKER_STARTUP_DELAY, 0),
                ): selector.selector({
                    "number": {
                        "min": 0, "max": 5,
                        "step": 0.1,
                        "unit_of_measurement": "s", "mode": "slider",
                    }
                }),
                vol.Optional(
                    CONF_MEDIA_CONTENT_TYPE,
                    default=existing.get(CONF_MEDIA_CONTENT_TYPE, "audio/mpeg"),
                ): selector.selector({
                    "select": {
                        "options": MEDIA_CONTENT_TYPE_OPTIONS,
                        "mode": "dropdown",
                    }
                }),
                vol.Optional(
                    CONF_RINGTONE_PATH,
                    default=existing.get(CONF_RINGTONE_PATH, ""),
                ): str,
                vol.Optional(
                    CONF_RINGTONE_DURATION,
                    default=existing.get(CONF_RINGTONE_DURATION, 3),
                ): selector.selector({
                    "number": {
                        "min": 0, "max": 30,
                        "unit_of_measurement": "s", "mode": "slider",
                    }
                }),
                vol.Optional(
                    CONF_TTS_ENABLED,
                    default=existing.get(CONF_TTS_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_TTS_REALTIME,
                    default=existing.get(CONF_TTS_REALTIME, False),
                ): bool,
                vol.Optional(
                    CONF_TTS_REALTIME_TEXT,
                    default=existing.get(CONF_TTS_REALTIME_TEXT, "Someone is at the door"),
                ): str,
                vol.Optional(
                    CONF_TTS_ENGINE,
                    default=existing.get(CONF_TTS_ENGINE, ""),
                ): selector.selector({
                    "entity": {"domain": "tts"}
                }),
                vol.Optional(
                    CONF_TTS_FILE_PATH,
                    default=existing.get(CONF_TTS_FILE_PATH, ""),
                ): str,
            }),
        )

    # ------------------------------------------------------------------ #
    # Step 6 — Debounce
    # ------------------------------------------------------------------ #
    async def async_step_debounce(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_dnd()

        opts = self._options
        return self.async_show_form(
            step_id="debounce",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_DEBOUNCE_ENABLED,
                    default=opts.get(CONF_DEBOUNCE_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_DEBOUNCE_DURATION,
                    default=opts.get(CONF_DEBOUNCE_DURATION, DEBOUNCE_DEFAULT_DURATION),
                ): selector.selector({
                    "number": {
                        "min": DEBOUNCE_MIN_DURATION, "max": DEBOUNCE_MAX_DURATION,
                        "step": DEBOUNCE_DURATION_STEP,
                        "unit_of_measurement": "s", "mode": "slider"
                    }
                }),
            }),
        )

    # ------------------------------------------------------------------ #
    # Step 7 — Do Not Disturb
    # ------------------------------------------------------------------ #
    async def async_step_dnd(self, user_input=None):
        if user_input is not None:
            self._options.update(user_input)
            if self._data != self._entry.data:
                self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data=self._options)

        opts = self._options
        return self.async_show_form(
            step_id="dnd",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_DND_ENABLED,
                    default=opts.get(CONF_DND_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_DND_START,
                    default=opts.get(CONF_DND_START, "22:00:00"),
                ): selector.selector({"time": {}}),
                vol.Optional(
                    CONF_DND_END,
                    default=opts.get(CONF_DND_END, "08:00:00"),
                ): selector.selector({"time": {}}),
            }),
        )