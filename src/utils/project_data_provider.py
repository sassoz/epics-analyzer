# src/utils/project_data_provider.py
import json
import os
import networkx as nx
from utils.logger_config import logger
from utils.jira_tree_classes import JiraTreeGenerator
from utils.config import JIRA_ISSUES_DIR, JSON_SUMMARY_DIR # Import JSON_SUMMARY_DIR

class ProjectDataProvider:
    """
    Lädt, verarbeitet und stellt alle notwendigen Projektdaten für Analysen bereit.
    Diese Klasse dient als zentraler und effizienter Daten-Hub.
    """
    def __init__(self, epic_id: str, json_dir: str = JIRA_ISSUES_DIR, hierarchy_config: dict = None, verbose: bool = False):
        self.epic_id = epic_id
        self.json_dir = json_dir
        self.config = {"jira_issue_relation_map": hierarchy_config}
        self.root_node = None

        # Initiale Datenstrukturen, die vom TreeGenerator erwartet werden
        self.issue_tree = nx.DiGraph()
        self.issue_details = self._build_issue_details_cache()

        # Der Generator wird jetzt mit der übergebenen Konfiguration initialisiert
        self.tree_generator = JiraTreeGenerator(allowed_types=hierarchy_config, verbose=verbose)

        # Baue den Issue-Baum mit dem neuen Generator
        self.tree_generator.build_tree_for_root(self.epic_id, self)

        self.all_activities = self._gather_all_activities()

        if self.all_activities:
            self.all_activities.sort(key=lambda x: x.get('zeitstempel_iso', ''))

        if self.issue_tree:
            logger.info(f"ProjectDataProvider für Epic '{epic_id}' mit {len(self.issue_tree.nodes())} Issues initialisiert.")
        else:
            logger.warning(f"ProjectDataProvider für Epic '{epic_id}' konnte keinen gültigen Issue-Baum erstellen.")

    def find_and_set_root_node(self):
        """
        Finds and sets the root node of the issue tree.
        The root is the node with an in-degree of 0.
        """
        if not self.issue_tree:
            self.root_node = None
            return

        for node in self.issue_tree.nodes():
            if self.issue_tree.in_degree(node) == 0:
                self.root_node = node
                logger.info(f"Root node identified and set to: {self.root_node}")
                return

        # Fallback or warning if no root is found
        logger.warning("No root node with in-degree 0 found in the issue tree.")
        self.root_node = self.epic_id # As a fallback

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
        # Temporarily get all json files in the json_dir to build a complete cache
        all_json_files = [f for f in os.listdir(self.json_dir) if f.endswith('.json')]
        for file_name in all_json_files:
            issue_key = file_name.replace('.json', '')
            file_path = os.path.join(self.json_dir, file_name)
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
                        'fix_versions': data.get('fix_versions'),
                        'links': data.get('links', []),
                        'issues_in_epic': data.get('issues_in_epic', [])
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
