"""Native HA TTS entity using the separately configured Assist speech profile."""
from homeassistant.components.tts import TextToSpeechEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AutomationAITTS(hass.data[DOMAIN][entry.entry_id], entry.entry_id)])


class AutomationAITTS(TextToSpeechEntity):
    _attr_name = "Automation AI Deutsch"
    _attr_has_entity_name = True
    _attr_default_language = "de"
    _attr_supported_languages = ["de", "de-DE"]
    _attr_supported_options = []

    def __init__(self, client, entry_id):
        self.client = client
        self._attr_unique_id = entry_id+"_tts"

    @property
    def default_language(self): return "de"

    @property
    def supported_languages(self): return ["de", "de-DE"]

    async def async_get_tts_audio(self, message, language, options=None):
        data = await self.client.request("/internal/tts", {"text": message}, binary=True)
        return "wav", data
