import os
import json
import re

def get_last_activity_value(activities, field_name):
    """
    Sucht den letzten Wert für ein bestimmtes Feld in den Aktivitäten.
    """
    for activity in reversed(activities):
        if activity.get("feld_name") == field_name:
            raw_value = activity.get("neuer_wert", "")

            # Verarbeitet Werte wie "New:Value[...]" oder "Value"
            if ':' in raw_value:
                value = raw_value.split(':', 1)[1]
                value = value.split('[')[0].strip()
                if value:
                    return value
            elif raw_value:
                 return raw_value.split('[')[0].strip()

    return "n/a"  # Standardwert, wenn nichts gefunden wird

def create_story_overview(directory_path):
    """
    Erstellt eine Liste von Storys aus JSON-Dateien in einem Verzeichnis.
    """
    stories_list = []

    if not os.path.isdir(directory_path):
        print(f"Fehler: Verzeichnis '{directory_path}' nicht gefunden.")
        return []

    for filename in os.listdir(directory_path):
        if filename.endswith(".json"):
            file_path = os.path.join(directory_path, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    if data.get("issue_type") == "Story":
                        activities = data.get("activities", [])
                        story_info = {
                            "key": data.get("key", "N/A"),
                            "status": data.get("status", "N/A"),
                            "resolution": get_last_activity_value(activities, "Resolution"),
                            "story_points": get_last_activity_value(activities, "Story Points")
                        }
                        stories_list.append(story_info)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Fehler beim Lesen der Datei {filename}: {e}")

    return stories_list

def filter_stories_for_keys(stories):
    """
    Filtert die Story-Liste nach den angegebenen Kriterien und gibt nur die Keys zurück.
    """
    filtered_keys = []
    for story in stories:
        # Filterkriterien anwenden
        status_ok = story['status'].lower() in ['resolved', 'done', 'closed']
        resolution_ok = story['resolution'] == 'Done'
        story_points_ok = story['story_points'] == 'n/a'

        if status_ok and resolution_ok and story_points_ok:
            filtered_keys.append(story['key'])

    return filtered_keys

# --- Hauptteil des Skripts ---
if __name__ == "__main__":
    # Pfad zum Verzeichnis, relativ zum Skriptstandort
    JIRA_ISSUES_DIR = os.path.join('data', 'jira_issues')

    # 1. Alle Story-Daten sammeln
    all_stories = create_story_overview(JIRA_ISSUES_DIR)

    # 2. Die gesammelten Daten filtern
    keys_to_review = filter_stories_for_keys(all_stories)

    # 3. NEUER FILTER: Nur Keys mit bestimmten Kennungen behalten
    final_keys = []
    project_identifiers = ['SECEIT', 'ADCL', 'MAGBUS']
    for key in keys_to_review:
        if any(identifier in key for identifier in project_identifiers):
            final_keys.append(key)

    # 4. Das endgültige Ergebnis ausgeben
    print("Folgende Keys entsprechen ALLEN Filterkriterien:")
    print("-------------------------------------------------")
    if final_keys:
        for key in final_keys:
            print(key)
    else:
        print("Keine Keys gefunden, die allen Kriterien entsprechen.")
