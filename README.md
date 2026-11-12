# Automation AI – Home-Assistant-Integration

In HACS → Benutzerdefinierte Repositories `https://github.com/SaschaSV/automation-ai-integration` als **Integration** hinzufügen, Automation AI herunterladen und Home Assistant neu starten. Danach die Integration unter Geräte & Dienste hinzufügen und mit der Automation-AI-App koppeln. Die Aufnahme in den voreingestellten Marketplace-Katalog erfolgt nicht automatisch.

Bei bestehender manueller Installation zuerst ein vollständiges Home-Assistant-Backup erstellen, dann dieses Repository in HACS hinzufügen und herunterladen. HACS übernimmt denselben Ordner `custom_components/automation_ai`; keine zweite Integration anlegen. Künftige Releases erscheinen über HACS als Updates. Vor jedem Integrationsupdate ein vollständiges Backup einschließlich Home-Assistant-Konfiguration erstellen; danach ist ein Core-Neustart nötig. HACS-Updates werden nicht ohne Backup automatisch installiert.

Die App selbst wird getrennt aus `https://github.com/SaschaSV/homeassistant-apps` installiert. Beide Artefakte verwenden dieselbe Release-Version. Aktive Assist-Pipelines werden durch Installation oder Modellwahl nicht eigenmächtig umgestellt.

Dieses öffentliche Repository enthält nur den zur Installation nötigen Integrationscode. Der Entwicklungsquellcode bleibt privat. Keine Zugangsdaten veröffentlichen.
