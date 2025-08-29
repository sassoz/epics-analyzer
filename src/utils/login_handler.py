# -*- coding: utf-8 -*-
r"""
Windows-first Selenium login handler for Jira behind a corporate proxy (Telekom/MWG).

Key features
------------
- Ensures Selenium <-> ChromeDriver uses direct loopback (NO_PROXY for localhost).
- Reuses your real Chrome profile to inherit SSO, proxy, and cert trust.
- Handles 3 auth paths:
  1) Already signed in (issue content present)
  2) Microsoft 365 / Azure AD login (loginfmt -> passwd -> stay signed in)
  3) Classic Jira username/password form
- Detects Telekom Secure Web Gateway ("mwg-internal") and fails fast with screenshot.

Optional environment variables
------------------------------
JIRA_HEADLESS=true|false           # default: false
CHROME_USER_DATA_DIR=<path>        # default: %USERPROFILE%\AppData\Local\Google\Chrome\User Data
CHROME_PROFILE_DIRECTORY=Default   # e.g., "Default", "Profile 1"
CORP_PROXY=http://sia-lb.telekom.de:8080
JIRA_PROXY_INLINE=true|false       # if true, set Chrome --proxy-server (Chrome ONLY), never via env
JIRA_LOGIN_TIMEOUT=40              # seconds
"""

