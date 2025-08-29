import os
import sys
import yaml
from .logger_config import logger # Annahme, dass logger_config in utils liegt

from utils.config import PROMPTS_DIR

def load_prompt_template(filename: str, key: str) -> str:
    """
    Lädt eine Prompt-Vorlage aus einer YAML-Datei im PROMPTS_DIR.

    Args:
        filename (str): Der Name der YAML-Datei (z.B. 'summary_prompt.yaml').
        key (str): Der Schlüssel innerhalb der YAML-Datei, dessen Wert geladen werden soll.

    Returns:
        str: Die geladene Prompt-Vorlage als String.
    """
    file_path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            return prompts[key]
    except FileNotFoundError:
        logger.error(f"Prompt-Datei nicht gefunden: {file_path}")
        sys.exit(1) # Beendet das Skript, wenn ein Prompt fehlt
    except KeyError:
        logger.error(f"Schlüssel '{key}' nicht in der Prompt-Datei '{filename}' gefunden.")
        sys.exit(1)
