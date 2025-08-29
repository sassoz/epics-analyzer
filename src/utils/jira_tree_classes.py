# src/utils/jira_tree_classes.py
# src/utils/jira_tree_classes.py
"""
Modul zum Erstellen, Visualisieren und Verarbeiten von JIRA-Issue-Beziehungsbäumen.

Dieses Modul bietet die Funktionalität, JIRA-Issue-Bäume basierend auf einer
flexibel konfigurierbaren Hierarchie von Issue-Verknüpfungen zu erstellen,
diese grafisch darzustellen und strukturierte Kontext-Zusammenfassungen für
die Weiterverarbeitung zu generieren.
"""

import json
import os
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
import glob
from collections import defaultdict
import matplotlib.patches as mpatches
from utils.logger_config import logger
from utils.config import (
    JIRA_ISSUES_DIR,
    ISSUE_TREES_DIR,
    JSON_SUMMARY_DIR,
    LOGS_DIR,
    JIRA_TREE_MANAGEMENT,
    ISSUE_LOG_FILE # <-- NEUER IMPORT
)


class JiraTreeGenerator:
    """
    Erstellt einen Graphen von JIRA-Issues basierend auf einer flexiblen Hierarchie.

    Diese Klasse durchsucht JSON-Dateien von JIRA-Issues und baut einen gerichteten
    Graphen (einen Baum), der die Beziehungen zwischen den Issues darstellt. Die Art
    der zu verfolgenden Beziehungen ist flexibel konfigurierbar.
    """
    def __init__(self, json_dir=JIRA_ISSUES_DIR, allowed_types=None):
        """
        Initialisiert den JiraTreeGenerator.

        Diese Klasse kann so konfiguriert werden, dass sie verschiedene Hierarchie-Typen
        verwendet. Wenn keine Konfiguration (`allowed_types`) übergeben wird, greift sie
        auf die Standardkonfiguration `JIRA_TREE_MANAGEMENT` zurück.

        Args:
            json_dir (str): Das Verzeichnis, das die JIRA-Issue-JSON-Dateien enthält.
            allowed_types (dict, optional): Ein Dictionary, das einem Issue-Typ (str) eine
                                            Liste von erlaubten Beziehungs-Typen (str)
                                            zuordnet. Z.B. {'Epic': ['realized_by'], ...}.
                                            Wenn None, wird der Standard aus der config verwendet.
        """
        self.json_dir = json_dir
        # Verwende die übergebene Konfiguration, oder greife auf den Standard zurück
        self.allowed_hierarchy_types = allowed_types if allowed_types is not None else JIRA_TREE_MANAGEMENT

    # +++ NEUE METHODE zum Protokollieren fehlender Issues +++
    def _log_missing_issue(self, issue_key: str):
        """
        Protokolliert einen fehlenden Issue-Key in der zentralen Log-Datei.
        Verhindert doppelte Einträge, um die Datei sauber zu halten.
        """
        try:
            existing_keys = set()
            # Prüfen, ob die Log-Datei bereits existiert und Einträge hat
            if os.path.exists(ISSUE_LOG_FILE):
                with open(ISSUE_LOG_FILE, 'r', encoding='utf-8') as f:
                    existing_keys = {line.strip() for line in f}

            # Nur schreiben, wenn der Key noch nicht in der Datei ist
            if issue_key not in existing_keys:
                with open(ISSUE_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{issue_key}\n")
                logger.info(f"Fehlender Key '{issue_key}' wurde zur Nachverfolgung in {ISSUE_LOG_FILE} hinzugefügt.")
        except Exception as e:
            logger.error(f"Fehler beim Schreiben des fehlenden Keys '{issue_key}' in die Log-Datei: {e}")


    def read_jira_issue(self, file_path):
        """
        Liest einen JIRA-Issue aus einer JSON-Datei.

        Args:
            file_path (str): Der Pfad zur JSON-Datei.

        Returns:
            dict or None: Ein Dictionary mit den Issue-Daten oder None bei einem Fehler.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            logger.error(f"Warning: File {file_path} not found")
            return None
        except json.JSONDecodeError:
            logger.error(f"Error: File {file_path} contains invalid JSON")
            return None

    def find_json_for_key(self, key):
        """
        Findet die passende JSON-Datei für einen bestimmten JIRA-Key.

        Durchsucht das angegebene Verzeichnis nach einer Datei, die dem Key entspricht.
        Prüft zuerst auf einen exakten Dateinamen-Match (z.B. 'PROJ-123.json') und
        durchsucht andernfalls den Inhalt der Dateien.

        Args:
            key (str): Der JIRA-Key (z.B. "PROJ-123").

        Returns:
            str or None: Der Dateipfad zur gefundenen JSON-Datei oder None, wenn nichts
                         gefunden wurde.
        """
        exact_path = os.path.join(self.json_dir, f"{key}.json")
        if os.path.exists(exact_path):
            return exact_path
        json_files = glob.glob(os.path.join(self.json_dir, "*.json"))
        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if data.get("key") == key:
                        return file_path
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        return None

    def build_issue_tree(self, root_key, include_rejected=False):
        """
        Baut einen gerichteten Graphen basierend auf einer flexiblen Hierarchie-Konfiguration.

        Beginnend mit einem Wurzel-Issue wird der Baum rekursiv aufgebaut, indem die
        Verknüpfungen (`issue_links`) verfolgt werden. Welche Verknüpfungen berücksichtigt
        werden, hängt von der Konfiguration (`self.allowed_hierarchy_types`) ab, die den
        Eltern-Issue-Typ auf eine Liste gültiger Beziehungs-Typen abbildet.

        Args:
            root_key (str): Der Schlüssel des Wurzel-Issues (z.B. "PROJ-1").
            include_rejected (bool, optional): Wenn False, werden Issues mit der Resolution
                                               'Rejected' oder 'Withdrawn' (und deren
                                               gesamte untergeordnete Zweige) ausgeschlossen.
                                               Standard ist False.

        Returns:
            nx.DiGraph or None: Ein gerichteter Graph, der die gefilterte Baumstruktur
                                darstellt, oder None, wenn ein Fehler auftritt (z.B.
                                Wurzel-Issue nicht gefunden).
        """
        logger.info(f"Building issue tree for root issue: {root_key}")
        G = nx.DiGraph()
        file_path = self.find_json_for_key(root_key)
        if not file_path:
            logger.error(f"Error: No JSON file found for root key {root_key}")
            self._log_missing_issue(root_key) # Auch der Root-Key könnte fehlen
            return None

        root_data = self.read_jira_issue(file_path)
        if not root_data:
            logger.error(f"Error: The JSON file for root key {root_key} could not be read")
            return None

        root_issue_type = root_data.get('issue_type', '')
        if root_issue_type not in self.allowed_hierarchy_types:
            logger.error(f"Error: Root issue {root_key} is of type '{root_issue_type}', "
                         f"which is not a valid starting point in the hierarchy configuration.")
            return None

        # Prüft auf eine Liste von auszuschließenden Resolution-Typen
        resolutions_to_skip = ['Rejected', 'Withdrawn']
        root_resolution = root_data.get('resolution')
        if not include_rejected and root_resolution in resolutions_to_skip:
            logger.error(f"Error: Root issue {root_key} has resolution '{root_resolution}' and will not be processed.")
            return None

        G.add_node(root_key, **root_data)
        visited = set()

        def _add_children(parent_key):
            """Rekursive Hilfsfunktion, die generisch nach Kindern sucht."""
            if parent_key in visited:
                return
            visited.add(parent_key)

            parent_data = G.nodes[parent_key]
            parent_issue_type = parent_data.get('issue_type', '')

            allowed_relations = self.allowed_hierarchy_types.get(parent_issue_type, [])

            if not allowed_relations or 'issue_links' not in parent_data:
                return

            for link in parent_data['issue_links']:
                relation_type = link.get('relation_type')

                if relation_type in allowed_relations:
                    child_key = link.get('key')
                    if not child_key:
                        continue

                    child_file_path = self.find_json_for_key(child_key)
                    if not child_file_path:
                        logger.warning(f"Skipping child {child_key}: JSON file not found.")
                        self._log_missing_issue(child_key) # <-- HIER WIRD DIE NEUE METHODE AUFGERUFEN
                        continue

                    child_data = self.read_jira_issue(child_file_path)
                    if not child_data:
                        logger.warning(f"Skipping child {child_key}: JSON file could not be read.")
                        continue

                    # Prüft auf eine Liste von auszuschließenden Resolution-Typen
                    child_resolution = child_data.get('resolution')
                    if not include_rejected and child_resolution in resolutions_to_skip:
                        logger.info(f"Skipping child {child_key} because its resolution is '{child_resolution}'.")
                        continue

                    G.add_node(child_key, **child_data)
                    G.add_edge(parent_key, child_key)
                    _add_children(child_key)

        _add_children(root_key)

        if G.number_of_nodes() <= 1 and not root_data.get('issue_links'):
            logger.info(f"Warning: The root issue {root_key} has no 'issue_links' entries")

        logger.info(f"Tree built. Number of nodes: {G.number_of_nodes()}")
        return G

class JiraTreeVisualizer:
    """
    Klasse zur Visualisierung eines JIRA-Issue-Baum-Graphen.

    Nimmt einen `networkx.DiGraph` entgegen und erstellt eine grafische Darstellung,
    die als Bilddatei gespeichert wird. Die Knoten werden nach ihrem Status eingefärbt.
    """
    def __init__(self, output_dir=ISSUE_TREES_DIR, format='png'):
        """
        Initialisiert den Visualizer.

        Args:
            output_dir (str): Das Verzeichnis zum Speichern der erstellten Bilder.
            format (str): Das Dateiformat für die Ausgabe (z.B. 'png', 'svg').
        """
        self.output_dir = output_dir
        self.format = format
        self.status_colors = {'Funnel': 'lightgray', 'Backlog for Analysis': 'lightgray', 'Analysis': 'lemonchiffon', 'Backlog': 'lemonchiffon', 'Review': 'lemonchiffon', 'Waiting': 'lightblue', 'In Progress': 'lightgreen', 'Deployment': 'lightgreen', 'Validation': 'lightgreen', 'Resolved': 'green', 'Closed': 'green'}

    def _determine_node_size_and_font(self, G):
        """Bestimmt dynamisch die Größe der Knoten und Schrift basierend auf der Knotenanzahl."""
        if G.number_of_nodes() > 20: return 2000, 8, (20, 12)
        elif G.number_of_nodes() > 10: return 3000, 8, (16, 12)
        else: return 4000, 9, (12, 12)

    def visualize(self, G, root_key, output_file=None):
        """
        Erstellt und speichert eine Visualisierung des Graphen.

        Der Graph wird mit einem hierarchischen Layout (dot) dargestellt. Die Knoten-
        beschriftungen enthalten den Key und die Fix-Version(en). Eine Legende erklärt
        die Farbkodierung der Status.

        Args:
            G (nx.DiGraph): Der zu visualisierende Graph.
            root_key (str): Der Schlüssel des Wurzel-Issues, wird für den Dateinamen
                            und Titel verwendet.
            output_file (str, optional): Der vollständige Pfad zur Ausgabedatei.
                                         Wenn nicht angegeben, wird ein Standardname
                                         im `output_dir` generiert.

        Returns:
            bool: True, wenn die Visualisierung erfolgreich gespeichert wurde, sonst False.
        """
        if G is None or not isinstance(G, nx.DiGraph) or G.number_of_nodes() <= 1:
            if G is None or not isinstance(G, nx.DiGraph): logger.error("Error: Invalid graph provided.")
            else: logger.info(f"Warning: The graph contains only the root node {root_key}.")
            return False

        if output_file is None:
            os.makedirs(self.output_dir, exist_ok=True)
            output_file = os.path.join(self.output_dir, f"{root_key}_issue_tree.{self.format}")

        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
        NODE_SIZE, FONT_SIZE, figure_size = self._determine_node_size_and_font(G)
        plt.figure(figsize=figure_size)

        nodes_by_status = defaultdict(list)
        for node, attrs in G.nodes(data=True):
            nodes_by_status[attrs.get('status', '')].append(node)

        for status, nodes in nodes_by_status.items():
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_size=NODE_SIZE, node_color=self.status_colors.get(status, 'peachpuff'), alpha=0.8)

        labels = {}
        for node, attrs in G.nodes(data=True):
            fix_versions = attrs.get('fix_versions', [])
            fix_versions_string = "\n".join(fix_versions) if isinstance(fix_versions, list) else str(fix_versions)
            labels[node] = f"{node.split('-')[0]}-\n{node.split('-')[1]}\n{fix_versions_string}"

        nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5, arrows=True, arrowstyle='->', arrowsize=15)
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=FONT_SIZE, font_family='sans-serif', verticalalignment='center')

        legend_patches = [mpatches.Patch(color=color, label=status) for status, color in self.status_colors.items() if status and any(node for node in nodes_by_status.get(status, []))]
        plt.legend(handles=legend_patches, loc='upper right', title='Status')

        title = G.nodes[list(G.nodes())[0]].get("title", '')
        plt.title(f"{root_key} Jira Hierarchy\n{title}", fontsize=16)
        plt.axis('off')

        try:
            plt.tight_layout()
            plt.savefig(output_file, dpi=100, bbox_inches='tight')
            plt.close()
            logger.info(f"Issue Tree saved: {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving visualization: {e}")
            return False


class JiraContextGenerator:
    """
    Erstellt strukturierte Kontextdaten aus JIRA-Issue-Bäumen für die KI-Verarbeitung.

    Diese Klasse wandelt einen `networkx.DiGraph` in ein strukturiertes JSON-Format um.
    Das JSON enthält eine Liste aller Issues im Baum (in BFS-Reihenfolge), angereichert
    mit wichtigen Feldern und Beziehungs-Informationen (Eltern/Kinder).
    """
    def __init__(self, output_dir=JSON_SUMMARY_DIR):
        """
        Initialisiert den Kontext-Generator.

        Args:
            output_dir (str): Das Verzeichnis zum Speichern der erstellten
                              JSON-Zusammenfassungen. (Hinweis: Aktuell wird die
                              Ausgabe in LOGS_DIR gespeichert, nicht hier.)
        """
        self.output_dir = output_dir

    def generate_context(self, G, root_key, output_file=None):
        """
        Generiert eine JSON-formatierte Zeichenkette und speichert sie in einer Datei.

        Durchläuft den Graphen in einer Breadth-First-Search (BFS)-Reihenfolge,
        beginnend beim `root_key`. Für jeden Knoten werden relevante Attribute extrahiert
        und in eine strukturierte Form gebracht.

        Args:
            G (nx.DiGraph): Der Graph, aus dem der Kontext generiert werden soll.
            root_key (str): Der Schlüssel des Wurzel-Issues.
            output_file (str, optional): Der Pfad zur Speicherdatei. Wenn nicht angegeben,
                                         wird ein Standardpfad im LOGS_DIR verwendet.

        Returns:
            str: Eine JSON-formatierte Zeichenkette, die den Kontext darstellt.
                 Gibt bei einem Fehler einen leeren JSON-String "{}" zurück.
        """
        if G is None or not isinstance(G, nx.DiGraph):
            logger.error("Error: Invalid graph provided.")
            return "{}"
        if root_key not in G:
            logger.error(f"Error: Root node {root_key} not found in the graph.")
            return "{}"

        issues_data = []
        for node in nx.bfs_tree(G, source=root_key):
            node_attrs = G.nodes[node]
            issue_data = {"key": node, "title": node_attrs.get('title', 'No title'), "issue_type": node_attrs.get('issue_type', 'Unknown'), "status": node_attrs.get('status', 'Unknown')}

            # Optionale Felder hinzufügen
            for field in ['assignee', 'priority', 'target_start', 'target_end', 'description']:
                if value := node_attrs.get(field): issue_data[field] = value

            if fix_versions := node_attrs.get('fix_versions'):
                issue_data["fix_versions"] = fix_versions if isinstance(fix_versions, list) else str(fix_versions).split(', ')

            if business_value := node_attrs.get('business_value', {}):
                issue_data["business_value"] = business_value

            if acceptance_criteria := node_attrs.get('acceptance_criteria', []):
                issue_data["acceptance_criteria"] = acceptance_criteria if isinstance(acceptance_criteria, list) else [acceptance_criteria]

            # Verwendet die im Graphen vorhandenen Kanten, um realisierte Kinder zu finden
            if realized_by_keys := list(G.successors(node)):
                issue_data["realized_by"] = [{"key": child_key, "title": G.nodes[child_key].get('title', 'No title')} for child_key in realized_by_keys]

            # Verwendet die im Graphen vorhandenen Kanten, um realisierte Eltern zu finden
            if predecessors := list(G.predecessors(node)):
                issue_data["realizes"] = [{"key": parent, "title": G.nodes[parent].get('title', 'No title')} for parent in predecessors]

            issues_data.append(issue_data)

        context_json = {"root": root_key, "issues": issues_data}
        json_str = json.dumps(context_json, indent=2, ensure_ascii=False)

        # Logik zur Dateispeicherung
        # Hinweis: Das `output_file` Argument überschreibt den Standardpfad.
        #if output_file is None:
        #    context_file = os.path.join(LOGS_DIR, f"{root_key}_context.json")
        #else:
        #    context_file = output_file
        #    os.makedirs(os.path.dirname(context_file), exist_ok=True)
#
#        with open(context_file, 'w', encoding='utf-8') as file:
#            file.write(json_str)
#            logger.info(f"Context saved to file: {context_file}")
#
        return json_str
