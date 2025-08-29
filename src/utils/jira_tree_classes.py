# src/utils/jira_tree_classes.py
"""
Module for creating, visualizing, and processing JIRA issue relationship trees.

This module provides the functionality to create JIRA issue trees based on a
flexibly configurable hierarchy of issue links, to visualize them graphically,
and to generate structured context summaries for further processing.
"""

import json
import os
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
import glob
from collections import defaultdict
import matplotlib.patches as mpatches
from src.utils.logger_config import logger
from src.utils.config import (
    JIRA_ISSUES_DIR,
    ISSUE_TREES_DIR,
    JSON_SUMMARY_DIR,
    LOGS_DIR,
    JIRA_TREE_MANAGEMENT,
    ISSUE_LOG_FILE
)


class JiraTreeGenerator:
    """
    Creates a graph of JIRA issues based on a flexible hierarchy.

    This class searches JSON files of JIRA issues and builds a directed
    graph (a tree) representing the relationships between the issues. The type
    of relationships to follow is flexibly configurable.
    """
    def __init__(self, json_dir=JIRA_ISSUES_DIR, allowed_types=None, verbose=False):
        """
        Initializes the JiraTreeGenerator.

        This class can be configured to use different hierarchy types.
        If no configuration (`allowed_types`) is passed, it falls back
        to the default configuration `JIRA_TREE_MANAGEMENT`.

        Args:
            json_dir (str): The directory containing the JIRA issue JSON files.
            allowed_types (dict, optional): A dictionary that maps an issue type (str) to a
                                            list of allowed relationship types (str).
                                            E.g., {'Epic': ['realized_by'], ...}.
                                            If None, the default from the config is used.
            verbose (bool): If True, enables detailed print statements for debugging.
        """
        self.json_dir = json_dir
        self.allowed_hierarchy_types = allowed_types if allowed_types is not None else JIRA_TREE_MANAGEMENT
        self.verbose = verbose

    def _log_missing_issue(self, issue_key: str):
        """
        Logs a missing issue key in the central log file.
        Prevents duplicate entries to keep the file clean.
        """
        try:
            existing_keys = set()
            if os.path.exists(ISSUE_LOG_FILE):
                with open(ISSUE_LOG_FILE, 'r', encoding='utf-8') as f:
                    existing_keys = {line.strip() for line in f}

            if issue_key not in existing_keys:
                with open(ISSUE_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{issue_key}\n")
                logger.info(f"Missing key '{issue_key}' was added for tracking in {ISSUE_LOG_FILE}.")
        except Exception as e:
            logger.error(f"Error writing missing key '{issue_key}' to the log file: {e}")


    def read_jira_issue(self, file_path):
        """
        Reads a JIRA issue from a JSON file.

        Args:
            file_path (str): The path to the JSON file.

        Returns:
            dict or None: A dictionary with the issue data or None in case of an error.
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
        Finds the corresponding JSON file for a given JIRA key.
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
        Builds a directed graph based on a flexible hierarchy configuration.
        """
        if self.verbose:
            print("\n" + "="*50)
            print(f"🌲 START: Building Tree for Root: {root_key}")
            print(f"CONFIG: {self.allowed_hierarchy_types}")
            print("="*50)

        G = nx.DiGraph()
        file_path = self.find_json_for_key(root_key)
        if not file_path:
            logger.error(f"Error: No JSON file found for root key {root_key}")
            self._log_missing_issue(root_key)
            return None

        root_data = self.read_jira_issue(file_path)
        if not root_data:
            logger.error(f"Error: The JSON file for root key {root_key} could not be read")
            return None

        root_issue_type = root_data.get('issue_type', '')
        if not root_issue_type:
            logger.error(f"Error: Root issue {root_key} has an empty 'issue_type'.")
            return None

        if root_issue_type not in self.allowed_hierarchy_types:
            logger.error(f"Error: Root issue {root_key} is of type '{root_issue_type}', which is not a valid starting point.")
            return None

        resolutions_to_skip = ['Rejected', 'Withdrawn']
        root_resolution = root_data.get('resolution')
        if not include_rejected and root_resolution in resolutions_to_skip:
            logger.error(f"Error: Root issue {root_key} has resolution '{root_resolution}' and will not be processed.")
            return None

        G.add_node(root_key, **root_data)
        visited = set()

        def _add_children(parent_key):
            """Recursive helper function that generically searches for children."""
            if parent_key in visited:
                return
            visited.add(parent_key)

            parent_data = G.nodes[parent_key]
            parent_issue_type = parent_data.get('issue_type', '')
            
            if self.verbose:
                print(f"\n🔎 Processing Parent: {parent_key} (Type: {parent_issue_type})")

            allowed_relations = self.allowed_hierarchy_types.get(parent_issue_type, [])

            if not allowed_relations:
                if self.verbose:
                    print(f"  -> ⚠️ No relations configured for type '{parent_issue_type}'. Stopping this branch.")
                return
            if 'issue_links' not in parent_data:
                if self.verbose:
                    print("  -> ⚠️ Parent has no 'issue_links' field. Stopping this branch.")
                return

            if self.verbose:
                print(f"  -> Allowed Relations for '{parent_issue_type}': {allowed_relations}")

            for link in parent_data['issue_links']:
                relation_type = link.get('relation_type')
                child_key = link.get('key')
                
                if not child_key or not relation_type:
                    continue

                if self.verbose:
                    print(f"  - Found link: {parent_key} -> '{relation_type}' -> {child_key}", end="")

                if relation_type in allowed_relations:
                    if self.verbose:
                        print(" ... ✅ MATCH")

                    child_file_path = self.find_json_for_key(child_key)
                    if not child_file_path:
                        logger.warning(f"Skipping child {child_key}: JSON file not found.")
                        self._log_missing_issue(child_key)
                        continue

                    child_data = self.read_jira_issue(child_file_path)
                    if not child_data:
                        logger.warning(f"Skipping child {child_key}: JSON file could not be read.")
                        continue

                    child_resolution = child_data.get('resolution')
                    if not include_rejected and child_resolution in resolutions_to_skip:
                        logger.info(f"Skipping child {child_key} because its resolution is '{child_resolution}'.")
                        continue

                    G.add_node(child_key, **child_data)
                    G.add_edge(parent_key, child_key)
                    _add_children(child_key)
                else:
                    if self.verbose:
                        print(" ... ❌ NO MATCH")

        _add_children(root_key)

        if G.number_of_nodes() <= 1 and not root_data.get('issue_links'):
            logger.info(f"Warning: The root issue {root_key} has no 'issue_links' entries")

        logger.info(f"Tree built. Number of nodes: {G.number_of_nodes()}")
        if self.verbose:
            print("="*50)
            print(f"🌲 END: Tree building complete. Total nodes: {G.number_of_nodes()}")
            print("="*50 + "\n")
        return G

class JiraTreeVisualizer:
    """
    Class for visualizing a JIRA issue tree graph.
    """
    def __init__(self, output_dir=ISSUE_TREES_DIR, format='png'):
        self.output_dir = output_dir
        self.format = format
        self.status_colors = {'Funnel': 'lightgray', 'Backlog for Analysis': 'lightgray', 'Analysis': 'lemonchiffon', 'Backlog': 'lemonchiffon', 'Review': 'lemonchiffon', 'Waiting': 'lightblue', 'In Progress': 'lightgreen', 'Deployment': 'lightgreen', 'Validation': 'lightgreen', 'Resolved': 'green', 'Closed': 'green'}

    def _determine_node_size_and_font(self, G):
        if G.number_of_nodes() > 20: return 2000, 8, (20, 12)
        elif G.number_of_nodes() > 10: return 3000, 8, (16, 12)
        else: return 4000, 9, (12, 12)

    def visualize(self, G, root_key, output_file=None):
        """
        Creates and saves a visualization of the graph.
        """
        if G is None or not isinstance(G, nx.DiGraph) or G.number_of_nodes() <= 1:
            if G is None or not isinstance(G, nx.DiGraph): logger.error("Error: Invalid graph provided.")
            else: logger.info(f"Warning: The graph contains only the root node {root_key}.")
            return False

        if output_file is None:
            os.makedirs(self.output_dir, exist_ok=True)
            output_file = os.path.join(self.output_dir, f"{root_key}_issue_tree.{self.format}")

        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
        except ImportError:
            logger.warning("pygraphviz not found. Falling back to a simpler graph layout.")
            pos = nx.spring_layout(G)

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
    Creates structured context data from JIRA issue trees for AI processing.
    """
    def __init__(self, output_dir=JSON_SUMMARY_DIR):
        self.output_dir = output_dir

    def generate_context(self, G, root_key, output_file=None):
        """
        Generates a JSON-formatted string and saves it to a file.
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

            for field in ['assignee', 'priority', 'target_start', 'target_end', 'description']:
                if value := node_attrs.get(field): issue_data[field] = value

            if fix_versions := node_attrs.get('fix_versions'):
                issue_data["fix_versions"] = fix_versions if isinstance(fix_versions, list) else str(fix_versions).split(', ')

            if business_value := node_attrs.get('business_value', {}):
                issue_data["business_value"] = business_value

            if acceptance_criteria := node_attrs.get('acceptance_criteria', []):
                issue_data["acceptance_criteria"] = acceptance_criteria if isinstance(acceptance_criteria, list) else [acceptance_criteria]

            if realized_by_keys := list(G.successors(node)):
                issue_data["realized_by"] = [{"key": child_key, "title": G.nodes[child_key].get('title', 'No title')} for child_key in realized_by_keys]

            if predecessors := list(G.predecessors(node)):
                issue_data["realizes"] = [{"key": parent, "title": G.nodes[parent].get('title', 'No title')} for parent in predecessors]

            issues_data.append(issue_data)

        context_json = {"root": root_key, "issues": issues_data}
        json_str = json.dumps(context_json, indent=2, ensure_ascii=False)

        return json_str
