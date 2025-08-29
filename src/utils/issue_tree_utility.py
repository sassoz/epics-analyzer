# src/utils/issue_tree_utility.py

import os
import sys
import json
import argparse

# Add project root to path to allow imports from other directories
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.jira_tree_classes import JiraTreeGenerator, JiraContextGenerator
from src.utils.config import JIRA_TREE_FULL, JIRA_ISSUES_DIR
from src.utils.logger_config import logger

def get_issue_hierarchy_as_dict(start_issue_key: str) -> dict:
    """
    Builds a hierarchical dictionary representing the issue tree for a given starting issue.

    This function leverages the existing JiraTreeGenerator to build a graph representation
    of the issue hierarchy and then uses JiraContextGenerator to convert that graph
    into a nested dictionary (JSON-like) format.

    Args:
        start_issue_key: The JIRA key of the root issue (e.g., 'BEMABU-12345').

    Returns:
        A nested dictionary representing the issue hierarchy, or an error dictionary
        if the tree cannot be built.
    """
    logger.info(f"Attempting to build issue hierarchy for '{start_issue_key}'...")

    # Check if the root issue JSON file exists, as it's required by the generators.
    root_issue_file = os.path.join(JIRA_ISSUES_DIR, f"{start_issue_key}.json")
    if not os.path.exists(root_issue_file):
        logger.error(f"Root issue file not found: {root_issue_file}")
        return {
            "error": "The root issue data file does not exist.",
            "message": f"Please run the scraper first for issue '{start_issue_key}' to fetch its data."
        }

    # 1. Use JiraTreeGenerator to build the graph from the locally stored JSON files.
    #    We use JIRA_TREE_FULL to get the most comprehensive hierarchy possible.
    tree_generator = JiraTreeGenerator(allowed_types=JIRA_TREE_FULL)
    issue_graph = tree_generator.build_issue_tree(start_issue_key)

    if not issue_graph or start_issue_key not in issue_graph:
        logger.warning(f"Could not build a graph for '{start_issue_key}'. The issue might be a standalone ticket with no recognized links, or its data is missing.")
        return {
            "warning": "Could not build a complete graph for the issue.",
            "message": "The issue may have no children or linked issues, or the data for its children is missing."
        }

    # 2. Use JiraContextGenerator to convert the graph into a nested dictionary.
    context_generator = JiraContextGenerator()
    issue_hierarchy = context_generator.generate_context(issue_graph, start_issue_key)

    logger.info(f"Successfully generated hierarchy for '{start_issue_key}'.")
    return issue_hierarchy

if __name__ == '__main__':
    # Example of how to use this function from the command line.
    parser = argparse.ArgumentParser(description="Generate a JSON tree for a given JIRA issue.")
    parser.add_argument("issue_key", type=str, help="The root JIRA issue key (e.g., 'BEMABU-12345').")
    args = parser.parse_args()

    # Get the hierarchy.
    hierarchy_dict = get_issue_hierarchy_as_dict(args.issue_key)

    # Print it as a nicely formatted JSON string.
    print(json.dumps(hierarchy_dict, indent=2, ensure_ascii=False))
