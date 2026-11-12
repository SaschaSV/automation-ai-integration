"""Signed local-only channel. No API token or pairing secret is sent in request bodies."""
import hashlib
import hmac
import json
import secrets
import time

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError


class BridgeClient:
    def __init__(self, hass, data): self.hass, self.data = hass, data

    async def request(self, path, value, *, binary=False):
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        stamp, nonce = str(time.time()), secrets.token_hex(16)
        signature = hmac.new(self.data["pairing_key"].encode(), f"POST\n{path}\n{stamp}\n{nonce}\n".encode()+body, hashlib.sha256).hexdigest()
        headers = {"Content-Type": "application/json", "X-AA-Time": stamp, "X-AA-Nonce": nonce, "X-AA-Signature": signature}
        try:
            async with async_get_clientsession(self.hass).post("http://"+self.data["app_host"]+":8099"+path,
                    data=body, headers=headers, allow_redirects=False, timeout=90) as response:
                if response.status != 200: raise HomeAssistantError("Automation AI konnte die interne Anfrage nicht autorisieren oder abschließen.")
                if binary:
                    value = await response.content.read(16_000_001)
                    if len(value) > 16_000_000: raise HomeAssistantError("Sprachausgabe zu groß.")
                    return value
                return await response.json()
        except HomeAssistantError: raise
        except Exception as exc: raise HomeAssistantError("Automation AI ist nicht erreichbar; keine automatische Wiederholung.") from exc
