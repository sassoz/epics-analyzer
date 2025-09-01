import os, json
from utils.config import JIRA_ISSUES_DIR

EPIC = "SDN-24421"  # change if needed

def load(key):
    p = os.path.join(JIRA_ISSUES_DIR, f"{key}.json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

epic = load(EPIC)
if not epic:
    print(f"Not found: {EPIC}.json — run the scraper first.")
    raise SystemExit(1)

children = epic.get("issues_in_epic") or []
print(f"{EPIC} — {len(children)} issues in epic\n")

for ch in children:
    key = ch["key"]
    data = load(key)
    # If traversal didn’t fetch a child yet, we still print the key+URL
    if not data:
        print(f"  - {key:10}  (not cached yet)  {ch.get('url','')}")
        continue

    summary   = data.get("summary","")
    status    = data.get("status","")
    assignee  = data.get("assignee","")
    fixvers   = ", ".join(data.get("fix_versions") or [])
    print(f"  - {key:10}  [{status:12}]  {assignee:25}  {summary}")
    if fixvers:
        print(f"               fixVersions: {fixvers}")
