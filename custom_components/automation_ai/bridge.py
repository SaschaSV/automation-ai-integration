"""Narrow native config adapter, runtime-shape guarded and locked with HA's editor."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from pathlib import Path
import re
import uuid

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from .const import VERSION

KINDS = {"automation": "automations.yaml", "script": "scripts.yaml", "scene": "scenes.yaml"}


def find_view(hass, kind):
    """Locate the already registered native editor through its bound handler.

    No version guesses: if the shape changed, writing stays unavailable.
    """
    from homeassistant.components.config.view import BaseEditConfigView
    seen = set()
    def walk(value, depth=0):
        if id(value) in seen or depth > 8: return None
        seen.add(id(value))
        bound = getattr(value, "__self__", None)
        if isinstance(bound, BaseEditConfigView) and bound.url == f"/api/config/{kind}/config/{{config_key}}": return bound
        wrapped = getattr(value, "__wrapped__", None)
        if wrapped:
            result = walk(wrapped, depth+1)
            if result: return result
        for cell in getattr(value, "__closure__", ()) or ():
            try: nested = cell.cell_contents
            except ValueError: continue
            if inspect.isfunction(nested) or inspect.ismethod(nested):
                result = walk(nested, depth+1)
                if result: return result
        return None
    for route in hass.http.app.router.routes():
        result = walk(route.handler)
        if result and all(hasattr(result, a) for a in ("mutation_lock", "read_config", "_write_value", "_delete_value", "_get_value", "path")):
            return result
    raise HomeAssistantError("Nativer Konfigurationsadapter passt nicht zur installierten HA-Version; Schreiben gesperrt.")


def source_bytes(hass, kind):
    root = Path(hass.config.config_dir).resolve()
    main = root / "configuration.yaml"
    if main.stat().st_size > 2_000_000: raise HomeAssistantError("Hauptkonfiguration zu groß.")
    text = main.read_text(encoding="utf-8")
    pattern = rf"(?m)^{kind}:\s*!include\s+{re.escape(KINDS[kind])}\s*(?:#.*)?$"
    if not re.search(pattern, text): raise HomeAssistantError("Nur die native, direkt eingebundene YAML-Datei ist bearbeitbar; Packages und andere Includes bleiben erhalten.")
    path = root / KINDS[kind]
    if path.is_symlink() or path.resolve().parent != root: raise HomeAssistantError("Abweichender Konfigurationspfad nicht unterstützt.")
    if path.exists() and path.stat().st_size > 2_000_000: raise HomeAssistantError("Konfigurationsdatei zu groß.")
    data = path.read_bytes() if path.exists() else b""
    if re.search(rb"!\w+", data): raise HomeAssistantError("YAML-Datei enthält benutzerdefinierte Tags oder weitere Includes; keine automatische Umschreibung.")
    return data


async def snapshot(hass, kind, key, view):
    raw = await hass.async_add_executor_job(source_bytes, hass, kind)
    current = await view.read_config(hass)
    if kind != "script":
        ids = [row.get("id") for row in current]
        if any(not i for i in ids) or len(ids) != len(set(ids)):
            raise HomeAssistantError("Fehlende oder doppelte IDs in der Quelldatei; keine Änderung fremder Einträge.")
    value = view._get_value(hass, current, key)
    if value and "use_blueprint" in value: raise HomeAssistantError("Blueprint-Quelle wird nicht umgeschrieben.")
    if value is None:
        registry = er.async_get(hass)
        platform = "homeassistant" if kind == "scene" else kind
        if registry.async_get_entity_id(kind, platform, key):
            raise HomeAssistantError("Objekt existiert aus einer anderen Quelle; keine Dublette.")
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(kind, "homeassistant" if kind == "scene" else kind, key)
    runtime = hass.states.get(eid) if eid else None
    runtime_value = {"entity_id": eid, "state": runtime.state, "last_updated": runtime.last_updated.isoformat(), "context": runtime.context.as_dict()} if runtime else None
    return {"safe": True, "kind": kind, "key": key, "source_hash": hashlib.sha256(raw).hexdigest(), "value": value, "source": KINDS[kind], "runtime": runtime_value}, current


@callback
def async_register(hass):
    for handler in (capabilities, config_snapshot, config_write, entity_for_config, zigbee_permit, webdav_match): websocket_api.async_register_command(hass, handler)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/webdav_match", vol.Required("url"): str,
    vol.Required("username"): str, vol.Required("backup_path"): str})
@websocket_api.async_response
async def webdav_match(hass, connection, msg):
    entries = [e for e in hass.config_entries.async_entries("webdav") if e.data.get("url") == msg["url"] and e.data.get("username") == msg["username"]]
    if len(entries) > 1:
        connection.send_error(msg["id"], "ambiguous", "Mehrere passende WebDAV-Einträge."); return
    if not entries:
        connection.send_result(msg["id"], {"entry_id": None, "agent_ids": []}); return
    entry = entries[0]
    if entry.data.get("backup_path", "/") != msg["backup_path"] or entry.data.get("verify_ssl", True) is not True:
        connection.send_error(msg["id"], "scope", "Vorhandenes WebDAV-Ziel hat einen anderen Pfad oder deaktivierte Zertifikatsprüfung."); return
    from homeassistant.components.backup.const import DATA_MANAGER
    manager = hass.data.get(DATA_MANAGER)
    agents = [key for key, agent in manager.backup_agents.items() if agent.unique_id == entry.entry_id] if manager else []
    connection.send_result(msg["id"], {"entry_id": entry.entry_id, "agent_ids": agents})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/capabilities"})
@websocket_api.async_response
async def capabilities(hass, connection, msg):
    editable = []
    for kind in KINDS:
        try: find_view(hass, kind); editable.append(kind)
        except (HomeAssistantError, ImportError, AttributeError): pass
    connection.send_result(msg["id"], {"version": VERSION, "native_editors": editable, "mqtt": "mqtt" in hass.config.components,
        "limits": ["Nur native Standardquellen; keine Packages, Blueprints, freien Dateien oder Shellbefehle.", "Manuelle Dateieditoren außerhalb der HA-API teilen deren Sperre nicht."]})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/config_snapshot", vol.Required("kind"): vol.In(KINDS), vol.Required("key"): str})
@websocket_api.async_response
async def config_snapshot(hass, connection, msg):
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", msg["key"]): raise HomeAssistantError("Ungültige ID.")
        view = find_view(hass, msg["kind"])
        async with view.mutation_lock:
            value, _ = await snapshot(hass, msg["kind"], msg["key"], view)
        connection.send_result(msg["id"], value)
    except (HomeAssistantError, ValueError, KeyError, TypeError, ImportError, AttributeError) as exc:
        connection.send_error(msg["id"], "not_supported", str(exc) if isinstance(exc, HomeAssistantError) else "Quelladapter nicht verfügbar.")


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/config_write", vol.Required("kind"): vol.In(KINDS),
    vol.Required("key"): str, vol.Required("value"): vol.Any(dict, None), vol.Required("expected_source"): str})
@websocket_api.async_response
async def config_write(hass, connection, msg):
    kind, key, value = msg["kind"], msg["key"], msg["value"]
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key) or len(json.dumps(value)) > 150000: raise HomeAssistantError("Ungültige Konfigurationsgröße oder ID.")
        from homeassistant.components.config.view import _write
        from homeassistant.components.config.const import ACTION_CREATE_UPDATE, ACTION_DELETE
        view = find_view(hass, kind)
        async with view.mutation_lock:
            before, current = await snapshot(hass, kind, key, view)
            if before["source_hash"] != msg["expected_source"]: raise HomeAssistantError("Quelle wurde zwischenzeitlich verändert.")
            view.key_schema(key)
            if value is None:
                if before["value"] is None: raise HomeAssistantError("Objekt fehlt.")
                view._delete_value(hass, current, key)
            else:
                if "use_blueprint" in value or (kind != "script" and value.get("id", key) != key): raise HomeAssistantError("ID/Quelle darf nicht verändert werden.")
                if view.data_validator: await view.data_validator(hass, key, value)
                elif view.data_schema: view.data_schema(value)
                else: raise HomeAssistantError("Nativer Validator fehlt.")
                view._write_value(hass, current, key, value)
            # Recheck raw file immediately before the native atomic writer (external editor detection).
            raw = await hass.async_add_executor_job(source_bytes, hass, kind)
            if hashlib.sha256(raw).hexdigest() != msg["expected_source"]: raise HomeAssistantError("Datei wurde außerhalb des Editors verändert.")
            await hass.async_add_executor_job(_write, hass.config.path(view.path), current)
        if view.post_write_hook is not None: await view.post_write_hook(ACTION_DELETE if value is None else ACTION_CREATE_UPDATE, key)
        connection.send_result(msg["id"], {"written": True})
    except Exception as exc:
        connection.send_error(msg["id"], "write_failed", str(exc) if isinstance(exc, HomeAssistantError) else "Native Validierung oder Schreibvorgang fehlgeschlagen; Zustand prüfen.")


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/entity_for_config", vol.Required("kind"): vol.In(KINDS), vol.Required("key"): str})
@websocket_api.async_response
async def entity_for_config(hass, connection, msg):
    registry = er.async_get(hass)
    platform = "homeassistant" if msg["kind"] == "scene" else msg["kind"]
    connection.send_result(msg["id"], registry.async_get_entity_id(msg["kind"], platform, msg["key"]))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "automation_ai/zigbee_permit", vol.Required("base_topic"): str,
    vol.Required("duration"): vol.All(int, vol.Range(min=0, max=254))})
@websocket_api.async_response
async def zigbee_permit(hass, connection, msg):
    from homeassistant.components import mqtt
    base = msg["base_topic"]
    if not re.fullmatch(r"[A-Za-z0-9_/-]{1,100}", base) or ".." in base:
        connection.send_error(msg["id"], "invalid_format", "Ungültiger MQTT-Präfix."); return
    transaction = uuid.uuid4().hex
    future = asyncio.get_running_loop().create_future()
    @callback
    def on_message(message):
        try: value = json.loads(message.payload)
        except (ValueError, TypeError): return
        if value.get("transaction") == transaction and not future.done(): future.set_result(value)
    unsubscribe = await mqtt.async_subscribe(hass, base+"/bridge/response/permit_join", on_message, qos=1)
    try:
        await mqtt.async_publish(hass, base+"/bridge/request/permit_join", json.dumps({"time": msg["duration"], "transaction": transaction}), qos=1, retain=False)
        result = await asyncio.wait_for(future, 20)
        if result.get("status") != "ok": raise HomeAssistantError("Zigbee2MQTT hat das Kopplungsfenster abgelehnt.")
        connection.send_result(msg["id"], {"accepted": True, "duration": msg["duration"]})
    except Exception:
        connection.send_error(msg["id"], "pairing_unconfirmed", "Kopplungsfenster nicht bestätigt; keine automatische Wiederholung.")
    finally: unsubscribe()
