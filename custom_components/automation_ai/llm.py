"""Assist handoff: no approval tool and no private context inferred from a wake word."""
import uuid
try:
    import probatio as vol
except ImportError:
    import voluptuous as vol
from homeassistant.core import callback
from homeassistant.helpers import llm
try:
    from homeassistant.components.llm import LLMTools
except ImportError:
    LLMTools = None
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .client import BridgeClient

PROMPT = "Für Einrichtung, Reparatur, Automationen und Backups automation_ai__auftrag verwenden. Ein Auftrag ist keine Ausführungsfreigabe. Kurz auf die prüfbare Karte in Automation AI hinweisen. Benutzeridentität niemals erfinden."


class JobTool(llm.Tool):
    name = "automation_ai__auftrag"
    title = "Automation-AI-Auftrag vorbereiten"
    description = "Natürlichen Verwaltungswunsch als persistenten Auftrag an Automation AI übergeben; keine direkte Freigabe."
    integration = DOMAIN
    parameters = vol.Schema({vol.Required("message"): str})
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=True)

    async def async_call(self, hass, tool_input, llm_context):
        uid = getattr(llm_context.context, "user_id", None)
        if not uid: raise HomeAssistantError("Für diesen Auftrag fehlt eine persönliche Benutzerzuordnung. Bitte Automation AI in deinem HA-Konto öffnen.")
        user = await hass.auth.async_get_user(uid)
        if not user or not user.is_active or not user.is_admin or user.system_generated:
            raise HomeAssistantError("Dieser Verwaltungsauftrag benötigt einen persönlichen Administrator.")
        client = next((v for v in hass.data.get(DOMAIN, {}).values() if isinstance(v, BridgeClient)), None)
        if not client: raise HomeAssistantError("Automation-AI-Bridge ist nicht eingerichtet.")
        message = tool_input.tool_args["message"]
        if not 1 <= len(message) <= 12000: raise HomeAssistantError("Auftrag zu lang.")
        request_id = str(getattr(tool_input, "id", None) or uuid.uuid4().hex)
        result = await client.request("/internal/assist", {"user_id": uid, "device_id": llm_context.device_id,
            "message": message, "request_id": request_id})
        return llm.ToolResult(data=result, error=bool(result.get("error"))) if hasattr(llm, "ToolResult") else result


@callback
def async_get_tools(hass, llm_context, api_id):
    if api_id not in ("assist", DOMAIN): return None
    return LLMTools(tools=[JobTool()], prompt=PROMPT) if LLMTools else None


class LegacyAPI(llm.API):
    def __init__(self, hass):
        super().__init__(hass=hass, id=DOMAIN, name="Automation AI – geprüfte Aufträge")

    async def async_get_api_instance(self, llm_context):
        return llm.APIInstance(api=self, api_prompt=PROMPT, llm_context=llm_context, tools=[JobTool()])


@callback
def register_legacy(hass):
    if LLMTools is not None: return lambda: None
    return llm.async_register_api(hass, LegacyAPI(hass))
