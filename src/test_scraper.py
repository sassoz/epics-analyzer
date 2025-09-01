# src/test_scraper.py
import os, json
from utils.jira_scraper_api import JiraScraper
from utils.config import JIRA_ISSUES_DIR

ROOT_ISSUE = "SDN-24685"  # you can change this

url = f"https://jira.telekom.de/browse/{ROOT_ISSUE}"
scraper = JiraScraper(url, email="", scrape_mode="check", check_days=1)

if scraper.login():
    scraper.run()
    print(f"\nProcessed {len(scraper.processed_issues)} issues:")
    for k in sorted(scraper.processed_issues):
        print(" -", k)

    # --- NEW: print user stories under all Epics we scraped ---
    print("\nUser stories found under Epics:")
    epic_count = 0
    story_count = 0

    for k in sorted(scraper.processed_issues):
        p = os.path.join(JIRA_ISSUES_DIR, f"{k}.json")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        if (data.get("issue_type") or "").lower() == "epic":
            epic_count += 1
            children = data.get("issues_in_epic") or []
            if children:
                print(f"\nEPIC {k} — {data.get('summary')}")
                for ch in children:
                    print(f"  - {ch.get('key')}  {ch.get('url','')}")
                    story_count += 1

    print(f"\nTotal: {story_count} issues-in-epic across {epic_count} epics.")
else:
    print("Login failed")
