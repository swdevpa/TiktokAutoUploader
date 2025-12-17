import json
import time
import os
import asyncio
import random
import math
from playwright.async_api import async_playwright, Page, BrowserContext
from .cookies import load_cookies_from_file, save_cookies_to_file

class SignupBrowser:
    def __init__(self, headless=True, proxy=None, guest_mode=False, timezone_id=None, storage_state_path=None):
        self.headless = headless
        self.proxy = proxy
        self.guest_mode = guest_mode
        self.timezone_id = timezone_id
        self.storage_state_path = storage_state_path
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.37 Safari/537.36"

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



        # Detect proxy settings (timezone, locale)
        timezone_id = "America/New_York"
        locale = "en-US"
        geolocation = None
        
        detected_settings = None
        if proxy_config:
            print("Detecting proxy location...")
            try:
                detected_settings = await self._detect_proxy_settings(proxy_config)
            except Exception as e:
                print(f"Failed to detect proxy settings: {e}")
                
        if detected_settings:
            # Use detected locale/geo
            locale = detected_settings.get("locale", locale)
            if "lat" in detected_settings and "lon" in detected_settings:
                geolocation = {"latitude": detected_settings["lat"], "longitude": detected_settings["lon"]}
            
            # Use detected timezone UNLESS manual override is provided
            if self.timezone_id:
                print(f"Using manual timezone override: {self.timezone_id} (Detected: {detected_settings.get('timezone')})")
                timezone_id = self.timezone_id
            else:
                timezone_id = detected_settings.get("timezone", timezone_id)
            
            print(f"Final Configuration: {timezone_id} | {locale}")
            
        elif self.timezone_id:
             print(f"Using manual timezone override (Detection failed): {self.timezone_id}")
             timezone_id = self.timezone_id

        # Store intended locale for later API calls
        self.locale = locale

        # Create context with stealth settings
        context_options = {
            "user_agent": self.user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "locale": locale,
            "timezone_id": timezone_id,
            "device_scale_factor": 2,
            "has_touch": True,
            "is_mobile": False,
            "permissions": ["geolocation"],
            # "extra_http_headers": {
            #     "DNT": "1" # DNT: 1 means "Do Not Track" - DISABLED
            # }
        }
        
        if geolocation:
            context_options["geolocation"] = geolocation

        # Load storage state if provided and exists (JSON format)
        if self.storage_state_path and os.path.exists(self.storage_state_path) and self.storage_state_path.endswith(".json"):
             try:
                 with open(self.storage_state_path, "r") as f:
                     json.load(f) # Validate JSON
                 context_options["storage_state"] = self.storage_state_path
                 print(f"Loaded session from JSON: {self.storage_state_path}")
             except Exception as e:
                 print(f"Error loading storage_state JSON: {e}")

        self.context = await self.browser.new_context(**context_options)

        # Apply CDP Stealth Patches
        await self._apply_stealth(self.context)


        # 11. Setup isolated signer page
        await self._setup_signer_page()

        self.page = await self.context.new_page()

    async def _apply_stealth(self, context: BrowserContext):
        pass
        # 1. Remove webdriver property - DISABLED (Local execution)
        # await context.add_init_script("""
        #     Object.defineProperty(navigator, 'webdriver', {
        #         get: () => undefined
        #     });
        # """)

        # 2. Mock chrome object - DISABLED (Local execution)
        # await context.add_init_script("""
        #     window.chrome = {
        #         runtime: {}
        #     };
        # """)

        # 3. Mock permissions - DISABLED (Local execution)
        # await context.add_init_script("""
        #     const originalQuery = window.navigator.permissions.query;
        #     return window.navigator.permissions.query = (parameters) => (
        #         parameters.name === 'notifications' ?
        #         Promise.resolve({ state: Notification.permission }) :
        #         originalQuery.apply(navigator.permissions, [parameters])
        #     );
        # """)


        # 4. Mock plugins (basic) - DISABLED (Too aggressive)
        # await context.add_init_script("""
        #     Object.defineProperty(navigator, 'plugins', {
        #         get: () => [1, 2, 3, 4, 5]
        #     });
        # """)


        # 5. WebGL Vendor/Renderer - DISABLED (Too aggressive/mismatch risk)
        # await context.add_init_script("""
        #     const getParameter = WebGLRenderingContext.prototype.getParameter;
        #     WebGLRenderingContext.prototype.getParameter = function(parameter) {
        #         // UNMASKED_VENDOR_WEBGL
        #         if (parameter === 37445) {
        #             return 'Intel Inc.';
        #         }
        #         // UNMASKED_RENDERER_WEBGL
        #         if (parameter === 37446) {
        #             return 'Intel Iris OpenGL Engine';
        #         }
        #         return getParameter(parameter);
        #     };
        # """)

        # 6. Canvas Noise Injection - DISABLED for stability in SignupBrowser
        # await context.add_init_script("""
        # ... (disabled)
        # """)


        # 7. AudioContext Noise - DISABLED for stability in SignupBrowser
        # await context.add_init_script(...)


        # 8. Hardware Concurrency & Memory Spoofing - DISABLED (Stability)
        # await context.add_init_script("""
        #     Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
        #     Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        # """)


        # 9. Font Enumeration Masking (Basic) - DISABLED for stability
        # await context.add_init_script(...)


        # 10. WebRTC IP Leak Protection (Smart Mocking)
        # Instead of disabling (which breaks signup), we mock the API to return no candidates.
        await context.add_init_script("""
            // Keep the original classes just in case, but usually we overwrite.
            const originalRTC = window.RTCPeerConnection;
            
            // Mock RTCPeerConnection to pass "is defined" checks but leak nothing
            window.RTCPeerConnection = function(config) {
                this.localDescription = null;
                this.remoteDescription = null;
                this.iceConnectionState = 'new';
                this.iceGatheringState = 'complete'; // Pretend we are done gathering
                this.signalingState = 'stable';
                
                this.createOffer = async () => ({ type: 'offer', sdp: '' });
                this.createAnswer = async () => ({ type: 'answer', sdp: '' });
                this.setLocalDescription = async () => {};
                this.setRemoteDescription = async () => {};
                this.addIceCandidate = async () => {};
                this.close = () => {};
                this.addEventListener = () => {};
                this.removeEventListener = () => {};
                return this;
            };
            
            // Mock prototypes to look legit
            window.RTCPeerConnection.prototype = originalRTC.prototype;
            
            // Mock Media Devices to return empty list (prevents hardware enumeration leaks)
            if (navigator.mediaDevices) {
                navigator.mediaDevices.enumerateDevices = () => Promise.resolve([
                    { kind: 'audioinput', deviceId: 'default', label: 'Default Audio', groupId: 'default' },
                    { kind: 'videoinput', deviceId: 'default', label: 'Default Video', groupId: 'default' }
                ]);
                navigator.mediaDevices.getUserMedia = () => Promise.reject(new Error("Permission denied"));
            }
        """)


    async def _setup_signer_page(self):
        """
        Creates an isolated page for signature generation to avoid conflicts with main page scripts.
        """
        self.signer_page = await self.context.new_page()
        
        # Block external JS on this page to prevent conflicts and speed up loading
        # BUT: We must allow our own injected scripts to run. 
        # add_init_script runs before anything else, so it should work even if we block network JS.
        await self.signer_page.route("**/*.js", lambda route: route.abort())
        
        # Load scripts content
        base_path = os.path.join(os.path.dirname(__file__), "tiktok-signature", "javascript")
        scripts = ["signer.js", "webmssdk.js", "xbogus.js"]
        
        for script in scripts:
            path = os.path.join(base_path, script)
            if os.path.exists(path):
                # add_init_script is robust against CSP and runs in the page context successfully
                await self.signer_page.add_init_script(path=path)
            else:
                print(f"Warning: Signature script not found: {path}")

        # Add helper functions as init script too
        await self.signer_page.add_init_script("""
            window.generateSignature = function(url) {
                try {
                    if (typeof window.byted_acrawler === "undefined" || typeof window.byted_acrawler.sign !== "function") {
                        return null;
                    }
                    return window.byted_acrawler.sign({ url: url });
                } catch (e) { return null; }
            };
            window.generateBogus = function(url, userAgent) {
                try {
                    if (typeof window.window.sign !== "function") {
                        return null;
                    }
                    return window.window.sign(url, userAgent);
                } catch (e) { return null; }
            };
        """)

        try:
            # Navigate to a simple page on TikTok to set Origin/Cookies and trigger init scripts.
            await self.signer_page.goto("https://www.tiktok.com/legal/page/row/privacy-policy/en", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Signer page navigation warning: {e}")

    async def load_session(self, filename: str = None):
        """
        Loads session from a JSON file (Playwright storageState) OR migrates from legacy pickle.
        """
        if self.guest_mode:
            return

        target_path = filename if filename else self.storage_state_path
        if not target_path:
            return

        if target_path.endswith(".json"):
            if os.path.exists(target_path):
                 # Already loaded in start() via new_context if passed, but valid to check cookies
                 print(f"Session {target_path} loaded.")
            else:
                 # Check migration
                 legacy_path = target_path.replace(".json", ".cookie")
                 if os.path.exists(legacy_path):
                     print(f"Migrating legacy pickle session: {legacy_path} -> {target_path}")
                     await self.load_cookies(legacy_path)
        elif target_path.endswith(".cookie"):
             await self.load_cookies(target_path)

    async def save_session(self, filename: str = None):
        """
        Saves the current session state (Cookies + LocalStorage) to a JSON file.
        """
        target_path = filename if filename else self.storage_state_path
        if not target_path:
            return
            
        if not target_path.endswith(".json") and not target_path.endswith(".cookie"):
            target_path += ".json"

        if target_path.endswith(".cookie"):
             await self.save_cookies(target_path)
             return

        try:
            await self.context.storage_state(path=target_path)
            print(f"Session saved to {target_path} (Cookies + LocalStorage)")
        except Exception as e:
            print(f"Error saving session state: {e}")

    async def load_cookies(self, filename):
        # Legacy support
        if self.guest_mode:
            print("Guest mode enabled: Skipping cookie loading.")
            return

        cookies = load_cookies_from_file(filename)
        if cookies:
            clean_cookies = []
            for c in cookies:
                c.pop("expiry", None)
                if "sameSite" in c and c["sameSite"] not in ["Strict", "Lax", "None"]:
                    c.pop("sameSite")
                clean_cookies.append(c)
            
            try:
                await self.context.add_cookies(clean_cookies)
                print(f"Loaded {len(clean_cookies)} cookies from legacy file.")
            except Exception as e:
                print(f"Error loading cookies: {e}")

    async def save_cookies(self, filename):
        # Legacy support
        cookies = await self.context.cookies()
        save_cookies_to_file(cookies, filename)

    async def get_signature(self, url):
        # Use our isolated signer page
        if not hasattr(self, 'signer_page') or not self.signer_page:
            # Fallback if somehow not initialized, though start() should have done it
            await self._setup_signer_page()
            
        # Check if 'verifyFp' is already in URL
        if "verifyFp=" not in url:
             verify_fp = "verify_k6M3D9v8_5jJ2_4K8L_9N0P_Q1R2S3T4U5V6"
             if "?" in url:
                 new_url = f"{url}&verifyFp={verify_fp}"
             else:
                 new_url = f"{url}?verifyFp={verify_fp}"
        else:
             new_url = url
             try:
                 # Extract verifyFp for return
                 import urllib.parse
                 parsed = urllib.parse.urlparse(new_url)
                 params = urllib.parse.parse_qs(parsed.query)
                 verify_fp = params.get("verifyFp", [""])[0]
             except:
                 verify_fp = ""

        # Execute signature generation in SIGNER context
        try:
            # 2. Signature
            signature = await self.signer_page.evaluate(f'window.generateSignature("{new_url}")')
            
            # 3. X-Bogus
            if "?" in new_url:
                query_string = new_url.split("?", 1)[1]
            else:
                query_string = ""
                
            user_agent = self.user_agent
            bogus = await self.signer_page.evaluate(f'window.generateBogus("{query_string}", "{user_agent}")')
            
            return {
                "signature": signature,
                "verify_fp": verify_fp,
                "x_bogus": bogus,
                "signed_url": f"{new_url}&X-Bogus={bogus}&_signature={signature}"
            }
        except Exception as e:
            print(f"Signature generation failed: {e}")
            return None


    async def request_email_code(self, email):
        """
        Requests a verification code for the given email using the Web API.
        """
        api_url = "https://www.tiktok.com/passport/web/email/send_code/"
        
        # Navigate to home to ensure cookies/fp
        if not self.page.url or "tiktok.com" not in self.page.url:
            try:
                await self.page.goto("https://www.tiktok.com/signup", timeout=30000)
            except:
                pass

        cookies = await self.context.cookies()
        ms_token = next((c["value"] for c in cookies if c["name"] == "msToken"), "")
        did = next((c["value"] for c in cookies if c["name"] == "tt_webid_v2"), "") 
        # s_v_web_id often acts as verifyFp in web context
        existing_fp = next((c["value"] for c in cookies if c["name"] == "s_v_web_id"), "")

        params = {
            "aid": 1459,
            "language": "en",
            "app_language": "en",
            "region": "IE", 
            "msToken": ms_token,
            "account_sdk_source": "web",
            "multi_login": 1,
        }
        if did:
            params["did"] = did
            
        if existing_fp:
            verify_fp = existing_fp
        else:
            # Add random verifyFp if not present in cookies
            chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            verify_fp = "verify_" + "".join(random.choices(chars, k=36))
        
        params["verifyFp"] = verify_fp

        # Build query for signature
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        url_to_sign = f"{api_url}?{query_string}"
        
        sig_data = await self.get_signature(url_to_sign)
        if not sig_data:
            print("[-] Failed to sign request")
            return None
            
        params["X-Bogus"] = sig_data["x_bogus"]
        params["_signature"] = sig_data["signature"]
        
        # Prepare Body
        data = {
            "email": email,
            "type": 34,
            "aid": 1459,
            "mix_mode": 1,
            "fixed_mix_mode": 1,
            "email_logic_type": 2,
            "account_sdk_source": "web"
        }
        if did:
            data["did"] = did
            
        # Setup headers to look authentic
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.user_agent,
            "Referer": "https://www.tiktok.com/signup",
        }
        if hasattr(self, 'locale') and self.locale:
            headers["Accept-Language"] = f"{self.locale},en;q=0.9"

        print(f"Sending code to {email}...")
        try:
            # page.request shares the browser/context proxy and cookies
            response = await self.page.request.post(
                api_url,
                params=params,
                data=data,
                headers=headers
            )
            result = await response.json()
            return result
        except Exception as e:
            print(f"API Request Exception: {e}")
            return None


    async def close(self):
        if hasattr(self, 'signer_page') and self.signer_page:
            try:
                await self.signer_page.close()
            except:
                pass
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

    async def human_click(self, selector):
        """
        Moves mouse to element with a human-like curve and clicks.
        """
        if not self.page:
            return
            
        element = await self.page.wait_for_selector(selector)
        if not element:
            return

        box = await element.bounding_box()
        if not box:
            return

        # Target point (randomized within the element)
        target_x = box["x"] + box["width"] * (0.2 + 0.6 * random.random())
        target_y = box["y"] + box["height"] * (0.2 + 0.6 * random.random())

        # Start point (current mouse position) - Playwright doesn't expose this directly easily,
        # so we assume 0,0 or track it. For now, let's just move from a random edge point if unknown.
        start_x = random.randint(0, 1920)
        start_y = random.randint(0, 1080)
        
        # Generate curve
        steps = random.randint(25, 50)
        points = self._bezier_curve(start_x, start_y, target_x, target_y, steps)
        
        for point in points:
            await self.page.mouse.move(point[0], point[1])
            # Tiny sleep between moves for variable speed
            if random.random() > 0.8:
                await asyncio.sleep(random.uniform(0.001, 0.005))

        # Hesitate before click
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.03, 0.07))
        await self.page.mouse.up()

    async def human_type(self, selector, text):
        """
        Types text with random delays.
        """
        if not self.page:
            return
            
        await self.human_click(selector)
        
        for char in text:
            await self.page.keyboard.type(char)
            # Random delay between keystrokes
            await asyncio.sleep(random.uniform(0.05, 0.15))
            
            # Occasional longer pause
            if random.random() > 0.9:
                await asyncio.sleep(random.uniform(0.2, 0.5))

    def _bezier_curve(self, x1, y1, x2, y2, steps):
        """
        Generates a cubic bezier curve points.
        """
        # Control points
        cx1 = x1 + (x2 - x1) * random.uniform(0.2, 0.8)
        cy1 = y1 + (y2 - y1) * random.uniform(0.2, 0.8) + random.uniform(-100, 100)
        
        cx2 = x1 + (x2 - x1) * random.uniform(0.2, 0.8)
        cy2 = y1 + (y2 - y1) * random.uniform(0.2, 0.8) + random.uniform(-100, 100)
        
        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * cx1 + 3*(1-t) * t**2 * cx2 + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * cy1 + 3*(1-t) * t**2 * cy2 + t**3 * y2
            points.append((x, y))
        return points

    async def _detect_proxy_settings(self, proxy_config):
        """
        Detects the timezone, locale, and geolocation of the proxy IP.
        Now uses ipapi.co (HTTPS) as primary source for better accuracy (matches Whoer),
        with ip-api.com (HTTP) as fallback.
        """
        # Create a temporary non-persistent context just for the IP check
        # We cannot use self.context because it might be already set up or we want to avoid polluting it before config
        temp_browser = await self.playwright.chromium.launch(
            proxy=proxy_config,
            headless=True, # Always headless for check
            args=["--no-sandbox"]
        )
        
        # We need a context to make requests
        page = await temp_browser.new_page()
        
        detected = {}
        
        # 1. Primary Source: ipapi.co (More accurate for Residential IPs)
        try:
            print("  → Probing ipapi.co (Primary)...")
            response = await page.goto("https://ipapi.co/json/", timeout=15000)
            if response and response.ok:
                data = await response.json()
                detected["timezone"] = data.get("timezone")
                detected["locale"] = "en-US" # Default
                
                # Construct locale from country
                country = data.get("country_code")
                if country:
                    detected["locale"] = f"en-{country}"
                    
                detected["lat"] = data.get("latitude")
                detected["lon"] = data.get("longitude")
                
                print(f"    ✔ Primary Source Success: {detected.get('timezone')} ({country})")
                await temp_browser.close()
                return detected
        except Exception as e:
            print(f"    ✖ Primary Source Failed: {e}")

        # 2. Fallback Source: ip-api.com (Faster, HTTP, less strict)
        try:
            print("  → Probing ip-api.com (Fallback)...")
            # This is HTTP, so might leak if not careful, but we are in a proxy context
            response = await page.goto("http://ip-api.com/json", timeout=15000)
            if response and response.ok:
                data = await response.json()
                detected["timezone"] = data.get("timezone")
                detected["locale"] = "en-US"
                
                country = data.get("countryCode")
                if country:
                    detected["locale"] = f"en-{country}"
                
                detected["lat"] = data.get("lat")
                detected["lon"] = data.get("lon")
                
                print(f"    ✔ Fallback Source Success: {detected.get('timezone')} ({country})")
        except Exception as e:
            print(f"    ✖ Fallback Source Failed: {e}")

        await temp_browser.close()
        return detected
