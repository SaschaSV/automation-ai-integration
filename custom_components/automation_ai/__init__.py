from homeassistant.const import Platform
from .client import BridgeClient
from .const import DOMAIN
from .bridge import async_register


async def async_setup(hass, config):
    return True


async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = BridgeClient(hass, entry.data)
    if not hass.data[DOMAIN].get("registered"):
        async_register(hass)
        hass.data[DOMAIN]["registered"] = True
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.TTS])
    # Older HA releases do not load the llm platform. Provide a separately selectable API there.
    from .llm import register_legacy
    entry.async_on_unload(register_legacy(hass))
    return True


async def async_unload_entry(hass, entry):
    result = await hass.config_entries.async_unload_platforms(entry, [Platform.TTS])
    if result: hass.data[DOMAIN].pop(entry.entry_id, None)
    return result
