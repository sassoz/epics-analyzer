# main_scraper.py

import os
import re
import sys
import json
import argparse
import yaml

# Add the parent directory (project root) to the search path...
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.jira_scraper_api import JiraScraper
from utils.jira_tree_classes import JiraTreeGenerator, JiraTreeVisualizer, JiraContextGenerator
from utils.azure_ai_client import AzureAIClient
from utils.epic_html_generator import EpicHtmlGenerator
from utils.token_usage_class import TokenUsage
from utils.logger_config import logger
from utils.json_parser import LLMJsonParser
from utils.html_translator import HtmlTranslator
from utils.project_data_provider import ProjectDataProvider
from features.console_reporter import ConsoleReporter
from features.json_summary_generator import JsonSummaryGenerator

# Import the specific analyzer classes
from features.scope_analyzer import ScopeAnalyzer
from features.dynamics_analyzer import DynamicsAnalyzer
from features.status_analyzer import StatusAnalyzer
from features.time_creep_analyzer import TimeCreepAnalyzer
from features.backlog_analyzer import BacklogAnalyzer
from features.analysis_runner import AnalysisRunner

from utils.config import (
    JIRA_ISSUES_DIR,
    JSON_SUMMARY_DIR,
    HTML_REPORTS_DIR,
    LLM_MODEL_HTML_GENERATOR,
    LLM_MODEL_BUSINESS_VALUE,
    LLM_MODEL_SUMMARY,
    LLM_MODEL_TRANSLATOR,
    DEFAULT_SCRAPE_HTML,
    JIRA_EMAIL,
    PROMPTS_DIR,
    TOKEN_LOG_FILE,
    SCRAPER_CHECK_DAYS,
    ISSUE_LOG_FILE,
    JIRA_TREE_MANAGEMENT,
    JIRA_TREE_MANAGEMENT_LIGHT,
    JIRA_TREE_FULL,
    MAX_JIRA_TREE_CONTEXT_SIZE
)

# Central list of analyzers to use
ANALYZERS_TO_RUN = [
    ScopeAnalyzer,
    #DynamicsAnalyzer,
    StatusAnalyzer,
    TimeCreepAnalyzer,
    BacklogAnalyzer
]


def load_prompt(filename, key):
    """Loads a prompt from a YAML file in PROMPTS_DIR."""
    file_path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            return prompts[key]
    except (FileNotFoundError, KeyError) as e:
        logger.error(f"Error loading prompt: {e}")
        sys.exit(1)

def get_business_epics_from_file(file_path=None):
    """
    Loads and extracts Business Epic IDs from a text file.
    """
    print("\n=== Telekom Jira Issue Extractor and Analyst ===")
    if not file_path:
        file_path = input("Please enter the path to the TXT file with Business Epics (or press Enter for 'BE_Liste.txt'): ")
        if not file_path:
            file_path = "BE_Liste.txt"

    file_to_try = file_path if os.path.exists(file_path) else f"{file_path}.txt"
    if not os.path.exists(file_to_try):
        print(f"ERROR: The file {file_to_try} does not exist.")
        return []

    business_epics = []
    epic_id_pattern = re.compile(r'[A-Z][A-Z0-9]*-\d+')

    with open(file_to_try, 'r', encoding='utf-8') as file:
        for line in file:
            match = epic_id_pattern.search(line)
            if match:
                business_epics.append(match.group(0))

    print(f"{len(business_epics)} Business Epics found.")
    return business_epics

