"""
Liest Jira Business Epics aus lokalen JSON-Dateien, filtert und sortiert sie.

Dieses Skript durchsucht ein vordefiniertes Verzeichnis ('data/jira_issues') nach
JSON-Exporten von Jira-Vorgängen. Es identifiziert alle 'Business Epics',
schließt Vorgänge mit dem Status 'Withdrawn' oder 'Rejected' aus und sortiert
die verbleibenden Epics.

Die Sortierung erfolgt in zwei Stufen:
1.  Nach einer benutzerdefinierten Reihenfolge der Status (CUSTOM_STATUS_ORDER).
2.  Innerhalb jedes Status wird nach der 'fix_version' sortiert.

Das Ergebnis ist eine auf der Konsole ausgegebene, gruppierte Liste der
Business-Epic-Keys, die für einen schnellen Überblick über den aktuellen
Stand der Epics im Funnel und in der Entwicklung dient.
"""
import os
import json
import time

# --- Konfiguration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
JIRA_ISSUES_DIR = os.path.join(BASE_DIR, 'data', 'jira_issues')

# --- NEU: Definition der benutzerdefinierten Status-Reihenfolge ---
CUSTOM_STATUS_ORDER = [
    'Funnel',
    'Backlog for Analysis',
    'Analysis',
    'Review',
    'Backlog',
    'In Progress',
    'Closed'
]

# --- Hauptlogik ---
business_epics_list = []
print(f"✅ Korrekter Pfad wird durchsucht: {JIRA_ISSUES_DIR}\n")
start_time = time.time()

if not os.path.isdir(JIRA_ISSUES_DIR):
    print(f"Fehler: Das Verzeichnis '{JIRA_ISSUES_DIR}' wurde nicht gefunden.")
else:
    # Daten sammeln
    for filename in os.listdir(JIRA_ISSUES_DIR):
        if filename.endswith('.json'):
            file_path = os.path.join(JIRA_ISSUES_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if data.get('issue_type') == 'Business Epic':
                    resolution = data.get('resolution')
                    if resolution not in ['Withdrawn', 'Rejected']:
                        epic_info = {
                            'key': data.get('key'),
                            'status': data.get('status'),
                            'fix_versions': data.get('fix_versions', [])
                        }
                        business_epics_list.append(epic_info)

            except Exception as e:
                print(f"Fehler bei der Verarbeitung von {filename}: {e}")

# --- ANGEPASSTE SORTIERUNG mit benutzerdefinierter Reihenfolge ---

# Hilfsfunktion, um den Index für einen gegebenen Status zu ermitteln.
# Dies ermöglicht die Sortierung nach der CUSTOM_STATUS_ORDER-Liste.
def get_status_sort_key(epic):
    status = epic.get('status')
    try:
        # Gibt die Position (Index) des Status in der Liste zurück.
        return CUSTOM_STATUS_ORDER.index(status)
    except ValueError:
        # Wenn der Status nicht in der Liste ist, gib ihm einen hohen Wert,
        # damit er am Ende sortiert wird.
        return len(CUSTOM_STATUS_ORDER)

# Die Sortierung verwendet nun die Hilfsfunktion für den Status.
business_epics_list.sort(key=lambda epic: (
    get_status_sort_key(epic),
    (epic.get('fix_versions') or [''])[0]
))

end_time = time.time()
duration = end_time - start_time

# --- Ausgabe ---
print("-" * 50)
print(f"Analyse abgeschlossen.")
print(f"Dauer des Aufbaus und der Sortierung: {duration:.4f} Sekunden")
print(f"Anzahl gefundener Business Epics (gefiltert): {len(business_epics_list)}")
print("-" * 50)

if not business_epics_list:
    print("Keine passenden Business Epics gefunden.")
else:
    # Ausgabestruktur (unverändert)
    current_status = None
    current_fix_version = None

    for epic in business_epics_list:
        status = epic.get('status') or 'Kein Status'
        fix_version = (epic.get('fix_versions') or ['Keine'])[0]

        if status != current_status:
            current_status = status
            print(f"\n--- Status: {current_status} ---")
            current_fix_version = None

        if fix_version != current_fix_version:
            current_fix_version = fix_version
            print(f"    --- Fix Version: {current_fix_version}")

        print(f"        - {epic['key']}")
