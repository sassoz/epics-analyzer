import os, inspect
import utils.jira_api_client as m
from utils.jira_api_client import JiraApiClient

print("MODULE FILE:", m.__file__)
print("JIRA_CF_EPIC_LINK =", os.getenv("JIRA_CF_EPIC_LINK"))

# Show the public attributes on the class so we see if 'search' exists
print("JiraApiClient attrs:", [a for a in dir(JiraApiClient) if not a.startswith("_")])

# If 'search' exists, execute the three queries
if hasattr(JiraApiClient, "search"):
    c = JiraApiClient()
    print("parent =", len(c.search('parent = "SDN-24421"', fields="key")))
    print('Epic Link =', len(c.search('"Epic Link" = "SDN-24421"', fields="key")))
    print("customfield_10008 =", len(c.search('customfield_10008 = "SDN-24421"', fields="key")))
else:
    print("NOTE: 'search' method not found on JiraApiClient. You may be importing a different copy.")
