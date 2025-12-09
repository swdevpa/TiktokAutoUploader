import asyncio
import random
import logging
import time
import requests
from pathlib import Path
from .StealthBrowser import StealthBrowser

logger = logging.getLogger("warmup")

# Configuration (Point 5 of Spec)
WARMUP_CONFIG = {
    "global_like_rate": 0.05,
    "interaction_gate_threshold": 0.7,
    "scroll_back_probability": 0.015,
    "watch_patterns": {
        "instant_skip_weight": 0.4,
        "drop_off_weight": 0.4,
        "engaged_view_weight": 0.2
    },
    "niche_training": {
        "enabled": True,
        "keywords": ["#iphone", "#app", "#tech", "#hack", "#ios", "#productivity", "#apple", "trick", "tutorial"],
        "blacklisted_keywords": ["#dance", "#comedy", "#trend", "#lipsync", "pov", "drama"],
        "boost_factor": 3.0
    }
}

class WarmupBrowser(StealthBrowser):
    """
    Specialized browser wrapper for 'warming up' TikTok accounts.
    Inherits all stealth/proxy logic from StealthBrowser.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actions_performed = {
            "watched_seconds": 0,
            "scrolls": 0,
            "likes": 0,
            "mouse_moves": 0
        }

    async def human_scroll(self, reverse=False):
        """
        Scrolls strictly using mouse wheel to simulate desktop user behavior.
        reverse=True means scroll UP (backwards).
        """
        try:
            # Scroll distance roughly one video height (approx 800-900px on 1080p minus UI)
            # Desktop TikTok layout is variable, but wheel scroll works reliably.
            scroll_amount = random.randint(300, 700)
            if reverse:
                scroll_amount = -scroll_amount

            # Break it down into small steps (acceleration/deceleration)
            steps = random.randint(8, 20)
            
            # Bézier-like speed curve (simple ease-in-out)
            for i in range(steps):
                if not self.page:
                    break
                
                # Simple easing: slightly faster in middle
                progress = i / steps
                current_step_size = (scroll_amount / steps) * (1 + 0.5 * math.sin(progress * math.pi))
                
                await self.page.mouse.wheel(0, current_step_size)
                
                # Tiny random pause between wheel 'ticks'
                await asyncio.sleep(random.uniform(0.02, 0.08))
            
            self.actions_performed["scrolls"] += 1
        except Exception as e:
            logger.warning(f"Error during scroll: {e}")

    async def idle_mouse_jitter(self, duration_sec):
        """
        Moves the mouse slightly while watching a video (idle behavior).
        """
        end_time = time.time() + duration_sec
        while time.time() < end_time:
            # Only do jitter occasionally
            if random.random() < 0.3:
                # Get current pos (not directly possible in Playwright without tracking, 
                # so we just move relative or to random nearby point if we knew where we were.
                # Since we don't track, we move to a random central-ish area or just wiggle).
                width = 1920
                height = 1080
                x = random.randint(200, width-200)
                y = random.randint(200, height-200)
                
                # Move to x,y quickly
                await self.page.mouse.move(x, y, steps=random.randint(3, 10))
                
            sleep_chunk = random.uniform(0.5, 3.0)
            # Don't oversleep total duration
            remaining = end_time - time.time()
            if remaining <= 0: break
            await asyncio.sleep(min(sleep_chunk, remaining))

    async def get_video_content_info(self):
        """
        Scans the current video DOM for description keywords (Niche Training).
        Returns: {'text': str, 'tags': list}
        """
        info = {'text': '', 'tags': []}
        try:
            # Selector for video description on Desktop Web
            # e.g. [data-e2e="video-desc"] or nearby containers
            desc_el = await self.page.query_selector('[data-e2e="video-desc"]')
            if desc_el:
                text = await desc_el.inner_text()
                info['text'] = text.lower()
                # Extract hashtags roughly
                info['tags'] = [w for w in info['text'].split() if w.startswith("#")]
        except Exception as e:
            logger.debug(f"Content scan failed: {e}")
        return info

    async def determine_watch_strategy(self, content_info):
        """
        Decides the archetype based on content (Niche Training) and weights.
        Returns: (archetype_name, duration_multiplier, like_boost)
        """
        # 1. Niche Training Filters
        config = WARMUP_CONFIG["niche_training"]
        positive_keywords = config["keywords"]
        negative_keywords = config["blacklisted_keywords"]
        boost_factor = config["boost_factor"]
        
        text = content_info.get('text', '')
        
        # Check Positive
        if config["enabled"] and any(w in text for w in positive_keywords):
            logger.info(f"Niche MATCH found: {text[:30]}...")
            return "engaged_view", 1.2, boost_factor # Boost like prob x3
        
        # Check Negative
        if config["enabled"] and any(w in text for w in negative_keywords):
            logger.info(f"Niche MISMATCH found: {text[:30]}...")
            return "instant_skip", 1.0, 0.0 # Force skip, no like
        
        # 2. Random Archetypes
        patterns = WARMUP_CONFIG["watch_patterns"]
        r = random.random()
        
        # Accumulate weights (assumes they likely sum to 1.0, but logic works sequentially)
        skip_threshold = patterns["instant_skip_weight"]
        drop_threshold = skip_threshold + patterns["drop_off_weight"]
        
        if r < skip_threshold:
            return "instant_skip", 1.0, 1.0
        elif r < drop_threshold:
            return "drop_off", 1.0, 1.0
        else:
            return "engaged_view", 1.0, 1.0

    async def perform_advanced_interaction(self):
        """
        Executes "Share-Trick" or "Profile Deep-Dive" occasionally.
        """
        r = random.random()
        try:
            if r < 0.5:
                # Share Trick
                # Find share button (arrow icon)
                share_btn = await self.page.query_selector('[data-e2e="share-icon"]')
                if share_btn:
                    await self.human_click_element(share_btn)
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                    # Click body to dismiss or 'Copy Link'
                    # On desktop, share menu might be a popover. Clicking body usually closes it.
                    # Or find 'Copy link' text
                    copy_link = await self.page.query_selector('text="Copy link"')
                    if copy_link and random.random() < 0.5:
                        await self.human_click_element(copy_link)
                        logger.info("Performed Share-Trick (Copy Link)")
                    else:
                        # Dismiss
                        await self.page.mouse.click(500, 500) # blind click in center
                        logger.info("Performed Share-Trick (Dismiss)")
            else:
                # Profile Deep Dive
                # Click username [data-e2e="video-author-uniqueid"]
                user_link = await self.page.query_selector('[data-e2e="video-author-uniqueid"]')
                if user_link:
                    await self.human_click_element(user_link)
                    logger.info("Performed Profile Deep-Dive (Enter)")
                    # Wait for load
                    await self.page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(random.uniform(2, 5))
                    # Scroll a bit
                    await self.human_scroll()
                    await asyncio.sleep(random.uniform(1, 3))
                    # Go back
                    await self.page.go_back()
                    logger.info("Performed Profile Deep-Dive (Return)")
                    await asyncio.sleep(random.uniform(1, 2))
                    
        except Exception as e:
            logger.debug(f"Advanced interaction failed: {e}")


    async def human_click_element(self, element):
        """
        Helper to invoke human_click on a specific playwright element handle.
        """
        if not element: return
        # selector logic in human_click expects a string selector, 
        # but here we have an element handle. 
        # We need to adapt human_click or just use bounding box logic here.
        box = await element.bounding_box()
        if box:
            self.human_click_box(box)

    async def human_click_box(self, box):
        """
        Internal: clicks a bounding box with bezier path.
        """
        # Target
        target_x = box["x"] + box["width"] * random.uniform(0.2, 0.8)
        target_y = box["y"] + box["height"] * random.uniform(0.2, 0.8)
        
        # Start (mock) - assume center or random
        start_x = random.randint(0, 1920)
        start_y = random.randint(0, 1080)
        
        steps = random.randint(20, 40)
        # Use underlying bezier from StealthBrowser (assuming it's implemented there or we duplicate)
        # We can implement a local helper if StealthBrowser._bezier_curve isn't accessible or is different.
        points = self._bezier_curve(start_x, start_y, target_x, target_y, steps)
        
        for p in points:
            await self.page.mouse.move(p[0], p[1])
            if random.random() > 0.9: await asyncio.sleep(0.001)
            
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await self.page.mouse.up()


    async def run_warmup(self, duration_minutes: int):
        logger.info(f"Starting ADVANCED Warmup Protocol for {duration_minutes}m.")
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        # Navigate
        try:
            await self.page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 7)) 
        except Exception as e:
            logger.error(f"Failed to load For You: {e}")
            return

        while time.time() < end_time:
            # 1. Analyze Content
            content_info = await self.get_video_content_info()
            
            # 2. Determine Archetype
            archetype, dur_mult, like_prob_mult = await self.determine_watch_strategy(content_info)
            
            # 3. Determine Watch Duration
            # Assuming 'video_duration' is unknown (hard to read without waiting), we simulate behavior based on user time.
            # Real users don't know duration either until they finish or look at the bar.
            # We estimate a "full" video is ~15-30s.
            estimated_full_duration = random.uniform(15, 30)
            
            if archetype == "instant_skip":
                watch_time = random.uniform(0.5, 2.5)
                logger.info(f"[Action] Instant Skip ({watch_time:.1f}s) - {content_info['text'][:20]}...")
            
            elif archetype == "drop_off":
                watch_time = estimated_full_duration * random.uniform(0.3, 0.6)
                logger.info(f"[Action] Drop-Off ({watch_time:.1f}s)")
                
            elif archetype == "engaged_view":
                # Watch 95-130% (Looping)
                watch_time = estimated_full_duration * random.uniform(0.95, 1.3)
                logger.info(f"[Action] Engaged View ({watch_time:.1f}s) - MATCHED!")
            
            # 4. Watch Loop
            await self.idle_mouse_jitter(watch_time)
            self.actions_performed["watched_seconds"] += watch_time
            
            # 5. Conditional Interactions (Only if Engaged View)
            if archetype == "engaged_view":
                # Gatekeeper: Did we watch enough? (Yes, by definition of engaged view time)
                
                # Check Conditional Like
                # Base rate * boost
                base_like_rate = WARMUP_CONFIG["global_like_rate"]
                like_chance = base_like_rate * like_prob_mult
                
                if random.random() < like_chance:
                    await self.maybe_like_video() # Existing method, improved with Human Click later?
                
                # Advanced Interaction?
                if random.random() < 0.05: # 5% chance generic advanced interaction
                    await self.perform_advanced_interaction()

            # 6. Scroll Logic (with Scroll-Back chance)
            # Scroll Back Probability
            if random.random() < WARMUP_CONFIG["scroll_back_probability"]:
                logger.info("Perform Scroll-Back Move")
                await self.human_scroll() # Down (next)
                await asyncio.sleep(1.0)
                await self.human_scroll(reverse=True) # Up (back)
                # Now we are back at the "interesting" video.
                # Force Engaged View behavior effectively by waiting again?
                await asyncio.sleep(random.uniform(5, 10))
                if random.random() < 0.2: # High chance to like after scroll back
                    await self.maybe_like_video()
            else:
                await self.human_scroll()
                
            await asyncio.sleep(random.uniform(0.5, 1.5))

        logger.info("Advanced Warmup Complete.")


async def warmup_user(session_file_path: str, proxy: str, duration_minutes: int, callback_url: str = None):
    """
    Entry point function to be called by API.
    """
    logger.info(f"Initializing warmup for session {Path(session_file_path).name} with proxy {proxy}")
    
    actions = {}
    status = "success"
    error_msg = None
    
    try:
        # Use context manager to ensure browser closes
        async with WarmupBrowser(headless=True, proxy=proxy) as browser:
            # browser.context is already set up with proxy/stealth in __enter__
            
            # Load cookies
            if session_file_path and Path(session_file_path).exists():
                browser.load_cookies(session_file_path)
            else:
                logger.warning("No session file found or provided. Running as guest (less effective for account warmup).")

            await browser.run_warmup(duration_minutes)
            actions = browser.actions_performed

    except Exception as e:
        logger.exception(f"Warmup failed: {e}")
        status = "error"
        error_msg = str(e)
    finally:
        # Callback
        if callback_url:
            try:
                payload = {
                    "status": status,
                    "proxy": proxy,
                    "session": Path(session_file_path).name if session_file_path else "none",
                    "actions": actions,
                    "duration_minutes_requested": duration_minutes,
                    "error": error_msg
                }
                logger.info(f"Sending callback to {callback_url}")
                # Use requests for synchronous HTTP (or httpx for async, but running in standard thread here is mostly fine for simple callback, 
                # actually async is better since we are in async def. But requests is sync.)
                # Since this is running in a BackgroundTask (which is just run in the event loop if async), blocking calls block the loop.
                # Better to use asyncio.to_thread for requests or use aiohttp/httpx.
                # For simplicity/dependency avoidance, let's wrap requests in to_thread.
                await asyncio.to_thread(requests.post, callback_url, json=payload, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send callback: {e}")
