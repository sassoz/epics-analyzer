"""
Modul zur Übersetzung von HTML-Berichten mittels einer Batch-Strategie.

Diese Datei enthält die Klasse `HtmlTranslator`, die darauf spezialisiert ist,
HTML-Dateien mit Fachjargon aus der Telekommunikations- und IT-Branche präzise
von Deutsch nach Englisch zu übersetzen. Sie nutzt eine Batch-Verarbeitung, um
Effizienz und Übersetzungsqualität zu maximieren.
"""
import os
import sys
import logging
import json
from bs4 import BeautifulSoup, NavigableString

# Stellt sicher, dass die übergeordneten utils-Module gefunden werden
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.config import HTML_REPORTS_DIR
from utils.azure_ai_client import AzureAIClient
from utils.token_usage_class import TokenUsage

# System-Prompt für die Batch-Verarbeitung mit JSON
SYSTEM_PROMPT_TRANSLATOR = """
You are an expert translator specializing in the Telecommunications and IT sectors.
Your task is to translate a batch of German text snippets into professional, domain-specific English.
You will receive a JSON object with a key "texts_to_translate", which contains a list of objects, each with an "id" and "text".
You MUST return a JSON object with a single key "translations", containing a list of objects with the corresponding "id" and the translated "text".
It is crucial that you accurately translate technical terms, jargon, and business concepts.
Do NOT translate technical identifiers like Jira keys (e.g., 'BEMABU-2365').
Your response must be a valid JSON object and nothing else.
"""

# Liste von Tags, deren Inhalt übersetzt werden soll
TRANSLATABLE_TAGS = ['p', 'h1', 'h2', 'h3', 'li', 'td', 'th', 'title', 'div', 'strong', 'b', 'em']

class HtmlTranslator:
    """
    Eine Klasse zur Übersetzung von HTML-Dateien unter Beibehaltung der Struktur.

    Verwendet eine Batch-Strategie, um alle relevanten Textinhalte und Attribute
    gebündelt an eine KI-API zu senden und die Ergebnisse anschließend wieder
    in das HTML-Dokument einzufügen.
    """
    def __init__(self, ai_client: AzureAIClient, token_tracker: TokenUsage, model_name: str):
        """
        Initialisiert den HtmlTranslator.

        Args:
            ai_client (AzureAIClient): Ein instanziierter Client für die Azure AI API.
            token_tracker (TokenUsage): Eine Instanz zur Protokollierung des Token-Verbrauchs.
            model_name (str): Der Name des zu verwendenden Übersetzungsmodells.
        """
        self.ai_client = ai_client
        self.ai_client.system_prompt = SYSTEM_PROMPT_TRANSLATOR # Setzt den spezifischen Prompt
        self.token_tracker = token_tracker
        self.model_name = model_name

    def translate_file(self, issue_key: str):
        """
        Übersetzt eine einzelne HTML-Berichtsdatei vom Deutschen ins Englische.

        Implementiert eine Batch-Strategie, um alle Textknoten und 'alt'-Attribute
        zu extrahieren, in einer einzigen Anfrage zu übersetzen und die Ergebnisse
        wieder an den ursprünglichen Positionen im HTML einzufügen.

        Args:
            issue_key (str): Der Jira-Key des Epics (z.B. "BEMABU-1410"), der als
                             Basis für die Dateinamen dient.
        """
        input_filename = f"{issue_key}_summary.html"
        output_filename = f"{issue_key}_summary_englisch.html"
        input_filepath = os.path.join(HTML_REPORTS_DIR, input_filename)
        output_filepath = os.path.join(HTML_REPORTS_DIR, output_filename)

        if not os.path.exists(input_filepath):
            logging.error(f"Eingabedatei für Übersetzung nicht gefunden: {input_filepath}")
            return

        logging.info(f"Lese und parse Datei für Übersetzung: {input_filename}")
        with open(input_filepath, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')

        # --- PHASE 1: Alle zu übersetzenden Inhalte extrahieren ---
        nodes_to_translate = []
        texts_for_api = []

        # Extrahiere Textknoten
        for text_node in soup.find_all(string=True):
            if text_node.parent.name in ['script', 'style'] or not text_node.strip():
                continue
            if text_node.parent.name in TRANSLATABLE_TAGS:
                original_text = text_node.strip()
                if original_text:
                    node_id = len(nodes_to_translate)
                    nodes_to_translate.append({"id": node_id, "type": "text", "node": text_node})
                    texts_for_api.append({"id": node_id, "text": original_text})

        # Extrahiere 'alt'-Attribute von Bildern
        for img_tag in soup.find_all('img', alt=True):
            original_alt = img_tag['alt'].strip()
            if original_alt:
                node_id = len(nodes_to_translate)
                nodes_to_translate.append({"id": node_id, "type": "attribute", "node": img_tag, "attr_name": "alt"})
                texts_for_api.append({"id": node_id, "text": original_alt})

        if not texts_for_api:
            logging.warning(f"Keine Texte zur Übersetzung in {input_filename} gefunden.")
            return

        logging.info(f"{len(texts_for_api)} Elemente zur Batch-Übersetzung extrahiert.")

        # --- PHASE 2: Einzelner API-Aufruf mit allen Texten ---
        try:
            api_payload = {"texts_to_translate": texts_for_api}
            user_prompt_json = json.dumps(api_payload, ensure_ascii=False, indent=2)

            response = self.ai_client.completion(
                model_name=self.model_name,
                user_prompt=user_prompt_json,
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"}
            )

            self.token_tracker.log_usage(
                model=self.model_name,
                input_tokens=response['usage'].prompt_tokens,
                output_tokens=response['usage'].completion_tokens,
                total_tokens=response['usage'].total_tokens,
                task_name="html_translation",
                entity_id=issue_key
            )

            # --- PHASE 3: Antwort verarbeiten und Inhalte wieder einfügen ---
            translated_data = json.loads(response['text'])
            translations = translated_data.get("translations", [])

            if len(translations) != len(nodes_to_translate):
                logging.warning(f"Anzahl der Übersetzungen ({len(translations)}) stimmt nicht mit Originaltexten ({len(nodes_to_translate)}) überein!")

            for item in translations:
                item_id = item.get("id")
                translated_text = item.get("text", "").strip()
                if 0 <= item_id < len(nodes_to_translate):
                    target = nodes_to_translate[item_id]
                    if target['type'] == 'text':
                        target['node'].replace_with(NavigableString(translated_text))
                    elif target['type'] == 'attribute':
                        target['node'][target['attr_name']] = translated_text

        except json.JSONDecodeError:
            logging.error("Fehler beim Parsen der JSON-Antwort von der API.", exc_info=True)
            logging.debug(f"Erhaltene Antwort: {response.get('text', 'Keine Antwort')}")
            return
        except Exception as e:
            logging.error(f"Ein Fehler ist während des API-Aufrufs aufgetreten: {e}", exc_info=True)
            return

        # Speichere die übersetzte HTML-Datei
        with open(output_filepath, "w", encoding='utf-8') as f:
            f.write(str(soup))

        logging.info(f"Übersetzte Datei erfolgreich gespeichert: {output_filepath}\n")
