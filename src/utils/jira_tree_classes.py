
import networkx as nx
from tqdm import tqdm
import logging
import os
import json
import matplotlib.pyplot as plt

# Configure logging
logger = logging.getLogger(__name__)

class JiraTreeGenerator:
    def __init__(self, jira_client, project_data_provider, verbose=False):
        self.jira_client = jira_client
        self.issue_details = project_data_provider.issue_details
        self.issue_tree = project_data_provider.issue_tree
        self.verbose = verbose
        self.all_issue_keys = list(project_data_provider.issue_details.keys())
        self.config = project_data_provider.config
        self.project_data_provider = project_data_provider
        
    def build_tree_for_root(self, root_key):
        if self.verbose:
            print(f"\n{'='*50}\n?? START: Building Tree for Root: {root_key}")
            print(f"CONFIG: {self.config.get('jira_issue_relation_map')}")
            print(f"{'='*50}\n")

        # Initialize the queue with the root issue
        processing_queue = [root_key]
        processed_keys = {root_key}

        # Use tqdm for progress bar if not in verbose mode
        pbar = None
        if not self.verbose:
            pbar = tqdm(total=1, desc="Processing Jira Issues")

        while processing_queue:
            parent_key = processing_queue.pop(0)

            parent_data = self.issue_details.get(parent_key)
            if not parent_data:
                logger.warning(f"No data found for parent issue {parent_key}, skipping.")
                if pbar: pbar.update(1)
                continue

            parent_issue_type = parent_data.get('type')
            if self.verbose:
                print(f"?? Processing Parent: {parent_key} (Type: {parent_issue_type})")

            # --- Unified Child Processing ---
            
            # 1. Get all potential children from links and 'issues_in_epic'
            potential_children = []
            
            # From standard links
            if 'links' in parent_data:
                for link in parent_data['links']:
                    child_key = link.get('key')
                    relation_type = link.get('relation')
                    if child_key:
                        potential_children.append({'key': child_key, 'relation': relation_type, 'source': 'link'})
            
            # From 'issues_in_epic' for Epics
            if parent_issue_type == 'Epic' and 'issues_in_epic' in parent_data:
                 if self.verbose: print(f"  -> Found 'Issues in epic' section for {parent_key}")
                 for issue_in_epic in parent_data['issues_in_epic']:
                    child_key = issue_in_epic.get('key')
                    if child_key:
                        # For issues in an epic, the relation is implicitly 'contains' or 'child'
                        potential_children.append({'key': child_key, 'relation': 'issue_in_epic', 'source': 'epic_child'})


            # 2. Determine allowed relations for the parent issue type
            jira_relation_map = self.config.get('jira_issue_relation_map', {})
            allowed_relations = jira_relation_map.get(parent_issue_type, [])
            
            # Add 'issue_in_epic' to allowed relations for Epics, as it's a structural link
            if parent_issue_type == 'Epic' and 'issue_in_epic' not in allowed_relations:
                allowed_relations.append('issue_in_epic')


            if self.verbose:
                print(f"  -> Allowed Relations for '{parent_issue_type}': {allowed_relations}")

            # 3. Process each potential child
            for child_info in potential_children:
                child_key = child_info['key']
                relation_type = child_info['relation']
                source = child_info['source']

                # Skip if data for child is not available
                if not self.issue_details.get(child_key):
                    logger.warning(f"No data for child {child_key} of {parent_key}, skipping.")
                    continue

                if self.verbose:
                    print(f"  - Found link: {parent_key} -> '{relation_type}' -> {child_key}", end="")

                # Check if the relation is allowed
                if relation_type in allowed_relations:
                    if self.verbose: print(" ... ?? MATCH")
                    
                    # Add edge to the graph
                    self.issue_tree.add_edge(parent_key, child_key, relation=relation_type)
                    
                    # Add to processing queue if not already processed
                    if child_key not in processed_keys:
                        processed_keys.add(child_key)
                        processing_queue.append(child_key)
                        if pbar: pbar.total += 1
                else:
                    if self.verbose: print(" ... ?? NO MATCH")
            
            if pbar:
                pbar.update(1)
        
        if pbar:
            pbar.close()

        if self.verbose:
            print(f"\n{'='*50}\n?? END: Tree building complete. Total nodes: {self.issue_tree.number_of_nodes()}")
            print(f"{'='*50}\n")
            
        self.project_data_provider.issue_tree = self.issue_tree
        self.project_data_provider.find_and_set_root_node()

        return self.issue_tree

class JiraTreeVisualizer:
    def __init__(self, format='png'):
        self.format = format

    def visualize(self, issue_tree, epic_id):
        if not issue_tree.nodes():
            logger.warning("Issue tree is empty, visualization will be skipped.")
            return

        plt.figure(figsize=(20, 15))
        pos = nx.nx_agraph.graphviz_layout(issue_tree, prog="dot")
        
        nx.draw(issue_tree, pos, with_labels=True, node_size=3000, node_color="skyblue", font_size=10, font_weight="bold")
        
        # Save the visualization
        output_dir = os.path.join("templates", f"{epic_id}_issue_tree.{self.format}")
        os.makedirs(os.path.dirname(output_dir), exist_ok=True)
        plt.savefig(output_dir)
        plt.close() # Close the figure to free up memory
        logger.info(f"Issue tree visualization saved to {output_dir}")

class JiraContextGenerator:
    def generate_context(self, issue_tree, epic_id):
        if not issue_tree or not epic_id in issue_tree:
            logger.warning(f"Cannot generate context. Epic ID '{epic_id}' not found in the tree or tree is empty.")
            return "{}" # Return an empty JSON object as a string

        # Create a serializable representation of the tree
        tree_data = nx.tree_data(issue_tree, root=epic_id)
        return json.dumps(tree_data, indent=2)

