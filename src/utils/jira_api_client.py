# src/utils/jira_api_client.py
import os
import requests
from pathlib import Path

def _load_dotenv():
    for d in [Path.cwd(), *Path.cwd().parents]:
        p = d / ".env"
        if not p.exists():
            continue
        try:
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass
        break

class JiraApiClient:
    """
    Thin wrapper around Jira REST API v2 using a Bearer token.
    Expects JIRA_API_TOKEN or JIRA_TOKEN to be set (can live in a .env file).
    """
    def __init__(self, base_url="https://jira.telekom.de", token=None, timeout=60):
        _load_dotenv()
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/rest/api/2"
        self.browse = f"{self.base_url}/browse"
        self.timeout = timeout

        token = token or os.getenv("JIRA_API_TOKEN") or os.getenv("JIRA_TOKEN")
        if not token:
            raise RuntimeError("No API token found. Set JIRA_API_TOKEN (or JIRA_TOKEN).")

        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        })

    def ping(self):
        r = self.s.get(f"{self.api}/myself", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_issue(self, key, fields=None, expand=None):
        params = {}
        if fields: params["fields"] = fields
        if expand: params["expand"] = expand
        r = self.s.get(f"{self.api}/issue/{key}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def search(self, jql, fields=None, max_results=500):
        """
        Robust JQL search: try GET first (often allowed behind corp proxies),
        then fall back to POST. Return [] on 400 instead of raising.
        """
        params = {"jql": jql, "maxResults": max_results}
        if fields:
            params["fields"] = fields

        # 1) Try GET
        r = self.s.get(f"{self.api}/search", params=params, timeout=self.timeout)
        if r.status_code == 200:
            return r.json().get("issues", [])
        if r.status_code == 400:
            return []

        # 2) Fallback: POST
        payload = {"jql": jql, "maxResults": max_results}
        if fields:
            payload["fields"] = fields
        r = self.s.post(f"{self.api}/search", json=payload, timeout=self.timeout)
        if r.status_code == 200:
            return r.json().get("issues", [])
        if r.status_code == 400:
            return []

        r.raise_for_status()
