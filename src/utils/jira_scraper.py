"""
Modul zum Scrapen und Verarbeiten von JIRA-Issues aus der Weboberfläche.

Dieses Modul stellt die Kernfunktionalität zur Automatisierung der JIRA-Webinteraktion
zur Verfügung. Es nutzt einen Headless-Browser, um Authentifizierung, Navigation und die
rekursive Extraktion von Issue-Daten und deren Beziehungen zu handhaben.

Die zentrale Klasse, JiraScraper, orchestriert den gesamten Prozess, inklusive:
- Der Browser-Interaktion und dem Login-Prozess.
- Verschiedenen Scraping-Modi ('true', 'check'), um das erneute Laden von
  Daten zu steuern.
- Einem robusten, zweistufigen Retry-Mechanismus für fehlgeschlagene Ladevorgänge.
- Der rekursiven Traversierung von "is realized by"-Links sowie Kind-Issues,
  um eine vollständige Hierarchie aufzubauen.
"""

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from datetime import datetime, timedelta
import subprocess
import re
import json
import xml.dom.minidom as md
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

from utils.config import JIRA_ISSUES_DIR, ISSUE_LOG_FILE
from utils.logger_config import logger
from utils.login_handler import JiraLoginHandler
from utils.file_exporter import FileExporter
from utils.data_extractor import DataExtractor
from utils.business_impact_api import process_description


class JiraScraper:
    """
    Hauptklasse zum Scraping von Jira-Issues mit integrierter Retry-Logik.

    Diese Klasse steuert den gesamten Prozess des Web-Scrapings für ein gegebenes
    Start-Issue (typischerweise ein Business Epic). Sie navigiert durch die
    Jira-Weboberfläche, extrahiert Daten und folgt rekursiv allen verknüpften
    Issues, um einen vollständigen Daten-Snapshot zu erstellen.

    Attributes:
        url (str): Die Start-URL des Jira-Issues.
        email (str): Die E-Mail-Adresse für den Jira-Login.
        scrape_mode (str): Steuert das Scraping-Verhalten.
            'true': Scrapt alle Issues, unabhängig vom lokalen Speicher.
            'check': Scrapt nur Issues, die lokal nicht oder nur veraltet
                     vorhanden sind (siehe _should_skip_issue).
        check_days (int): Die Anzahl der Tage, die eine lokale Datei als
                          "aktuell" gilt, wenn `scrape_mode` auf 'check'
                          gesetzt ist.
        driver: Die Selenium WebDriver-Instanz.
        processed_issues (set): Ein Set zur Nachverfolgung der in diesem
                                Programmlauf bereits verarbeiteten Issue-Keys,
                                um Endlosschleifen zu verhindern.
        issues_to_retry (dict): Sammelt Issues, die im ersten Durchlauf
                                fehlgeschlagen sind, für einen zweiten Versuch.
    """

    # __init__ bleibt unverändert
    def __init__(self, url, email, model="o3-mini", token_tracker=None, azure_client=None, scrape_mode='true', check_days=7):

        from dotenv import load_dotenv, find_dotenv
        _ = load_dotenv(find_dotenv())
        self.url = url
        self.email = email
        self.pwd = os.getenv("JIRA_LOGIN_PWD")
        self.login_handler = JiraLoginHandler()
        self.driver = None
        self.processed_issues = set()
        self.issues_to_retry = {}
        self.scrape_mode = scrape_mode
        self.check_days = check_days
        self.data_extractor = DataExtractor(
            description_processor=process_description,
            model=model,
            token_tracker=token_tracker,
            azure_client=azure_client
        )

    def _should_skip_issue(self, issue_key):
        """
        Prüft, ob das *Scraping* für ein Issue übersprungen werden soll.

        Im Modus 'check' wird das aktive Scraping übersprungen, wenn die
        zugehörige lokale JSON-Datei existiert UND eine der folgenden
        Bedingungen erfüllt ist:
        a) Der Status des Issues in der Datei ist 'closed'.
        b) Die Datei ist jünger als `self.check_days` Tage.

        In allen anderen Modi (z.B. 'true') gibt die Methode immer `False`
        zurück, was bedeutet, dass immer gescraped wird.
        """
        # Nur im 'check'-Modus die Prüfungen durchführen
        if self.scrape_mode != 'check':
            return False

        issue_file_path = os.path.join(JIRA_ISSUES_DIR, f"{issue_key}.json")

        # Wenn die Datei nicht existiert, kann nicht übersprungen werden.
        if not os.path.exists(issue_file_path):
            return False

        # Wenn die Datei existiert, prüfe Status und Alter.
        try:
            # Bedingung a): Prüfe, ob der Status 'closed' ist.
            with open(issue_file_path, 'r', encoding='utf-8') as f:
                issue_data = json.load(f)
            status = issue_data.get('status', '').lower()
            if status == 'closed':
                logger.info(f"Issue {issue_key} hat den Status 'closed'. Überspringe Scraping.")
                return True  # Überspringen, weil geschlossen.

            # Bedingung b): Wenn nicht geschlossen, prüfe das Alter der Datei.
            file_mod_time = os.path.getmtime(issue_file_path)
            modified_date = datetime.fromtimestamp(file_mod_time)
            if datetime.now() - modified_date < timedelta(days=self.check_days):
                logger.info(f"Issue {issue_key} ist aktuell (jünger als {self.check_days} Tage). Überspringe Scraping.")
                return True  # Überspringen, weil aktuell.

        except (json.JSONDecodeError, KeyError) as e:
            # Bei Fehlern (z.B. kaputte JSON-Datei) zur Sicherheit neu laden.
            logger.info(f"Konnte Status/Alter für {issue_key} nicht prüfen ({e}). Lade zur Sicherheit neu.")
            return False

        # Wenn keine der obigen Skip-Bedingungen zutraf, muss neu geladen werden.
        logger.info(f"Issue {issue_key} ist veraltet und nicht geschlossen. Wird erneut geladen.")
        return False

    def extract_and_save_issue_data(self, issue_url, issue_key=None, is_retry=False):
        """
        Extrahiert, speichert und liefert die Daten eines einzelnen Issues.

        Diese Methode ist der Kern des Scraping-Prozesses. Sie entscheidet auf
        Basis von `_should_skip_issue`, ob ein Issue aktiv von der Webseite
        geladen oder aus dem lokalen Cache gelesen werden soll.

        WICHTIG: Auch wenn das Scraping eines Issues übersprungen wird, liest
        die Methode die lokale Datei ein und gibt deren Inhalt zurück. Dies
        stellt sicher, dass die Traversierung zu den Kind-Issues (`issue_links`)
        immer fortgesetzt wird, auch wenn der Eltern-Knoten bereits aktuell war.
        Dadurch können fehlende oder veraltete Issues in der Hierarchie gezielt
        nachgeladen werden.

        Args:
            issue_url (str): Die URL des zu verarbeitenden Jira-Issues.
            issue_key (str, optional): Der Key des Issues. Wenn nicht
                                       angegeben, wird er aus der URL
                                       extrahiert.
            is_retry (bool, optional): Flag, das anzeigt, ob dies ein
                                       zweiter Versuch für ein fehlgeschlagenes
                                       Issue ist.

        Returns:
            dict or None: Ein Dictionary mit den Issue-Daten bei Erfolg,
                          andernfalls None. Die Daten können entweder frisch
                          gescraped oder aus einer lokalen Datei gelesen sein.
        """
        if not issue_key:
            issue_key = issue_url.split('/browse/')[1] if '/browse/' in issue_url else None
        if not issue_key:
            logger.warning(f"Konnte keinen Issue-Key aus URL extrahieren: {issue_url}"); return None

        # Verhindert Endlosschleifen innerhalb EINES Programmdurchlaufs
        if issue_key in self.processed_issues:
            logger.info(f"Issue {issue_key} wurde bereits in diesem Durchlauf verarbeitet, überspringe..."); return None

        # Prüfen, ob das Scraping für dieses Issue übersprungen werden soll
        if self._should_skip_issue(issue_key):
            # JA -> Lese die existierende Datei, um die Kind-Beziehungen zu erhalten
            issue_file_path = os.path.join(JIRA_ISSUES_DIR, f"{issue_key}.json")
            try:
                with open(issue_file_path, 'r', encoding='utf-8') as f:
                    issue_data = json.load(f)
                self.processed_issues.add(issue_key)
                # Gib die lokalen Daten zurück, damit die Traversierung fortgesetzt werden kann
                return issue_data
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.info(f"Issue {issue_key} sollte übersprungen werden, aber die lokale Datei ist nicht lesbar ({e}). Fahre mit dem Scraping fort.")
                # Fällt durch zum normalen Scraping-Block

        # NEIN -> Normales Scraping durchführen (gilt für 'true' Modus oder veraltete Issues im 'check' Modus)
        try:
            self.driver.get(issue_url)
            logger.info(f"Verarbeite Issue: {issue_key}" + (" (Retry)" if is_retry else ""))
            print(f"{datetime.now().strftime('%H:%M:%S')} Verarbeite Issue: {issue_key}" + (" (Retry)" if is_retry else ""))

            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "issue-content")))

            try:
                all_tab_link = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li#all-tabpanel a")))
                self.driver.execute_script("arguments[0].click();", all_tab_link)
                time.sleep(1)
                while True:
                    try:
                        load_more_button = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.CLASS_NAME, "show-more-all-tabpanel")))
                        self.driver.execute_script("arguments[0].click();", load_more_button)
                        time.sleep(2)
                    except TimeoutException:
                        break
            except Exception as tab_error:
                logger.info(f"Konnte für Issue {issue_key} nicht alle Aktivitäten laden. Wird für 2. Versuch vorgemerkt. Fehler: {tab_error}")
                self.issues_to_retry[issue_key] = issue_url
                return None

            html_content = self.driver.page_source
            issue_data = self.data_extractor.extract_issue_data(self.driver, issue_key)
            issue_data['activities'] = self.data_extractor.extract_activity_details(html_content)
            FileExporter.process_and_save_issue(self.driver, issue_key, html_content, issue_data)
            self.processed_issues.add(issue_key)
            return issue_data

        except Exception as e:
            if is_retry:
                html_source = self.driver.page_source
                if 'class="issue-error"' in html_source and "can't view this issue" in html_source:
                    logger.warning(f"Issue {issue_key} existiert nicht mehr oder die Berechtigung fehlt. Wird endgültig übersprungen.")
                    self.processed_issues.add(issue_key)
                    return None

            logger.error(f"Ein schwerwiegender Fehler ist beim Verarbeiten von Issue {issue_key} aufgetreten: {e}")
            self.issues_to_retry[issue_key] = issue_url
            return None

    def process_related_issues(self, issue_data, current_url, is_retry=False):
        """
        Iterative DFS over related issues to avoid recursion depth errors and cycles.
        Uses self.processed_issues as the global visited set.
        """
        if not issue_data:
            return

        stack = []
        # seed with the first layer
        for rel in issue_data.get("issue_links", []) or []:
            k = rel.get("key")
            u = rel.get("url")
            if not k or not u:
                continue
            if k in self.processed_issues:
                continue
            stack.append((k, u))

        while stack:
            k, u = stack.pop()

            # skip if we picked it up meanwhile
            if k in self.processed_issues:
                continue

            try:
                related_data = self.extract_and_save_issue_data(u, k, is_retry=is_retry)
                if not related_data:
                    # If it failed now, it will be retried by the normal retry path.
                    continue

                # mark visited immediately to break cycles
                self.processed_issues.add(k)

                # push its children
                for rel in related_data.get("issue_links", []) or []:
                    ck = rel.get("key")
                    cu = rel.get("url")
                    if not ck or not cu:
                        continue
                    if ck in self.processed_issues:
                        continue
                    stack.append((ck, cu))

            except Exception as e:
                item = k or "UNBEKANNT"
                logger.error(f"Fehler bei der Verarbeitung von Sub-Issue {item}: {e}", exc_info=True)
                continue

    def _log_final_failures(self):
        """
        Protokolliert alle Issues, die auch nach dem zweiten Versuch noch
        fehlerhaft sind, in eine separate Log-Datei für eine mögliche
        manuelle Nachverfolgung.
        """
        if not self.issues_to_retry: return
        logger.info(f"Schreibe {len(self.issues_to_retry)} endgültig fehlgeschlagene Issues in '{ISSUE_LOG_FILE}'")
        existing_keys = set()
        if os.path.exists(ISSUE_LOG_FILE):
            with open(ISSUE_LOG_FILE, 'r') as f:
                existing_keys = {line.strip() for line in f}
        with open(ISSUE_LOG_FILE, 'a') as f:
            for key in self.issues_to_retry:
                if key not in existing_keys:
                    f.write(f"{key}\n")

    def login(self):
        """
        Führt den Login-Prozess durch und initialisiert den WebDriver.

        Verwendet die in der Instanz gespeicherten Konfigurationsdaten
        (URL, E-Mail, Passwort) und den LoginHandler.

        Returns:
            bool: True bei Erfolg, andernfalls False.
        """
        logger.info("Starte Login-Prozess...")
        # Nutzt self.pwd, das im Konstruktor geladen wurde
        login_success = self.login_handler.login(self.url, self.email, self.pwd)
        if not login_success:
            logger.error("Login fehlgeschlagen. Breche ab.")
            return False

        # Speichert den initialisierten driver für spätere Verwendung
        self.driver = self.login_handler.driver
        return True


    def run(self, skip_login=False):
        """
        Orchestriert den gesamten Scraping-Prozess für das in der Instanz
        konfigurierte Start-Issue.

        Der Ablauf ist wie folgt:
        1.  Führt den Login durch (falls nicht übersprungen).
        2.  Startet Phase 1: Ein erster, vollständiger Durchlauf des Issue-Baums.
            Alle dabei fehlschlagenden Issues werden gesammelt.
        3.  Startet Phase 2: Ein zweiter Durchlauf (Retry) nur für die zuvor
            gesammelten, fehlerhaften Issues.
        4.  Protokolliert alle Issues, die auch in Phase 2 noch fehlschlagen.
        5.  Ruft die Anreicherungsmethode auf, um die Parent-Links in den
            JSON-Dateien zu ergänzen.
        """
        try:
            self.issues_to_retry.clear()
            if not skip_login:
                if not self.login():
                    return

            issue_key = self.url.split('/browse/')[1]
            logger.info(f"Beginne mit Start-Issue: {issue_key}")

            # --- PHASE 1: Erster Durchlauf ---
            logger.info("--- Starte 1. Scraping-Durchlauf ---")
            issue_data = self.extract_and_save_issue_data(self.url, issue_key)
            if issue_data:
                self.process_related_issues(issue_data, self.url)

            # --- PHASE 2: Zweiter Durchlauf (Retry) ---
            if self.issues_to_retry:
                logger.info(f"\n--- Starte 2. Scraping-Durchlauf (Retry) für {len(self.issues_to_retry)} Issue(s) ---")
                retries = self.issues_to_retry.copy()
                self.issues_to_retry.clear()
                for key, url in retries.items():
                    retried_data = self.extract_and_save_issue_data(url, key, is_retry=True)
                    if retried_data:
                        self.process_related_issues(retried_data, url, is_retry=True)
                logger.info("--- Retry-Durchlauf beendet. ---")

            # --- PHASE 3: Finale Protokollierung ---
            self._log_final_failures()

            self._enrich_issues_with_parent_links()
            logger.info(f"\nScraping für Epic {issue_key} abgeschlossen. Insgesamt {len(self.processed_issues)} Issues erfolgreich verarbeitet.")

        except Exception as e:
            logger.error(f"Ein unerwarteter Fehler im run-Durchlauf ist aufgetreten: {e}")
            import traceback
            traceback.print_exc()

    def _enrich_issues_with_parent_links(self):
        """
        Reichert die gescrapeten Issues mit Parent-Links an.

        Diese Methode liest alle in der aktuellen Sitzung verarbeiteten Issues,
        identifiziert die darin enthaltenen Kind-Beziehungen und schreibt
        einen `parent_link` in die jeweilige JSON-Datei des Kind-Issues.
        Dieser Ansatz ist effizient, da er nicht das gesamte Verzeichnis,
        sondern nur die relevanten Dateien verarbeitet.
        """
        logger.info("--- Starte Anreicherung der Issues mit Parent-Links ---")
        if not self.processed_issues:
            logger.info("Keine Issues in dieser Sitzung verarbeitet, überspringe Anreicherung.")
            return

        # 1. Erstelle eine "To-Do-Liste" der Anreicherungen
        enrichment_map = {}
        base_url = self.url.split('/browse/')[0] + '/browse/'
        logger.info(f"Analysiere {len(self.processed_issues)} verarbeitete Issues, um Beziehungen zu erstellen...")

        for parent_key in self.processed_issues:
            file_path = os.path.join(JIRA_ISSUES_DIR, f"{parent_key}.json")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    parent_data = json.load(f)

                if 'issue_links' in parent_data and parent_data['issue_links']:
                    # Erstelle die Informationen für den parent_link
                    parent_link_data = {
                        "key": parent_key,
                        "url": base_url + parent_key
                    }
                    # Füge jedes Kind-Issue zur "To-Do-Liste" hinzu
                    for link in parent_data['issue_links']:
                        child_key = link.get('key')
                        if child_key:
                            enrichment_map[child_key] = parent_link_data

            except FileNotFoundError:
                logger.info(f"Datei {file_path} nicht gefunden, obwohl als verarbeitet markiert. Überspringe für Parent-Link-Analyse.")
            except json.JSONDecodeError:
                logger.info(f"Fehler beim Lesen der JSON-Datei {file_path}. Überspringe für Parent-Link-Analyse.")

        if not enrichment_map:
            logger.info("Keine Kind-Beziehungen gefunden. Anreicherung nicht notwendig.")
            return

        # 2. Arbeite die "To-Do-Liste" ab und reichere die Kind-Dateien an
        logger.info(f"Reichere {len(enrichment_map)} Kind-Issues gezielt mit Parent-Links an...")
        enriched_count = 0
        for child_key, parent_info in enrichment_map.items():
            child_file_path = os.path.join(JIRA_ISSUES_DIR, f"{child_key}.json")
            try:
                # Prüfe, ob die Datei des Kind-Issues überhaupt existiert
                if os.path.exists(child_file_path):
                    # Lese, aktualisiere und schreibe die Datei in einem Vorgang
                    with open(child_file_path, 'r+', encoding='utf-8') as f:
                        child_data = json.load(f)
                        child_data['parent_link'] = parent_info
                        # Gehe zum Anfang der Datei zurück, um sie zu überschreiben
                        f.seek(0)
                        json.dump(child_data, f, indent=4, ensure_ascii=False)
                        f.truncate() # Kürze die Datei, falls der neue Inhalt kürzer ist
                    enriched_count += 1
                else:
                    logger.info(f"Kind-Issue {child_key} wurde nicht gescraped, daher keine Anreicherung möglich.")
            except Exception as e:
                logger.info(f"Unerwarteter Fehler beim Anreichern von {child_key}: {e}")

        logger.info(f"--- Anreicherung abgeschlossen. {enriched_count} von {len(enrichment_map)} möglichen Issues erfolgreich mit Parent-Links versehen. ---")
