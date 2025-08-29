# src/utils/jira_scraper_api.py
import os
import json
from datetime import datetime, timedelta


from utils.jira_api_client import JiraApiClient
from utils.config import JIRA_ISSUES_DIR, ISSUE_LOG_FILE, JIRA_LINK_TYPES_TO_FOLLOW
from utils.logger_config import logger

class JiraScraper:
    """
    API-based Jira scraper that mirrors the public surface of the old Selenium JiraScraper:
      - __init__(url, email, ...)
      - login()
      - run(skip_login=False)
      - extract_and_save_issue_data(issue_url, issue_key=None, is_retry=False)
      - process_related_issues(...)
      - _enrich_issues_with_parent_links()

    It writes one JSON per issue in JIRA_ISSUES_DIR with keys used elsewhere, especially:
      - key, summary, issuetype, status, assignee, duedate, fix_versions
      - description (plain text if present)
      - issue_links: [{relation_type, key, url, ...}]
      - parent_link (added in enrichment pass)
    """

    def __init__(self, url, email, model="o3-mini", token_tracker=None, azure_client=None, scrape_mode='true', check_days=7):
        self.url = url
        self.email = email
        self.scrape_mode = scrape_mode
        self.check_days = check_days
        self.processed_issues = set()
        self.issues_to_retry = {}
        self.client = JiraApiClient(base_url=url.split("/browse/")[0])  # e.g. https://jira.telekom.de
        os.makedirs(JIRA_ISSUES_DIR, exist_ok=True)

        # Optional custom fields via env (if you know them in your DC instance)
        self.cf_target_start = os.getenv("JIRA_CF_TARGET_START")  # e.g. customfield_12345
        self.cf_target_end   = os.getenv("JIRA_CF_TARGET_END")    # e.g. customfield_12346
        self.cf_epic_link    = os.getenv("JIRA_CF_EPIC_LINK")     # if parentEpic JQL not available
        self.login_handler = None


    # ---------- utilities ----------
    def _issue_file(self, key): return os.path.join(JIRA_ISSUES_DIR, f"{key}.json")

    def _should_skip_issue(self, issue_key):
        if self.scrape_mode != 'check':  # in 'true' we always refresh
            return False
        p = self._issue_file(issue_key)
        if not os.path.exists(p): return False

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status", "").lower() == "closed":
                logger.info(f"Issue {issue_key} is 'closed' -> skip refresh.")
                return True
            mtime = datetime.fromtimestamp(os.path.getmtime(p))
            if datetime.now() - mtime < timedelta(days=self.check_days):
                logger.info(f"Issue {issue_key} younger than {self.check_days}d -> skip refresh.")
                return True
        except Exception:
            logger.info(f"Couldn't check cache for {issue_key}, will refresh.")
            return False

        logger.info(f"Issue {issue_key} is stale -> refresh.")
        return False

    def _normalize_issue(self, issue):
        f = issue.get("fields", {}) or {}
        assignee = f.get("assignee")
        issuetype = f.get("issuetype") or {}
        status = f.get("status") or {}

        data = {
            "key": issue["key"],
            "url": f'{self.client.browse}/{issue["key"]}',
            "summary": f.get("summary"),
            "description": f.get("description"),
            "issuetype": issuetype.get("name"),
            "status": status.get("name"),
            "assignee": (assignee or {}).get("displayName"),
            "duedate": f.get("duedate"),
            "fix_versions": [v.get("name") for v in (f.get("fixVersions") or [])],
            "created": f.get("created"),
            "updated": f.get("updated"),
            "issue_links": []
        }

        # optional custom fields (if env provided)
        if self.cf_target_start and self.cf_target_start in f:
            data["target_start"] = f.get(self.cf_target_start)
        if self.cf_target_end and self.cf_target_end in f:
            data["target_end"]  = f.get(self.cf_target_end)

        # children via subtasks
        for st in (f.get("subtasks") or []):
            data["issue_links"].append({
                "relation_type": "child",
                "key": st["key"],
                "url": f'{self.client.browse}/{st["key"]}'
            })

        # linked issues: try to categorize "is realized by" as realized_by; else generic 'linked'
        for link in (f.get("issuelinks") or []):
            t = link.get("type") or {}
            name = (t.get("name") or "").lower()
            inward_text = (t.get("inward") or "").lower()
            outward_text = (t.get("outward") or "").lower()

            def _rel_for(text, default="linked"):
                return "realized_by" if "realized" in text or "realised" in text else default

            if "outwardIssue" in link:
                k = link["outwardIssue"]["key"]
                data["issue_links"].append({
                    "relation_type": _rel_for(outward_text or name),
                    "link_type": t.get("name"),
                    "direction": "outward",
                    "key": k,
                    "url": f"{self.client.browse}/{k}"
                })
            if "inwardIssue" in link:
                k = link["inwardIssue"]["key"]
                data["issue_links"].append({
                    "relation_type": _rel_for(inward_text or name),
                    "link_type": t.get("name"),
                    "direction": "inward",
                    "key": k,
                    "url": f"{self.client.browse}/{k}"
                })

        # issues in epic (downstream) if this is an Epic
        if (issuetype.get("name") or "").lower() == "epic":
            children = []
            # Prefer modern JQL first
            try:
                children += self.client.search(f'parentEpic = "{issue["key"]}"',
                                               fields="summary,status,assignee,issuetype")
            except Exception:
                pass
            # Fallback if parentEpic not supported
            if not children and self.cf_epic_link:
                try:
                    children += self.client.search(f'"{self.cf_epic_link}" = "{issue["key"]}"',
                                                   fields="summary,status,assignee,issuetype")
                except Exception:
                    pass

            seen = set()
            for ch in children:
                k = ch["key"]
                if k in seen: continue
                seen.add(k)
                data["issue_links"].append({
                    "relation_type": "issue_in_epic",
                    "key": k,
                    "url": f"{self.client.browse}/{k}"
                })

        return data

    # ---------- public API (mirrors old scraper) ----------
    def login(self):
        """API 'login' = sanity check that token works by calling /myself."""
        logger.info("Checking Jira API token via /myself ...")
        try:
            me = self.client.ping()
            logger.info(f"Authenticated as {me.get('displayName','?')}")
            return True
        except Exception as e:
            logger.error(f"API authentication failed: {e}")
            return False

    def extract_and_save_issue_data(self, issue_url, issue_key=None, is_retry=False):
        if not issue_key:
            issue_key = issue_url.split('/browse/')[1] if '/browse/' in issue_url else None
        if not issue_key:
            logger.warning(f"Could not extract key from URL: {issue_url}")
            return None

        if issue_key in self.processed_issues:
            logger.info(f"{issue_key} already processed in this run; skipping.")
            return None

        # honor cache if 'check'
        if self._should_skip_issue(issue_key):
            try:
                with open(self._issue_file(issue_key), "r", encoding="utf-8") as f:
                    cached = json.load(f)
                self.processed_issues.add(issue_key)
                return cached
            except Exception:
                logger.info(f"{issue_key} was to be skipped but cache unreadable; reloading via API.")

        try:
            logger.info(f"Fetching {issue_key} via REST API" + (" (Retry)" if is_retry else ""))
            raw = self.client.get_issue(issue_key,
                                        fields="summary,description,issuetype,status,assignee,duedate,fixVersions,created,updated,subtasks,issuelinks")
            data = self._normalize_issue(raw)

            # write JSON file
            with open(self._issue_file(issue_key), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            self.processed_issues.add(issue_key)
            return data

        except Exception as e:
            if is_retry:
                logger.warning(f"{issue_key} still failing on retry: {e}")
                self.processed_issues.add(issue_key)  # don't loop forever
                return None
            logger.error(f"Error processing {issue_key}: {e}")
            self.issues_to_retry[issue_key] = issue_url
            return None

    def process_related_issues(self, issue_data, current_url, is_retry=False):
        """
        Iterative DFS to avoid recursion depth errors and infinite loops.
        Uses self.processed_issues as visited set.
        Filters links based on the JIRA_LINK_TYPES_TO_FOLLOW whitelist.
        """
        if not issue_data:
            return

        stack = []
        for rel in issue_data.get("issue_links", []) or []:
            # --- MODIFIED: Only follow whitelisted link types ---
            if rel.get("relation_type") not in JIRA_LINK_TYPES_TO_FOLLOW:
                continue

            k, u = rel.get("key"), rel.get("url")
            if not k or not u:
                continue
            if k in self.processed_issues:
                continue
            stack.append((k, u))

        while stack:
            k, u = stack.pop()
            if k in self.processed_issues:
                continue

            child = self.extract_and_save_issue_data(u, k, is_retry=is_retry)
            if not child:
                continue

            # mark visited immediately
            self.processed_issues.add(k)

            # enqueue its links
            for rel in child.get("issue_links", []) or []:
                # --- MODIFIED: Only follow whitelisted link types ---
                if rel.get("relation_type") not in JIRA_LINK_TYPES_TO_FOLLOW:
                    continue

                ck, cu = rel.get("key"), rel.get("url")
                if not ck or not cu:
                    continue
                if ck in self.processed_issues:
                    continue
                stack.append((ck, cu))

    def _log_final_failures(self):
        if not self.issues_to_retry: return
        logger.info(f"Logging {len(self.issues_to_retry)} final failures to '{ISSUE_LOG_FILE}'")
        existing = set()
        if os.path.exists(ISSUE_LOG_FILE):
            with open(ISSUE_LOG_FILE, 'r') as f:
                existing = {line.strip() for line in f}
        with open(ISSUE_LOG_FILE, 'a') as f:
            for key in self.issues_to_retry:
                if key not in existing:
                    f.write(f"{key}\n")

    def _enrich_issues_with_parent_links(self):
        """
        After traversal, write a 'parent_link' into each child JSON file,
        derived from their parents' issue_links (same behavior as the Selenium version).
        """
        logger.info("--- Enriching child issues with parent_link ---")
        if not self.processed_issues:
            logger.info("No issues processed; skip enrichment.")
            return

        enrichment_map = {}
        base = self.url.split('/browse/')[0] + '/browse/'

        for parent_key in self.processed_issues:
            path = self._issue_file(parent_key)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    parent = json.load(f)
                if parent.get("issue_links"):
                    parent_link = {"key": parent_key, "url": base + parent_key}
                    for link in parent["issue_links"]:
                        child_key = link.get("key")
                        if child_key:
                            enrichment_map[child_key] = parent_link
            except Exception:
                continue

        if not enrichment_map:
            logger.info("No child relationships found; skip enrichment.")
            return

        enriched = 0
        for child_key, parent_link in enrichment_map.items():
            child_path = self._issue_file(child_key)
            if not os.path.exists(child_path): continue
            try:
                with open(child_path, "r+", encoding="utf-8") as f:
                    data = json.load(f)
                    data["parent_link"] = parent_link
                    f.seek(0)
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.truncate()
                enriched += 1
            except Exception as e:
                logger.info(f"Could not enrich {child_key}: {e}")

        logger.info(f"Enrichment done. parent_link written for {enriched} child issues.")

    def run(self, skip_login=False):
        try:
            self.issues_to_retry.clear()
            if not skip_login:
                if not self.login(): return

            start_key = self.url.split('/browse/')[1]
            logger.info(f"Start with {start_key}")

            # Pass 1
            data = self.extract_and_save_issue_data(self.url, start_key)
            if data:
                self.process_related_issues(data, self.url)

            # Retry pass
            if self.issues_to_retry:
                logger.info(f"--- Second pass retry for {len(self.issues_to_retry)} issues ---")
                retry_items = self.issues_to_retry.copy()
                self.issues_to_retry.clear()
                for k, u in retry_items.items():
                    rdata = self.extract_and_save_issue_data(u, k, is_retry=True)
                    if rdata:
                        self.process_related_issues(rdata, u, is_retry=True)

            self._log_final_failures()
            self._enrich_issues_with_parent_links()
            logger.info(f"Done. {len(self.processed_issues)} issues processed.")

        except Exception as e:
            logger.error(f"Run failed: {e}", exc_info=True)
