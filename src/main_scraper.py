# main_scraper.py

import os
import re
import sys
import json
import argparse
import yaml

# Fügen Sie das übergeordnete Verzeichnis (Projekt-Root) zum Suchpfad hinzu...
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

# Importiere die spezifischen Analyzer-Klassen
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

# Zentrale Liste der zu verwendenden Analyzer
ANALYZERS_TO_RUN = [
    ScopeAnalyzer,
    #DynamicsAnalyzer,
    StatusAnalyzer,
    TimeCreepAnalyzer,
    BacklogAnalyzer
]


def load_prompt(filename, key):
    """Lädt einen Prompt aus einer YAML-Datei im PROMPTS_DIR."""
    file_path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            return prompts[key]
    except (FileNotFoundError, KeyError) as e:
        logger.error(f"Fehler beim Laden des Prompts: {e}")
        sys.exit(1)

def get_business_epics_from_file(file_path=None):
    """
    Lädt und extrahiert Business Epic IDs aus einer Textdatei.
    """
    print("\n=== Telekom Jira Issue Extractor und Analyst ===")
    if not file_path:
        file_path = input("Bitte geben Sie den Pfad zur TXT-Datei mit Business Epics ein (oder drücken Sie Enter für 'BE_Liste.txt'): ")
        if not file_path:
            file_path = "BE_Liste.txt"

    file_to_try = file_path if os.path.exists(file_path) else f"{file_path}.txt"
    if not os.path.exists(file_to_try):
        print(f"FEHLER: Die Datei {file_to_try} existiert nicht.")
        return []

    business_epics = []
    epic_id_pattern = re.compile(r'[A-Z][A-Z0-9]*-\d+')

    with open(file_to_try, 'r', encoding='utf-8') as file:
        for line in file:
            match = epic_id_pattern.search(line)
            if match:
                business_epics.append(match.group(0))

    print(f"{len(business_epics)} Business Epics gefunden.")
    return business_epics

