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
"""

from selenium import webdriver
from selenium.webdriver.chrome.service  import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service    import Service as EdgeService
from selenium.webdriver.chrome.options  import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options    import Options as EdgeOptions
from webdriver_manager.chrome    import ChromeDriverManager
from webdriver_manager.firefox   import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

from config.settings import BROWSER, HEADLESS, PAGE_LOAD_TIMEOUT


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
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-popup-blocking")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=opts,
        )

    elif browser == "firefox":
        opts = FirefoxOptions()
        if HEADLESS:
            opts.add_argument("--headless")
        driver = webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()),
            options=opts,
        )
        driver.maximize_window()

    elif browser == "edge":
        opts = EdgeOptions()
        if HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument("--start-maximized")
        driver = webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()),
            options=opts,
        )

    else:
        raise ValueError(
            f"Unsupported browser: '{browser}'. Use chrome | firefox | edge."
        )

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver