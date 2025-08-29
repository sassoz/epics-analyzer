import logging
import os
import sys
from utils.config import LOGS_DIR

def setup_logger():
    """
    Konfiguriert den Logger mit separaten Loglevels für Datei und Konsole.
    """
    # Logger-Instanz holen
    logger = logging.getLogger("jira_scraper")
    logger.setLevel(logging.INFO)  # Das niedrigste Level, das verarbeitet wird

    # Verhindern, dass bei jedem Import neue Handler hinzugefügt werden
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.propagate = False
    # Pfad für die Log-Datei
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file_path = os.path.join(LOGS_DIR, "jira_scraper.log")

    # Formatter, der für beide Handler verwendet wird
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. File Handler: Schreibt alles ab INFO-Level in die Datei
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 2. Console Handler: Gibt alles ab WARNING-Level im Terminal aus
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    # Handler zum Logger hinzufügen
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Erstelle eine globale Logger-Instanz, die überall importiert werden kann
logger = setup_logger()
