import json
import time
import os
import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
from .cookies import load_cookies_from_file, save_cookies_to_file

class StealthBrowser:
    def __init__(self, headless=True, proxy=None):
        self.headless = headless
        self.proxy = proxy
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        self.playwright = await async_playwright().start()
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]

        proxy_config = None
        if self.proxy:
            proxy_config = self._parse_proxy(self.proxy)

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
            proxy=proxy_config
        )



        # Create context with stealth settings
        self.context = await self.browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York", # Or match proxy
            device_scale_factor=2,
            has_touch=True,
            is_mobile=False,
            permissions=["geolocation"],
        )

        # Apply CDP Stealth Patches
        await self._apply_stealth(self.context)

        # Load signature scripts
        await self._inject_signature_scripts()

        self.page = await self.context.new_page()

    async def _apply_stealth(self, context: BrowserContext):
        # 1. Override navigator.webdriver
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # 2. Mock chrome object
        await context.add_init_script("""
            window.chrome = {
                runtime: {}
            };
        """)

        # 3. Mock permissions
        await context.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            return window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)

        # 4. Mock plugins (basic)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

    async def _inject_signature_scripts(self):
        # Load JS files from tiktok-signature/javascript
        base_path = os.path.join(os.path.dirname(__file__), "tiktok-signature", "javascript")
        scripts = ["signer.js", "webmssdk.js", "xbogus.js"]
        
        for script in scripts:
            path = os.path.join(base_path, script)
            if os.path.exists(path):
                await self.context.add_init_script(path=path)
            else:
                print(f"Warning: Signature script not found: {path}")

        # Add helper functions
        await self.context.add_init_script("""
            window.generateSignature = function(url) {
                if (typeof window.byted_acrawler === "undefined" || typeof window.byted_acrawler.sign !== "function") {
                    return null;
                }
                return window.byted_acrawler.sign({ url: url });
            };
        """)

    async def load_cookies(self, filename):
        cookies = load_cookies_from_file(filename)
        if cookies:
            # Playwright expects 'sameSite' to be strictly typed or omitted if invalid
            # We might need to clean up cookies from Selenium format
            clean_cookies = []
            for c in cookies:
                # Basic cleanup
                c.pop("expiry", None) # Playwright uses 'expires'
                if "sameSite" in c and c["sameSite"] not in ["Strict", "Lax", "None"]:
                    c.pop("sameSite")
                clean_cookies.append(c)
            
            try:
                await self.context.add_cookies(clean_cookies)
            except Exception as e:
                print(f"Error loading cookies: {e}")

    async def save_cookies(self, filename):
        cookies = await self.context.cookies()
        save_cookies_to_file(cookies, filename)

    async def get_signature(self, url):
        # Ensure we are on a page (even if blank)
        if not self.page:
            self.page = await self.context.new_page()
        
        # We might need to navigate to a domain to set cookies/context correctly for signing?
        # Usually signature generation is purely JS based, but some checks might look at origin.
        # For now, assume we are already on tiktok.com or similar from login/setup.
        
        # Execute signature generation in page context
        try:
            # 1. VerifyFP (can be generated in python or JS, let's use a simple JS one or pass it)
            verify_fp = "verify_k6M3D9v8_5jJ2_4K8L_9N0P_Q1R2S3T4U5V6" # Placeholder or generate dynamic
            
            new_url = f"{url}&verifyFp={verify_fp}"
            
            # 2. Signature
            signature = await self.page.evaluate(f'window.generateSignature("{new_url}")')
            
            # 3. X-Bogus
            signed_url = f"{new_url}&_signature={signature}"
            query_string = signed_url.split("?")[1] if "?" in signed_url else ""
            user_agent = self.user_agent
            
            bogus = await self.page.evaluate(f'window.generateBogus("{query_string}", "{user_agent}")')
            
            return {
                "signature": signature,
                "verify_fp": verify_fp,
                "x_bogus": bogus,
                "signed_url": f"{signed_url}&X-Bogus={bogus}"
            }
        except Exception as e:
            print(f"Signature generation failed: {e}")
            return None

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def _parse_proxy(self, proxy_str):
        if "@" in proxy_str:
            # Format: user:pass@host:port or http://user:pass@host:port
            if "://" in proxy_str:
                protocol, rest = proxy_str.split("://", 1)
            else:
                protocol = "http"
                rest = proxy_str
            
            auth, server = rest.split("@", 1)
            username, password = auth.split(":", 1)
            
            return {
                "server": f"{protocol}://{server}",
                "username": username,
                "password": password
            }
        else:
            # Format: host:port or http://host:port
            return {"server": proxy_str}