def main():
    """
    Hauptfunktion zur Orchestrierung des Skripts.
    """
    parser = argparse.ArgumentParser(description='Jira Issue Link Scraper')
    parser.add_argument('--scraper', type=str.lower, choices=['true', 'false', 'check'], default='check', help='Steuert das Scraping')
    parser.add_argument('--html_summary', type=str.lower, choices=['true', 'false', 'check'], default='false', help="Erstellt JSON-Zusammenfassung und HTML-Report. 'true': immer neu; 'check': aus Cache, falls vorhanden; 'false': keine Erstellung.")
    parser.add_argument('--issue', type=str, default=None, help='Spezifische Jira-Issue-ID')
    parser.add_argument('--file', type=str, default=None, help='Pfad zur TXT-Datei mit Business Epics')
    parser.add_argument('--translate', type=str.lower, choices=['true', 'false', 'check'], default='false', help="Übersetzt den HTML-Report ins Englische.")

    args = parser.parse_args()

    token_tracker = TokenUsage(log_file_path=TOKEN_LOG_FILE)

    business_epics = [args.issue] if args.issue else get_business_epics_from_file(args.file)
    if not business_epics:
        print("Keine Business Epics gefunden. Programm wird beendet.")
        return

    if args.scraper != 'false':
        print(f"\n--- Scraping-Modus gestartet (Mode: {args.scraper}) ---")
        
        scraper = JiraScraper(
            f"https://jira.telekom.de/browse/{business_epics[0]}", JIRA_EMAIL,
            scrape_mode=args.scraper,
            check_days=SCRAPER_CHECK_DAYS
        )
        for i, epic in enumerate(business_epics):
            print(f"\n\n=============================================================\nVerarbeite Business Epic {i+1}/{len(business_epics)}: {epic}")
            scraper.url = f"https://jira.telekom.de/browse/{epic}"
            scraper.run(skip_login=(i > 0))
    else:
        print("\n--- Scraping übersprungen (Mode: 'false') ---")

    if args.html_summary != 'false':
        print("\n--- Analyse / Reporting gestartet ---")

        # Initialisierung der benötigten Clients und Generatoren
        azure_summary_client = AzureAIClient()
        visualizer = JiraTreeVisualizer(format='png')
        context_generator = JiraContextGenerator()
        html_generator = EpicHtmlGenerator(model=LLM_MODEL_HTML_GENERATOR, token_tracker=token_tracker)
        json_parser = LLMJsonParser()
        analysis_runner = AnalysisRunner(ANALYZERS_TO_RUN)
        json_summary_generator = JsonSummaryGenerator()
        reporter = ConsoleReporter()


        for epic in business_epics:
            print(f"\n--- Starte Verarbeitung für {epic} ---")
            complete_epic_data = None
            complete_summary_path = os.path.join(JSON_SUMMARY_DIR, f"{epic}_complete_summary.json")

            if args.html_summary == 'check' and os.path.exists(complete_summary_path):
                logger.info(f"Lade vollständige Zusammenfassung aus Cache: {complete_summary_path}")
                try:
                    with open(complete_summary_path, 'r', encoding='utf-8') as f:
                        complete_epic_data = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.info(f"Konnte Cache-Datei nicht lesen ({e}). Erstelle Zusammenfassung neu.")

            if complete_epic_data is None:
                logger.info("Keine gültige Cache-Datei gefunden oder Neuerstellung erzwungen. Generiere alle Daten...")

                data_provider = ProjectDataProvider(epic_id=epic, hierarchy_config=JIRA_TREE_FULL)
                if not data_provider.is_valid():
                    logger.error(f"Fehler: Konnte keine gültigen Daten für Analyse von Epic '{epic}' laden. Verarbeitung wird übersprungen.")
                    continue
                print(f"     - Erstelle Analyse für {epic}")
                analysis_results = analysis_runner.run_analyses(data_provider)
                reporter.create_backlog_plot(analysis_results.get("BacklogAnalyzer", {}), epic)

                logger.info(f"Erstelle vollständigen Baum für Visualisierung von {epic} mit JIRA_TREE_MANAGEMENT.")
                tree_generator_full = JiraTreeGenerator(allowed_types=JIRA_TREE_MANAGEMENT)
                issue_tree_for_visualization = tree_generator_full.build_issue_tree(epic)

                if issue_tree_for_visualization:
                    visualizer.visualize(issue_tree_for_visualization, epic)
                else:
                    logger.warning(f"Konnte keinen Baum für die Visualisierung von {epic} erstellen. Die Grafik wird im Report fehlen.")

                issue_tree_for_context = issue_tree_for_visualization

                if issue_tree_for_context and len(issue_tree_for_context) > MAX_JIRA_TREE_CONTEXT_SIZE:
                    logger.info(f"Management-Baum für LLM-Kontext von {epic} ist mit {len(issue_tree_for_context)} Knoten zu groß (Max: {MAX_JIRA_TREE_CONTEXT_SIZE}). Reduziere auf LIGHT-Hierarchie.")
                    tree_generator_light = JiraTreeGenerator(allowed_types=JIRA_TREE_MANAGEMENT_LIGHT)
                    issue_tree_for_context = tree_generator_light.build_issue_tree(epic)

                if not issue_tree_for_context:
                    logger.warning(f"Konnte keinen gültigen Baum für die LLM-Kontext-Generierung von {epic} erstellen. Überspringe Summary-Generierung.")
                    continue

                json_context = context_generator.generate_context(issue_tree_for_context, epic)
                summary_prompt_template = load_prompt("summary_prompt.yaml", "user_prompt_template")
                summary_prompt = summary_prompt_template.format(json_context=json_context)
                print(f"     - Erstelle Summary für {epic}")
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
                epic_status = data_provider.issue_details.get(epic, {}).get('status', 'Unbekannt')
                target_start_status = data_provider.issue_details.get(epic, {}).get('target_start', 'Unbekannt')
                target_end_status = data_provider.issue_details.get(epic, {}).get('target_end', 'Unbekannt')
                fix_version_status = data_provider.issue_details.get(epic, {}).get('fix_versions', 'Unbekannt')
                ordered_content_summary = {"epicId": content_summary.get("epicId"), "title": content_summary.get("title"), "status": epic_status, "target_start": target_start_status, "target_end": target_end_status, "fix_versions": fix_version_status}
                ordered_content_summary.update({k: v for k, v in content_summary.items() if k not in ordered_content_summary})
                content_summary = ordered_content_summary

                complete_epic_data = json_summary_generator.generate_and_save_complete_summary(analysis_results=analysis_results, content_summary=content_summary, epic_id=epic)

            if complete_epic_data:
                print(f"     - Erstelle HTML-File für {epic}")
                logger.info(f"Erstelle HTML-Report für {epic}...")
                html_file = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
                html_generator.generate_epic_html(complete_epic_data, epic, html_file)
            else:
                logger.error(f"Konnte keine vollständigen Daten für die HTML-Erstellung von {epic} erzeugen.")
            
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
                    logger.warning(f"Übersetzung für {epic} übersprungen, da die deutsche HTML-Datei nicht existiert.")
                else:
                    run_translation = False
                    if args.translate == 'true':
                        run_translation = True
                        logger.info(f"Übersetzung für {epic} wird erzwungen ('--translate true').")

                    elif args.translate == 'check':
                        if not os.path.exists(english_html_path):
                            run_translation = True
                            logger.info(f"Englische Version für {epic} existiert nicht. Starte Übersetzung ('--translate check').")
                        else:
                            logger.info(f"Englische Version für {epic} existiert bereits. Übersetzung wird übersprungen.")

                    if run_translation:
                        try:
                            print(f"     - Übersetze HTML-File für {epic}")
                            html_translator.translate_file(epic)
                        except Exception as e:
                            logger.error(f"Fehler bei der Übersetzung von {epic}: {e}")

    else:
        print("\n--- Analyse und HTML-Summary übersprungen ---")


if __name__ == "__main__":
    main()
