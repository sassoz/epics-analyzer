"""
Module for exporting JIRA issue data to various file formats.

This module provides functionality to export JIRA issue data to different file formats
including JSON, XML, and HTML. It handles the serialization and formatting of structured
issue data, ensuring proper encoding and organization of the exported files.

The main class, FileExporter, implements methods for saving JIRA issues in various formats
and handles path management, directory creation, and file writing operations. It supports
both raw HTML exports and processed data exports in structured formats.

Key features:
- Exports JIRA issue data to JSON, XML, and other formats
- Handles directory management and path resolution
- Supports BeautifulSoup-based HTML processing
- Provides consistent file naming conventions
- Ensures proper UTF-8 encoding for international character support
"""

import json
import xml.dom.minidom as md
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import os

from utils.data_extractor import DataExtractor
from utils.logger_config import logger
from utils.config import JIRA_ISSUES_DIR

class FileExporter:
    """Klasse zum Exportieren von Daten in verschiedene Dateiformate."""

    # Pfad für die Speicherung der Jira Issues
    JIRA_ISSUE_PATH = JIRA_ISSUES_DIR

    @staticmethod
    def ensure_directory_exists():
        """
        Stellt sicher, dass das Zielverzeichnis existiert. Erstellt es, falls nicht.
        """
        try:
            if not os.path.exists(FileExporter.JIRA_ISSUE_PATH):
                os.makedirs(FileExporter.JIRA_ISSUE_PATH)
                logger.info(f"Verzeichnis erstellt: {FileExporter.JIRA_ISSUE_PATH}")
        except Exception as e:
            logger.warning(f"Fehler beim Erstellen des Verzeichnisses: {e}")

    @staticmethod
    def get_full_path(filename):
        """
        Generiert den vollständigen Pfad für eine Datei im JIRA_ISSUE_PATH.

        Args:
            filename (str): Der Dateiname

        Returns:
            str: Der vollständige Pfad
        """
        return os.path.join(FileExporter.JIRA_ISSUE_PATH, filename)

    @staticmethod
    def save_as_xml(data, filename):
        """
        Speichert die Daten als XML-Datei im konfigurierten Verzeichnis.

        Args:
            data (dict): Die zu speichernden Daten
            filename (str): Der Dateiname
        """
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            FileExporter.ensure_directory_exists()

            # Generiere den vollständigen Pfad
            full_path = FileExporter.get_full_path(filename)

            # Erstelle das Root-Element
            root = ET.Element("issue")

            # Füge einfache Textelemente hinzu
            for key, value in data.items():
                if isinstance(value, str):
                    elem = ET.SubElement(root, key)
                    elem.text = value
                elif isinstance(value, list):
                    # Für Listen (Kommentare, Labels, etc.)
                    container = ET.SubElement(root, key)
                    if key == "comments":
                        for item in value:
                            comment = ET.SubElement(container, "comment")
                            for k, v in item.items():
                                item_elem = ET.SubElement(comment, k)
                                item_elem.text = str(v)  # Konvertiere auch nicht-string Werte
                    else:
                        for item in value:
                            if isinstance(item, str):
                                item_elem = ET.SubElement(container, "item")
                                item_elem.text = item
                            elif isinstance(item, dict):
                                item_elem = ET.SubElement(container, "item")
                                for k, v in item.items():
                                    sub_elem = ET.SubElement(item_elem, k)
                                    sub_elem.text = str(v)  # Konvertiere auch nicht-string Werte

            # Konvertiere zu einem formatierten XML-String
            rough_string = ET.tostring(root, 'utf-8')
            reparsed = md.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")

            # Speichere in Datei - überschreibt existierende Dateien
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(pretty_xml)

            logger.info(f"Daten als XML gespeichert: {full_path}")

        except Exception as e:
            logger.error(f"Fehler beim Speichern als XML: {e}")

    @staticmethod
    def save_as_json(data, filename):
        """
        Speichert die Daten als JSON-Datei im konfigurierten Verzeichnis.

        Args:
            data (dict): Die zu speichernden Daten
            filename (str): Der Dateiname
        """
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            FileExporter.ensure_directory_exists()

            # Generiere den vollständigen Pfad
            full_path = FileExporter.get_full_path(filename)

            # Speichere in Datei - überschreibt existierende Dateien
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Daten als JSON gespeichert: {full_path}")

        except Exception as e:
            logger.error(f"Fehler beim Speichern als JSON: {e}")

    @staticmethod
    def save_as_beautifulsoup_xml(html_content, filename):
        """
        Konvertiert HTML zu XML mittels BeautifulSoup und speichert im konfigurierten Verzeichnis.

        Args:
            html_content (str): Der HTML-Inhalt
            filename (str): Der Dateiname
        """
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            FileExporter.ensure_directory_exists()

            # Generiere den vollständigen Pfad
            full_path = FileExporter.get_full_path(filename)

            # Parse HTML mit BeautifulSoup
            soup = BeautifulSoup(html_content, 'lxml')

            # Entferne Scripts und Styles für eine schlankere Version
            for script in soup(["script", "style"]):
                script.extract()

            # Konvertiere zu XML
            xml_content = soup.prettify()

            # Speichere in Datei - überschreibt existierende Dateien
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(xml_content)

            logger.info(f"HTML mit BeautifulSoup als XML gespeichert: {full_path}")

        except Exception as e:
            logger.error(f"Fehler beim Konvertieren mit BeautifulSoup: {e}")

    @staticmethod
    def save_html(html_content, filename):
        """
        Speichert den HTML-Inhalt in einer Datei im konfigurierten Verzeichnis.

        Args:
            html_content (str): Der HTML-Inhalt
            filename (str): Der Dateiname
        """
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            FileExporter.ensure_directory_exists()

            # Generiere den vollständigen Pfad
            full_path = FileExporter.get_full_path(filename)

            # Speichere in Datei - überschreibt existierende Dateien
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"HTML-Inhalt gespeichert: {full_path}")

        except Exception as e:
            logger.error(f"Fehler beim Speichern des HTML-Inhalts: {e}")

    @staticmethod
    def process_and_save_issue(driver, issue_key, html_content, issue_data=None):
        """
        Verarbeitet und speichert ein Issue in verschiedenen Formaten im konfigurierten Verzeichnis.

        Args:
            driver (webdriver): Die Browser-Instanz
            issue_key (str): Der Jira-Issue-Key
            html_content (str): Der HTML-Inhalt der Issue-Seite
        """
        try:
            # Use the provided data if available, otherwise extract it
            if issue_data is None:
                issue_data = DataExtractor.extract_issue_data(driver, issue_key)

            # XML-Version (auskommentiert im Original, aber angepasst)
            # FileExporter.save_as_xml(issue_data, f"{issue_key}.xml")

            # JSON-Version
            FileExporter.save_as_json(issue_data, f"{issue_key}.json")

            # 2. BeautifulSoup Version (auskommentiert im Original, aber angepasst)
            # FileExporter.save_as_beautifulsoup_xml(html_content, f"{issue_key}_BS4.xml")

            # 3. Optional: Original-HTML (auskommentiert im Original, aber angepasst)
            # FileExporter.save_html(html_content, f"{issue_key}.html")

            logger.info(f"Alle Versionen für Issue {issue_key} gespeichert im Verzeichnis {FileExporter.JIRA_ISSUE_PATH}")

        except Exception as e:
            logger.error(f"Fehler beim Verarbeiten und Speichern des Issues {issue_key}: {e}")
