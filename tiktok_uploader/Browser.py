from .cookies import load_cookies_from_file, save_cookies_to_file
from fake_useragent import UserAgent, FakeUserAgentError
import undetected_chromedriver as uc
import threading, os, ssl
import certifi
from packaging.version import Version

_CERT_SETUP_DONE = False
_PACKAGING_PATCHED = False


def _ensure_ssl_certificates():
    """Ensure urllib/ssl stack picks up a usable CA bundle (fixes macOS Python installs)."""
    global _CERT_SETUP_DONE
    if _CERT_SETUP_DONE:
        return
    cert_path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", cert_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=cert_path)
    _CERT_SETUP_DONE = True


def _patch_packaging_version():
    """Backfill attrs expected by undetected_chromedriver when distutils.LooseVersion was used."""
    global _PACKAGING_PATCHED
    if _PACKAGING_PATCHED:
        return

    if not hasattr(Version, "version"):
        Version.version = property(lambda self: self.release)  # type: ignore[attr-defined]
    if not hasattr(Version, "vstring"):
        Version.vstring = property(lambda self: self.public)  # type: ignore[attr-defined]
    _PACKAGING_PATCHED = True


WITH_PROXIES = False

class Browser:
    __instance = None

    @staticmethod
    def get():
        if Browser.__instance is None:
            with threading.Lock():
                if Browser.__instance is None:
                    Browser.__instance = Browser()
        return Browser.__instance

    def __init__(self):
        if Browser.__instance is not None:
            raise Exception("This class is a singleton!")
        self.user_agent = ""
        self._driver = None
        options = uc.ChromeOptions()
        # Proxies not supported on login.
        # if WITH_PROXIES:
        #     options.add_argument('--proxy-server={}'.format(PROXIES[0]))
        _patch_packaging_version()
        _ensure_ssl_certificates()
        try:
            self._driver = uc.Chrome(options=options)
        except Exception as exc:
            Browser.__instance = None
            raise RuntimeError("Could not start a Chrome session for login. Please ensure Chrome is installed and retry.") from exc
        Browser.__instance = self
        self.with_random_user_agent()

    def with_random_user_agent(self, fallback=None):
        """Set random user agent.
        NOTE: This could fail with `FakeUserAgentError`.
        Provide `fallback` str to set the user agent to the provided string, in case it fails. 
        If fallback is not provided the exception is re-raised"""

        try:
            self.user_agent = UserAgent().random
        except FakeUserAgentError as e:
            if fallback:
                self.user_agent = fallback
            else:
                raise e

    @property
    def driver(self):
        if self._driver is None:
            raise RuntimeError("Browser session is not available.")
        return self._driver

    def load_cookies_from_file(self, filename):
        cookies = load_cookies_from_file(filename)
        for cookie in cookies:
            self._driver.add_cookie(cookie)
        self._driver.refresh()

    def save_cookies(self, filename: str, cookies:list=None):
        save_cookies_to_file(cookies, filename)


if __name__ == "__main__":
    import os
    # get current relative path of this file.
    print(os.path.dirname(os.path.abspath(__file__)))
