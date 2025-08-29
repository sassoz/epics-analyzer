from utils.jira_scraper_api import JiraScraper

issue_key = "SDN-27638"
url = f"https://jira.telekom.de/browse/{issue_key}"

scraper = JiraScraper(url, email="", scrape_mode="check", check_days=1)
if scraper.login():
    scraper.run()
    print(f"\nProcessed {len(scraper.processed_issues)} issues:")
    for k in list(scraper.processed_issues)[:10]:
        print(" -", k)
else:
    print("Login failed")
