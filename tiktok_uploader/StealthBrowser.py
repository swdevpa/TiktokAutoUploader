import json
import time
import os
import asyncio
import random
import math
from playwright.async_api import async_playwright, Page, BrowserContext
from .cookies import load_cookies_from_file, save_cookies_to_file

class StealthBrowser:
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

    async def probe_proxy(self):
        """
        Public utility to test proxy settings without starting a full session.
        Returns the detected configuration (timezone, locale, ip, etc).
        """
        self.playwright = await async_playwright().start()
        detected = {}
        try:
            proxy_config = self._parse_proxy(self.proxy) if self.proxy else None
            if proxy_config:
                detected = await self._detect_proxy_settings(proxy_config)
            else:
                detected = {"error": "No proxy provided"}
        except Exception as e:
            detected = {"error": str(e)}
        finally:
            await self.playwright.stop()
        return detected

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
            
            print(f"Proxy detected: {timezone_id} | {locale}")
            
        elif self.timezone_id:
             print(f"Using manual timezone override (Detection failed): {self.timezone_id}")
             timezone_id = self.timezone_id

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
            "extra_http_headers": {
                "DNT": "1" # DNT: 1 means "Do Not Track"
            }
        }
        
        if geolocation:
            context_options["geolocation"] = geolocation

        # Load storage state if provided and exists (JSON format)
        if self.storage_state_path and os.path.exists(self.storage_state_path) and self.storage_state_path.endswith(".json"):
             try:
                 with open(self.storage_state_path, "r") as f:
                     # Validate JSON content before passing to Playwright to avoid crashes
                     json.load(f)
                 context_options["storage_state"] = self.storage_state_path
                 print(f"Loaded session from JSON: {self.storage_state_path}")
             except Exception as e:
                 print(f"Error loading storage_state JSON: {e}")

        self.context = await self.browser.new_context(**context_options)

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
            Object.defineProperty(navigator, 'doNotTrack', {
                get: () => "1"
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

        # 5. WebGL Vendor/Renderer Spoofing
        await context.add_init_script("""
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // UNMASKED_VENDOR_WEBGL
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                // UNMASKED_RENDERER_WEBGL
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
        """)

        # 6. Canvas Noise Injection
        await context.add_init_script("""
            const toBlob = HTMLCanvasElement.prototype.toBlob;
            const toDataURL = HTMLCanvasElement.prototype.toDataURL;
            const getImageData = CanvasRenderingContext2D.prototype.getImageData;
            
            var noise = {
                "r": Math.floor(Math.random() * 10) - 5,
                "g": Math.floor(Math.random() * 10) - 5,
                "b": Math.floor(Math.random() * 10) - 5,
                "a": Math.floor(Math.random() * 10) - 5
            };

            // Override toDataURL
            HTMLCanvasElement.prototype.toDataURL = function(type, encoderOptions) {
                const context = this.getContext('2d');
                if (context) {
                    const shift = {
                        'r': Math.floor(Math.random() * 10) - 5,
                        'g': Math.floor(Math.random() * 10) - 5,
                        'b': Math.floor(Math.random() * 10) - 5,
                        'a': Math.floor(Math.random() * 10) - 5
                    };
                    const width = this.width;
                    const height = this.height;
                    const imageData = context.getImageData(0, 0, width, height);
                    for (let i = 0; i < height; i++) {
                        for (let j = 0; j < width; j++) {
                            const n = i * (width * 4) + j * 4;
                            imageData.data[n + 0] = imageData.data[n + 0] + shift.r;
                            imageData.data[n + 1] = imageData.data[n + 1] + shift.g;
                            imageData.data[n + 2] = imageData.data[n + 2] + shift.b;
                            imageData.data[n + 3] = imageData.data[n + 3] + shift.a;
                        }
                    }
                    context.putImageData(imageData, 0, 0);
                }
                return toDataURL.apply(this, arguments);
            };
        """)

        # 7. AudioContext Noise
        await context.add_init_script("""
            const getChannelData = AudioBuffer.prototype.getChannelData;
            Object.defineProperty(AudioBuffer.prototype, 'getChannelData', {
                value: function(channel) {
                    const results = getChannelData.apply(this, [channel]);
                    // Add tiny noise
                    for (let i = 0; i < results.length; i += 100) {
                        results[i] += (Math.random() * 0.0000001) - 0.00000005;
                    }
                    return results;
                }
            });
        """)

        # 8. Hardware Concurrency & Memory Spoofing
        await context.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """)

        # 9. Font Enumeration Masking (Basic)
        await context.add_init_script("""
            // Mask offsetWidth/offsetHeight for font detection
            const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
            const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
            
            Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
                get: function() {
                    if (this.style.fontFamily) {
                        // Add slight noise to dimensions if font is being measured
                        return originalOffsetWidth.get.call(this) + (Math.random() > 0.95 ? 1 : 0);
                    }
                    return originalOffsetWidth.get.call(this);
                }
            });
        """)

        # 10. WebRTC IP Leak Protection (Smart Mocking)
        # Instead of disabling (which is suspicious/breaks functionality), we mock the API to return no candidates.
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

    async def load_session(self, filename: str = None):
        """
        Loads session from a JSON file (Playwright storageState) OR migrates from legacy pickle.
        If filename is provided, it overrides self.storage_state_path.
        """
        if self.guest_mode:
            print("Guest mode enabled: Skipping session loading.")
            return

        target_path = filename if filename else self.storage_state_path
        if not target_path:
            return

        # 1. Try loading JSON (Preferred)
        # Note: If valid JSON was passed to new_context in start(), it's already loaded.
        # But if we are calling this manually or if start() didn't find it, we check again.
        
        # If the file path implies JSON
        if target_path.endswith(".json"):
            if os.path.exists(target_path):
                 # Already handled in start() if path was set, but if called late:
                 if target_path != self.storage_state_path:
                     print(f"Session {target_path} should be loaded via context creation. If not, cookies might be missing.")
                 else:
                     pass # Already loaded in start()
                 # We can't easily "add" localStorage after context creation without hacky scripts.
                 # So we assume start() handled it, or we just load cookies if context exists.
                 # For safety, let's load cookies from the JSON just in case.
                 try:
                     with open(target_path, 'r') as f:
                         data = json.load(f)
                         if "cookies" in data:
                             await self.context.add_cookies(data["cookies"])
                 except Exception as e:
                     print(f"Error re-loading cookies from JSON: {e}")
            else:
                 # Check for legacy pickle to migrate NOT supported here directly? 
                 # Better to check for legacy pickle if JSON doesn't exist.
                 legacy_path = target_path.replace(".json", ".cookie")
                 if os.path.exists(legacy_path):
                     print(f"Migrating legacy pickle session: {legacy_path} -> {target_path}")
                     await self.load_cookies(legacy_path)
                     # We will save as JSON at the end of the session or explicitly now?
                     # Let's just load it. The calling code should save_session() later.

        # 2. Legacy Pickle Support
        elif target_path.endswith(".cookie"):
             await self.load_cookies(target_path)

    async def save_session(self, filename: str = None):
        """
        Saves the current session state (Cookies + LocalStorage) to a JSON file.
        """
        target_path = filename if filename else self.storage_state_path
        if not target_path:
            return
            
        # Enforce JSON extension for new saves if not specified
        if not target_path.endswith(".json") and not target_path.endswith(".cookie"):
            target_path += ".json"

        # If strict .cookie request, fall back to legacy (not recommended)
        if target_path.endswith(".cookie"):
             await self.save_cookies(target_path)
             return

        try:
            await self.context.storage_state(path=target_path)
            print(f"Session saved to {target_path} (Cookies + LocalStorage)")
        except Exception as e:
            print(f"Error saving session state: {e}")

    async def load_cookies(self, filename):
        # Legacy support Wrapper
        if self.guest_mode:
            print("Guest mode enabled: Skipping cookie loading.")
            return

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
                print(f"Loaded {len(clean_cookies)} cookies from legacy file.")
            except Exception as e:
                print(f"Error loading cookies: {e}")

    async def save_cookies(self, filename):
        # Legacy support Wrapper
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
        temp_browser = await self.playwright.chromium.launch(
            proxy=proxy_config,
            headless=True, 
            args=["--no-sandbox"]
        )
        
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
