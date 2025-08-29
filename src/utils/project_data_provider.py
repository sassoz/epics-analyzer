# src/utils/project_data_provider.py
import json
import os
import sys
from utils.logger_config import logger
from utils.jira_tree_classes import JiraTreeGenerator
from utils.config import JIRA_ISSUES_DIR, JSON_SUMMARY_DIR # Import JSON_SUMMARY_DIR

class ProjectDataProvider:
    """
    Lädt, verarbeitet und stellt alle notwendigen Projektdaten für Analysen bereit.
    Diese Klasse dient als zentraler und effizienter Daten-Hub.
    """
    def __init__(self, epic_id: str, json_dir: str = JIRA_ISSUES_DIR, hierarchy_config: dict = None):
        self.epic_id = epic_id
        self.json_dir = json_dir
        # Der Generator wird jetzt mit der übergebenen Konfiguration initialisiert
        self.tree_generator = JiraTreeGenerator(json_dir=self.json_dir, allowed_types=hierarchy_config)

        # Lade alle Kerndaten
        self.issue_tree = self.tree_generator.build_issue_tree(self.epic_id, include_rejected=False)
        self.all_activities = self._gather_all_activities()
        self.issue_details = self._build_issue_details_cache()

        if self.all_activities:
            self.all_activities.sort(key=lambda x: x.get('zeitstempel_iso', ''))

        if self.issue_tree:
            logger.info(f"ProjectDataProvider für Epic '{epic_id}' mit {len(self.issue_tree.nodes())} Issues initialisiert.")
        else:
            logger.warning(f"ProjectDataProvider für Epic '{epic_id}' konnte keinen gültigen Issue-Baum erstellen.")

    def is_valid(self) -> bool:
        """Prüft, ob die grundlegenden Daten geladen werden konnten."""
        return self.issue_tree is not None and len(self.issue_tree.nodes()) > 0

    def _gather_all_activities(self) -> list:
        """Sammelt die Aktivitäten aller Issues im Baum."""
        all_activities = []
        if not self.issue_tree: return []
        for issue_key in self.issue_tree.nodes():
            file_path = os.path.join(self.json_dir, f"{issue_key}.json")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    issue_data = json.load(f)
                    activities = issue_data.get('activities', [])
                    for activity in activities:
                        activity['issue_key'] = issue_key
                    all_activities.extend(activities)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning(f"Datei für Issue '{issue_key}' nicht gefunden oder fehlerhaft: {e}")
                continue
        return all_activities

    def _build_issue_details_cache(self) -> dict:
        """Erstellt einen zentralen Cache mit aufbereiteten Details zu jedem Issue."""
        cache = {}
        if not self.issue_tree: return {}
        for issue_key in self.issue_tree.nodes():
            file_path = os.path.join(self.json_dir, f"{issue_key}.json")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    points = 0
                    story_points_value = data.get('story_points')
                    if story_points_value is not None:
                        try:
                            points = int(story_points_value)
                        except (ValueError, TypeError):
                            points = 0

                    cache[issue_key] = {
                        'type': data.get('issue_type'),
                        'title': data.get('title'),
                        'status': data.get('status'),
                        'resolution': data.get('resolution'),
                        'points': points,
                        'target_start': data.get('target_start'),
                        'target_end': data.get('target_end'),
                        'fix_versions': data.get('fix_versions')
                    }
            except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Konnte Details für Issue '{issue_key}' nicht laden: {e}")
                continue
        return cache

    def get_epic_json_summary(self, epic_id: str) -> dict | None:
        """Loads the JSON summary for a given epic ID from the JSON_SUMMARY_DIR."""
        file_path = os.path.join(JSON_SUMMARY_DIR, f"{epic_id}_json_summary.json")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"JSON summary file not found for {epic_id}: {file_path}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON summary for {epic_id}: {file_path}")
            return None
