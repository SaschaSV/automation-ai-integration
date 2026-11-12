import re
try:
    import probatio as vol
except ImportError:
    import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Only the local app's Supervisor DNS name; never arbitrary IPs or URLs.
            if not re.fullmatch(r"(?:local|[a-f0-9]{8})-automation-ai", user_input.get("app_host", "")):
                errors["app_host"] = "invalid_host"
            elif not re.fullmatch(r"[a-f0-9]{64}", user_input.get("pairing_key", "")):
                errors["pairing_key"] = "invalid_key"
            else:
                await self.async_set_unique_id("automation_ai_local")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Automation AI", data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("app_host", default="local-automation-ai"): str,
            vol.Required("pairing_key"): str,
        }), errors=errors)
