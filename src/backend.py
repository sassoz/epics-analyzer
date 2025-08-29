# backend.py
import os, sys, json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# Projekt-Root = eine Ebene über src
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from utils.jira_scraper_api import JiraScraper  # <- API-based scraper
from utils.config import JIRA_ISSUES_DIR

# ---- env helpers (load .env without deps) ----
def load_dotenv():
    for d in [REPO_ROOT, *REPO_ROOT.parents]:
        p = d / ".env"
        if p.exists():
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://jira.telekom.de").rstrip("/")
# Token is read inside JiraApiClient (JIRA_API_TOKEN or JIRA_TOKEN from .env)

app = FastAPI(title="BE Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunRequest(BaseModel):
    issue: str  # "SDN-27638" or full URL
    html_summary: Optional[bool] = False
    scrape_mode: Optional[str] = "true"  # "true" or "check"

class RunResponse(BaseModel):
    processed_count: int
    root: dict
    output_files: list[str]

@app.post("/api/run", response_model=RunResponse)
def run_scraper(req: RunRequest):
    # Normalize issue key/URL
    issue_key = req.issue
    if "/browse/" in issue_key:
        issue_key = issue_key.split("/browse/")[1].split("?")[0]

    issue_url = f"{JIRA_BASE_URL}/browse/{issue_key}"

    scraper = JiraScraper(
        url=issue_url,
        email="",  # not used by API-based scraper
        scrape_mode=req.scrape_mode,
        check_days=7
    )
    ok = scraper.login()
    if not ok:
        raise ValueError("Jira API authentication failed – check token (.env JIRA_API_TOKEN or JIRA_TOKEN).")

    scraper.run(skip_login=True)

    # read root JSON
    root_file = Path(JIRA_ISSUES_DIR) / f"{issue_key}.json"
    if not root_file.exists():
        raise RuntimeError(f"Root JSON not produced for {issue_key}.")
    root = json.loads(root_file.read_text(encoding="utf-8"))

    # collect produced files (flat)
    out_files = []
    for p in Path(JIRA_ISSUES_DIR).glob("*.json"):
        out_files.append(str(p))

    return RunResponse(
        processed_count=len(scraper.processed_issues),
        root=root,
        output_files=out_files
    )
