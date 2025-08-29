import os, sys, json, requests

BASE_URL = os.getenv("JIRA_BASE_URL", "https://jira.telekom.de")
TOKEN    = os.getenv("JIRA_TOKEN")
KEY      = sys.argv[1] if len(sys.argv) > 1 else os.getenv("JIRA_ISSUE", "SDN-27638")
VERIFY   = os.getenv("JIRA_CA_BUNDLE") or True  # point to corp CA .pem if needed

if not TOKEN:
    sys.exit("ERROR: set JIRA_TOKEN environment variable (bearer token).")

S = requests.Session()
S.headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})

def get(path, **params):
    r = S.get(f"{BASE_URL}{path}", params=params or None, timeout=30, verify=VERIFY)
    r.raise_for_status()
    return r.json()

def search_jql(jql, fields="key,summary,issuetype,status,assignee,fixVersions", max_results=100):
    out = []
    start = 0
    while True:
        r = S.get(f"{BASE_URL}/rest/api/2/search", params={
            "jql": jql, "fields": fields, "startAt": start, "maxResults": max_results
        }, timeout=30, verify=VERIFY)
        if r.status_code == 400:
            # invalid JQL/field — return empty rather than crash
            return []
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("issues", []))
        start += data.get("maxResults", 0)
        if start >= data.get("total", 0):
            break
    return out

def epic_link_field_id():
    # Find the custom field id for "Epic Link" on DC
    for f in get("/rest/api/2/field"):
        name = (f.get("name") or "").lower()
        if name == "epic link":
            return f["id"]  # e.g., "customfield_10008"
    return None

def slim(issue):
    f = issue["fields"]
    return {
        "key": issue["key"],
        "summary": f.get("summary"),
        "type": f.get("issuetype", {}).get("name"),
        "status": f.get("status", {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "fixVersions": [v.get("name") for v in f.get("fixVersions") or []],
    }

# 1) Root issue info
root = get(f"/rest/api/2/issue/{KEY}", fields="summary,issuetype,status,assignee,fixVersions")
root_info = slim({"key": KEY, "fields": root["fields"]})

# 2) Children via parent
children_parent = search_jql(f'parent = "{KEY}"')

# 3) Children via Epic Link (try field name, else fallback to customfield id)
children_epic = search_jql(f'"Epic Link" = "{KEY}"')  # many DC instances support the literal
if not children_epic:
    cf = epic_link_field_id()
    if cf:
        children_epic = search_jql(f'cf[{cf.split("_")[-1]}] = "{KEY}"')

# 4) Generic issue links (filter out the root itself)
children_links = [i for i in search_jql(f'issue in linkedIssues("{KEY}")') if i["key"] != KEY]

# Merge (by key) and print
merged = {}
for bucket in (children_parent, children_epic, children_links):
    for it in bucket:
        merged[it["key"]] = slim(it)

result = {
    "root": root_info,
    "children": list(merged.values()),
    "counts": {
        "parent": len(children_parent),
        "epicLink": len(children_epic),
        "linkedIssues": len(children_links),
        "unique_children": len(merged),
    }
}

print(json.dumps(result, indent=2, ensure_ascii=False))