def main():
    """
    Main function to orchestrate the script.
    """
    parser = argparse.ArgumentParser(description='Jira Issue Link Scraper')
    parser.add_argument('--scraper', type=str.lower, choices=['true', 'false', 'check'], default='check', help='Controls scraping')
    parser.add_argument('--html_summary', type=str.lower, choices=['true', 'false', 'check'], default='false', help="Creates JSON summary and HTML report. 'true': always new; 'check': from cache if available; 'false': no creation.")
    parser.add_argument('--issue', type=str, default=None, help='Specific Jira issue ID')
    parser.add_argument('--file', type=str, default=None, help='Path to the TXT file with Business Epics')
    parser.add_argument('--translate', type=str.lower, choices=['true', 'false', 'check'], default='false', help="Translates the HTML report to English.")
    parser.add_argument('--verbose', action='store_true', help='Enable detailed logging during tree generation.')

    args = parser.parse_args()

    token_tracker = TokenUsage(log_file_path=TOKEN_LOG_FILE)

    business_epics = [args.issue] if args.issue else get_business_epics_from_file(args.file)
    if not business_epics:
        print("No Business Epics found. Program will be terminated.")
        return

    if args.scraper != 'false':
        print(f"\n--- Scraping mode started (Mode: {args.scraper}) ---")
        
        scraper = JiraScraper(
            f"https://jira.telekom.de/browse/{business_epics[0]}", JIRA_EMAIL,
            scrape_mode=args.scraper,
            check_days=SCRAPER_CHECK_DAYS
        )
        for i, epic in enumerate(business_epics):
            print(f"\n\n=============================================================\nProcessing Business Epic {i+1}/{len(business_epics)}: {epic}")
            scraper.url = f"https://jira.telekom.de/browse/{epic}"
            scraper.run(skip_login=(i > 0))

            # --- NEW: Automatically generate the tree after scraping ---
            logger.info(f"--- Generating issue tree for {epic} ---")
            tree_generator = JiraTreeGenerator(allowed_types=JIRA_TREE_FULL, verbose=args.verbose)
            issue_tree = tree_generator.build_issue_tree(epic)
            if issue_tree:
                visualizer = JiraTreeVisualizer()
                visualizer.visualize(issue_tree, epic)
                logger.info(f"Successfully generated and saved the issue tree for {epic}.")
            else:
                logger.warning(f"Could not generate an issue tree for {epic}. The visualization will be skipped.")

    else:
        print("\n--- Scraping skipped (Mode: 'false') ---")

    if args.html_summary != 'false':
        print("\n--- Analysis / Reporting started ---")

        # Initialization of the required clients and generators
        azure_summary_client = AzureAIClient()
        visualizer = JiraTreeVisualizer(format='png')
        context_generator = JiraContextGenerator()
        html_generator = EpicHtmlGenerator(model=LLM_MODEL_HTML_GENERATOR, token_tracker=token_tracker)
        json_parser = LLMJsonParser()
        analysis_runner = AnalysisRunner(ANALYZERS_TO_RUN)
        json_summary_generator = JsonSummaryGenerator()
        reporter = ConsoleReporter()


        for epic in business_epics:
            print(f"\n--- Start processing for {epic} ---")
            complete_epic_data = None
            complete_summary_path = os.path.join(JSON_SUMMARY_DIR, f"{epic}_complete_summary.json")

            if args.html_summary == 'check' and os.path.exists(complete_summary_path):
                logger.info(f"Loading complete summary from cache: {complete_summary_path}")
                try:
                    with open(complete_summary_path, 'r', encoding='utf-8') as f:
                        complete_epic_data = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.info(f"Could not read cache file ({e}). Recreating summary.")

            if complete_epic_data is None:
                logger.info("No valid cache file found or recreation forced. Generating all data...")

                data_provider = ProjectDataProvider(epic_id=epic, hierarchy_config=JIRA_TREE_FULL, verbose=args.verbose)
                if not data_provider.is_valid():
                    logger.error(f"Error: Could not load valid data for analysis of Epic '{epic}'. Processing will be skipped.")
                    continue
                print(f"     - Creating analysis for {epic}")
                analysis_results = analysis_runner.run_analyses(data_provider)
                reporter.create_backlog_plot(analysis_results.get("BacklogAnalyzer", {}), epic)

                logger.info(f"Creating full tree for visualization of {epic} with JIRA_TREE_MANAGEMENT.")
                tree_generator_full = JiraTreeGenerator(allowed_types=JIRA_TREE_MANAGEMENT, verbose=args.verbose)
                issue_tree_for_visualization = tree_generator_full.build_issue_tree(epic)

                if issue_tree_for_visualization:
                    visualizer.visualize(issue_tree_for_visualization, epic)
                else:
                    logger.warning(f"Could not create a tree for the visualization of {epic}. The graphic will be missing in the report.")

                issue_tree_for_context = issue_tree_for_visualization

                if issue_tree_for_context and len(issue_tree_for_context) > MAX_JIRA_TREE_CONTEXT_SIZE:
                    logger.info(f"Management tree for LLM context of {epic} is too large with {len(issue_tree_for_context)} nodes (Max: {MAX_JIRA_TREE_CONTEXT_SIZE}). Reducing to LIGHT hierarchy.")
                    tree_generator_light = JiraTreeGenerator(allowed_types=JIRA_TREE_MANAGEMENT_LIGHT, verbose=args.verbose)
                    issue_tree_for_context = tree_generator_light.build_issue_tree(epic)

                if not issue_tree_for_context:
                    logger.warning(f"Could not create a valid tree for LLM context generation of {epic}. Skipping summary generation.")
                    continue

                json_context = context_generator.generate_context(issue_tree_for_context, epic)
                summary_prompt_template = load_prompt("summary_prompt.yaml", "user_prompt_template")
                summary_prompt = summary_prompt_template.format(json_context=json_context)
                print(f"     - Creating summary for {epic}")
                response_data = azure_summary_client.completion(
                    model_name=LLM_MODEL_SUMMARY,
                    user_prompt=summary_prompt,
                    max_tokens=20000,
                    response_format={"type": "json_object"}
                )

                if token_tracker and "usage" in response_data:
                    usage = response_data["usage"]
                    token_tracker.log_usage(model=LLM_MODEL_SUMMARY, input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, total_tokens=usage.total_tokens, task_name=f"summary_generation")

                content_summary = json_parser.extract_and_parse_json(response_data["text"])
                epic_status = data_provider.issue_details.get(epic, {}).get('status', 'Unknown')
                target_start_status = data_provider.issue_details.get(epic, {}).get('target_start', 'Unknown')
                target_end_status = data_provider.issue_details.get(epic, {}).get('target_end', 'Unknown')
                fix_version_status = data_provider.issue_details.get(epic, {}).get('fix_versions', 'Unknown')
                ordered_content_summary = {"epicId": content_summary.get("epicId"), "title": content_summary.get("title"), "status": epic_status, "target_start": target_start_status, "target_end": target_end_status, "fix_versions": fix_version_status}
                ordered_content_summary.update({k: v for k, v in content_summary.items() if k not in ordered_content_summary})
                content_summary = ordered_content_summary

                complete_epic_data = json_summary_generator.generate_and_save_complete_summary(analysis_results=analysis_results, content_summary=content_summary, epic_id=epic)

            if complete_epic_data:
                print(f"     - Creating HTML file for {epic}")
                logger.info(f"Creating HTML report for {epic}...")
                html_file = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
                html_generator.generate_epic_html(complete_epic_data, epic, html_file)
            else:
                logger.error(f"Could not generate complete data for the HTML creation of {epic}.")
            
            if args.translate != 'false':
                azure_translator_client = AzureAIClient()
                html_translator = HtmlTranslator(
                    ai_client=azure_translator_client,
                    token_tracker=token_tracker,
                    model_name=LLM_MODEL_TRANSLATOR
                )

                german_html_path = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
                english_html_path = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary_englisch.html")

                if not os.path.exists(german_html_path):
                    logger.warning(f"Translation for {epic} skipped because the German HTML file does not exist.")
                else:
                    run_translation = False
                    if args.translate == 'true':
                        run_translation = True
                        logger.info(f"Translation for {epic} is forced ('--translate true').")

                    elif args.translate == 'check':
                        if not os.path.exists(english_html_path):
                            run_translation = True
                            logger.info(f"English version for {epic} does not exist. Starting translation ('--translate check').")
                        else:
                            logger.info(f"English version for {epic} already exists. Translation will be skipped.")

                    if run_translation:
                        try:
                            print(f"     - Translating HTML file for {epic}")
                            html_translator.translate_file(epic)
                        except Exception as e:
                            logger.error(f"Error during translation of {epic}: {e}")

    else:
        print("\n--- Analysis and HTML summary skipped ---")


if __name__ == "__main__":
    main()