import os
import time
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class JiraLoginHandler:
    def __init__(self, headless: Optional[bool] = None):
        self.driver: Optional[webdriver.Chrome] = None
        # Read env overrides
        if headless is None:
            headless_env = os.getenv("JIRA_HEADLESS", "false").lower()
            headless = headless_env in ("1", "true", "yes", "y")
        self.headless = headless
        # Keep a default timeout generous for corporate redirects
        self.timeout = int(os.getenv("JIRA_LOGIN_TIMEOUT", "40"))

    # --------------------------- Browser setup --------------------------- #

    def _ensure_loopback_no_proxy(self):
        """Guarantee Selenium's local control channel does NOT pass through the corp proxy."""
        loopback = "localhost,127.0.0.1,::1"
        existing = os.environ.get("NO_PROXY", "")
        merged = ",".join([p for p in [existing, loopback] if p and p.strip()])
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged  # some libs read lowercase
        # Do NOT rely on HTTP_PROXY/HTTPS_PROXY env for Chrome. If needed, we set Chrome-only flag.
        logger.info("NO_PROXY set to: %s", merged)

    def _windows_chrome_profile_dir(self) -> str:
        user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        return os.path.join(user_profile, r"AppData\Local\Google\Chrome\User Data")

    def init_browser(self):
        """Initialize Chrome with Windows profile reuse and sane defaults."""
        self._ensure_loopback_no_proxy()

        options = Options()
        if self.headless:
            # Headless is often problematic for SSO; off by default.
            options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        # Ensure Chrome itself bypasses proxy for loopback
        options.add_argument("--proxy-bypass-list=<-loopback>")

        # Reuse your real Chrome profile so SSO/proxy/certs carry over
        user_data_dir = os.getenv("CHROME_USER_DATA_DIR", self._windows_chrome_profile_dir())
        profile_dir = os.getenv("CHROME_PROFILE_DIRECTORY", "Default")
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_dir}")

        # Optional: set corp proxy for Chrome PAGE traffic (not Selenium control channel)
        if os.getenv("JIRA_PROXY_INLINE", "false").lower() in ("1", "true", "yes", "y"):
            proxy = os.getenv("CORP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            if proxy:
                options.add_argument(f"--proxy-server={proxy}")
                logger.info("Chrome page proxy set: %s", proxy)
            else:
                logger.info("JIRA_PROXY_INLINE enabled but no proxy value set. Skipping.")

        # IMPORTANT: Do NOT spoof a macOS user-agent on Windows (it triggers security checks)
        # Leave default UA so SSO/Kerberos/NTLM remains happy.

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(max(60, self.timeout))
            logger.info("Chrome initialized (headless=%s) with profile: %s / %s", self.headless, user_data_dir, profile_dir)
        except WebDriverException as e:
            logger.error("Failed to start ChromeDriver. Check that Chrome & matching driver are installed. %s", e)
            raise
        return self.driver

    # --------------------------- Utility helpers --------------------------- #

    def _is_blocked_by_mwg(self) -> bool:
        if not self.driver:
            return False
        title = (self.driver.title or "").lower()
        src = (self.driver.page_source or "").lower()
        return "mwg-internal" in src or "telekom it security information" in title

    def _wait(self, by, selector, timeout=None):
        return Wait(self.driver, timeout or self.timeout).until(EC.presence_of_element_located((by, selector)))

    def _click_if_present(self, by, selector, timeout=3) -> bool:
        try:
            el = Wait(self.driver, timeout).until(EC.element_to_be_clickable((by, selector)))
            el.click()
            return True
        except Exception:
            return False

    def _send_if_present(self, by, selector, value, timeout=3) -> bool:
        try:
            el = Wait(self.driver, timeout).until(EC.presence_of_element_located((by, selector)))
            el.clear()
            el.send_keys(value)
            return True
        except Exception:
            return False

    def _save_error_artifacts(self, name_prefix="login_error"):
        if not self.driver:
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        try:
            self.driver.save_screenshot(f"{name_prefix}_{ts}.png")
        except Exception:
            pass
        try:
            with open(f"{name_prefix}_{ts}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source or "")
        except Exception:
            pass

    # --------------------------- Login flows --------------------------- #

    def _already_logged_in(self) -> bool:
        """Success if the Jira issue content (or a core Jira container) is present."""
        try:
            # Try common Jira DC containers first
            Wait(self.driver, 5).until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "issue-content")),
                    EC.presence_of_element_located((By.ID, "jira")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#ghx-content-main")),
                )
            )
            logger.info("Detected logged-in Jira session.")
            return True
        except TimeoutException:
            return False

    def _try_ms365_login(self, email: str, password: str) -> bool:
        """Attempt Microsoft 365 / Azure AD login."""
        try:
            # Email (loginfmt)
            if self._send_if_present(By.NAME, "loginfmt", email, timeout=10):
                self._click_if_present(By.ID, "idSIButton9", timeout=10)  # Next
                time.sleep(0.6)

            # Password
            if self._send_if_present(By.NAME, "passwd", password, timeout=10):
                self._click_if_present(By.ID, "idSIButton9", timeout=10)  # Sign in
                time.sleep(0.6)

            # "Stay signed in?" dialog
            self._click_if_present(By.ID, "idBtn_Back", timeout=5) or self._click_if_present(By.ID, "idSIButton9", timeout=5)

            # Some tenants show "Use your Windows account" or similar button
            # Try a very loose text match
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for b in buttons:
                    if "windows" in (b.text or "").lower():
                        b.click()
                        time.sleep(0.6)
                        break
            except Exception:
                pass

            # After MS login, Jira should load/redirect back
            return self._already_logged_in()
        except Exception as e:
            logger.info("MS365 login flow did not complete: %s", e)
            return False

    def _try_jira_basic_login(self, email: str, password: str) -> bool:
        """Attempt classic Jira local login form."""
        try:
            # Common Jira DC selectors
            # Username field
            if not (self._send_if_present(By.ID, "login-form-username", email, timeout=5) or
                    self._send_if_present(By.NAME, "username", email, timeout=5) or
                    self._send_if_present(By.CSS_SELECTOR, "input[type='email']", email, timeout=5)):
                return False

            # Password field
            if not (self._send_if_present(By.ID, "login-form-password", password, timeout=5) or
                    self._send_if_present(By.NAME, "password", password, timeout=5) or
                    self._send_if_present(By.CSS_SELECTOR, "input[type='password']", password, timeout=5)):
                return False

            # Submit
            if not (self._click_if_present(By.ID, "login", timeout=5) or
                    self._click_if_present(By.ID, "login-form-submit", timeout=5) or
                    self._click_if_present(By.CSS_SELECTOR, "button[type='submit']", timeout=5)):
                # Try pressing Enter on password field
                try:
                    self.driver.switch_to.active_element.send_keys(u"\ue007")
                except Exception:
                    pass

            return self._already_logged_in()
        except Exception as e:
            logger.info("Jira basic login flow did not complete: %s", e)
            return False

    # --------------------------- Public API --------------------------- #

    def login(self, url: str, email: str, password: str) -> bool:
        """
        Orchestrate the full login.
        Returns True if we land on a logged-in Jira page, else False (and saves artifacts).
        """
        if not self.driver:
            self.init_browser()

        logger.info("Navigating to Jira URL: %s", url)
        self.driver.get(url)

        # Fail fast if blocked by MWG
        if self._is_blocked_by_mwg():
            logger.error("Blocked by Telekom Secure Web Gateway (MWG) while opening Jira.")
            self._save_error_artifacts("blocked_mwg")
            return False

        # Case 1: already signed in
        if self._already_logged_in():
            return True

        # Case 2: Microsoft 365 / Azure AD
        if self._try_ms365_login(email, password):
            return True

        # Case 3: Classic Jira local login
        if self._try_jira_basic_login(email, password):
            return True

        # Still not in: check again for MWG or show generic failure
        if self._is_blocked_by_mwg():
            logger.error("Blocked by MWG during login redirect chain.")
        else:
            logger.error("Login did not complete successfully. Saving artifacts.")
        self._save_error_artifacts("login_error")
        return False

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        finally:
            self.driver = None
