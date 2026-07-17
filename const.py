DOMAIN = "smart_doorbell"
PLATFORMS = ["switch", "button", "sensor"]

# Core config
CONF_DOORBELL_NAME = "doorbell_name"
CONF_TRIGGER_ENTITY = "trigger_entity"

# Light Flash
CONF_LIGHT_ENTITIES = "light_entities"
CONF_LIGHT_FLASH_DURATION = "light_flash_duration"
CONF_DND_AFFECTS_LIGHTS = "dnd_affects_lights"

# Telegram
CONF_TELEGRAM_MESSAGE = "telegram_message"
CONF_DND_AFFECTS_TELEGRAM = "dnd_affects_telegram"

# Speaker (global)
CONF_SPEAKER_ENTITIES = "speaker_entities"
CONF_OVERALL_VOLUME = "overall_volume"
CONF_DND_AFFECTS_SPEAKER = "dnd_affects_speaker"
CONF_SPEAKER_CONFIGS = "speaker_configs"

# Speaker (per entity)
CONF_SPEAKER_ENTITY = "speaker_entity"
CONF_SPEAKER_VOLUME = "speaker_volume"
CONF_SPEAKER_SET_VOLUME = "speaker_set_volume"
CONF_MEDIA_CONTENT_TYPE = "media_content_type"
CONF_RINGTONE_PATH = "ringtone_path"
CONF_RINGTONE_DURATION = "ringtone_duration"
CONF_TTS_ENABLED = "tts_enabled"
CONF_TTS_REALTIME = "tts_realtime"
CONF_TTS_REALTIME_TEXT = "tts_realtime_text"
CONF_TTS_ENGINE = "tts_engine"
CONF_TTS_FILE_PATH = "tts_file_path"
CONF_SPEAKER_STARTUP_DELAY = "speaker_startup_delay"

# Do Not Disturb
CONF_DND_ENABLED = "dnd_enabled"
CONF_DND_START = "dnd_start"
CONF_DND_END = "dnd_end"

# Debounce
CONF_DEBOUNCE_ENABLED = "debounce_enabled"
CONF_DEBOUNCE_DURATION = "debounce_duration"
DEBOUNCE_MIN_DURATION = 0.1
DEBOUNCE_MAX_DURATION = 10.0
DEBOUNCE_DURATION_STEP = 0.1
DEBOUNCE_DEFAULT_DURATION = 0.5

# Runtime switch keys
SWITCH_LIGHT_FLASH = "light_flash"
SWITCH_TELEGRAM = "telegram"
SWITCH_SPEAKER = "speaker"
SWITCH_DND_MANUAL = "dnd_manual"

DEFAULT_SWITCHES = {
    SWITCH_LIGHT_FLASH: True,
    SWITCH_TELEGRAM: True,
    SWITCH_SPEAKER: True,
    SWITCH_DND_MANUAL: False,
}

MEDIA_CONTENT_TYPE_OPTIONS = [
    {"value": "audio/mpeg",  "label": "audio/mpeg (MP3 — ReSpeaker/satellite)"},
    {"value": "audio/wav",   "label": "audio/wav (WAV)"},
    {"value": "audio/ogg",   "label": "audio/ogg (OGG)"},
    {"value": "music",       "label": "music (generic — Chromecast etc.)"},
]