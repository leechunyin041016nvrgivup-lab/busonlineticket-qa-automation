"""
utils/driver_factory.py
───────────────────────
Creates and configures Selenium WebDriver instances.
Supports Chrome, Firefox, and Edge.

Headless/visible behaviour is driven by config/settings.py:
  UI_MODE=visible   → browser window shown (default)
  UI_MODE=headless  → no window (CI-friendly)
  UI_MODE=fast      → visible with reduced sleeps
  BROWSER=firefox   → swap browser

CI vs Local driver resolution
──────────────────────────────
In CI (GitHub Actions), the CHROMEDRIVER_PATH env var is set to the binary
installed by the browser-actions/setup-chrome action. We use that directly.
Locally, webdriver-manager downloads and manages the correct version.

Anti-bot-detection
──────────────────
Several flags are set to make headless Chrome look like a real browser.
Some sites (including BusOnlineTicket) detect headless Chrome via the
navigator.webdriver JS property or the default headless user-agent and
refuse to render the page properly. These flags suppress those signals.
"""

import os
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.service  import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service    import Service as EdgeService
from selenium.webdriver.chrome.options  import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options    import Options as EdgeOptions

from config.settings import BROWSER, HEADLESS, PAGE_LOAD_TIMEOUT


def _get_chromedriver_path() -> str | None:
    """
    Resolve the chromedriver binary path.

    Priority:
      1. CHROMEDRIVER_PATH env var  — set explicitly in qa.yml for CI
      2. 'chromedriver' on PATH     — works if already installed system-wide
      3. None                       — fall back to webdriver-manager
    """
    explicit = os.getenv("CHROMEDRIVER_PATH")
    if explicit and os.path.isfile(explicit):
        return explicit

    on_path = shutil.which("chromedriver")
    if on_path:
        return on_path

    return None  # fall back to webdriver-manager


def get_driver() -> webdriver.Remote:
    """
    Instantiate and return a configured WebDriver.
    The browser window is maximised automatically.
    """
    browser = BROWSER.lower()

    if browser == "chrome":
        opts = ChromeOptions()

        if HEADLESS:
            opts.add_argument("--headless=new")

        # ── Window / display ────────────────────────────────────────────────
        opts.add_argument("--start-maximized")
        opts.add_argument("--window-size=1920,1080")    # explicit size in headless

        # ── CI stability ────────────────────────────────────────────────────
        opts.add_argument("--no-sandbox")               # required in CI containers
        opts.add_argument("--disable-dev-shm-usage")    # prevents shared-mem crashes in CI
        opts.add_argument("--disable-gpu")              # avoids GPU errors in headless

        # ── Anti-bot-detection ───────────────────────────────────────────────
        # Sites like BusOnlineTicket detect headless Chrome via:
        #   • navigator.webdriver == true  (suppressed below)
        #   • Default headless User-Agent  (spoofed below)
        #   • Chrome automation infobar    (hidden below)
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--lang=en-US,en")
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        opts.add_experimental_option(
            "excludeSwitches", ["enable-logging", "enable-automation"]
        )
        opts.add_experimental_option("useAutomationExtension", False)

        # ── Misc ─────────────────────────────────────────────────────────────
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-popup-blocking")

        # ── Driver resolution ─────────────────────────────────────────────────
        cd_path = _get_chromedriver_path()
        if cd_path:
            service = ChromeService(executable_path=cd_path)
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            service = ChromeService(ChromeDriverManager().install())

        driver = webdriver.Chrome(service=service, options=opts)

        # Patch navigator.webdriver to undefined so JS cannot detect automation
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )

    elif browser == "firefox":
        opts = FirefoxOptions()
        if HEADLESS:
            opts.add_argument("--headless")

        ff_path = shutil.which("geckodriver")
        if ff_path:
            service = FirefoxService(executable_path=ff_path)
        else:
            from webdriver_manager.firefox import GeckoDriverManager
            service = FirefoxService(GeckoDriverManager().install())

        driver = webdriver.Firefox(service=service, options=opts)
        driver.maximize_window()

    elif browser == "edge":
        opts = EdgeOptions()
        if HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument("--start-maximized")

        from webdriver_manager.microsoft import EdgeChromiumDriverManager
        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=opts)

    else:
        raise ValueError(
            f"Unsupported browser: '{browser}'. Use chrome | firefox | edge."
        )

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver