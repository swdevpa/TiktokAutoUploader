import asyncio
import random
import logging
import time
import requests
from pathlib import Path
from .StealthBrowser import StealthBrowser

logger = logging.getLogger("warmup")

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

    async def human_scroll(self):
        """Scrolls down like a human (smoothly, variable speed)."""
        try:
            # Scroll distance between 300 and 800 pixels
            scroll_amount = random.randint(300, 800)
            # Break it down into small steps
            steps = random.randint(5, 15)
            step_size = scroll_amount / steps
            
            for _ in range(steps):
                if not self.page:
                    break
                await self.page.mouse.wheel(0, step_size)
                # tiny pause between wheel ticks
                await asyncio.sleep(random.uniform(0.01, 0.05))
            
            self.actions_performed["scrolls"] += 1
        except Exception as e:
            logger.warning(f"Error during scroll: {e}")

    async def human_mouse_move(self):
        """Moves mouse randomly across the screen."""
        try:
            if not self.page:
                return
            width = self.page.viewport_size['width']
            height = self.page.viewport_size['height']
            
            x = random.randint(0, width)
            y = random.randint(0, height)
            
            # Move in steps? or just move
            # Playwright move is instant unless steps provided
            await self.page.mouse.move(x, y, steps=random.randint(5, 20))
            self.actions_performed["mouse_moves"] += 1
        except Exception as e:
            logger.warning(f"Error during mouse move: {e}")

    async def maybe_like_video(self):
        """Tries to find a like button and click it with moderate probability (15%)."""
        if random.random() > 0.15:
            return

        try:
            # Try multiple selectors for the like button
            # 1. data-e2e="like-icon" (Standard)
            # 2. span[data-e2e="like-icon"] (Specific)
            # 3. button[aria-label^="Like"] (Accessibility)
            selectors = [
                '[data-e2e="like-icon"]',
                '[data-e2e="feed-like-icon"]',
                'div[data-e2e="like-icon"]',
            ]
            
            btn = None
            for sel in selectors:
                btns = await self.page.query_selector_all(sel)
                if btns:
                    # Filter for visible buttons only? 
                    # For simplicity, pick the first or second one as they are likely in viewport
                    btn = btns[0] 
                    if len(btns) > 1:
                        btn = btns[min(1, len(btns)-1)]
                    break
            
            if btn:
                # Scroll slightly into view if needed? usually Playwright handles auto-scroll on click
                await btn.click()
                self.actions_performed["likes"] += 1
                logger.info("Liked a video (click).")
                await asyncio.sleep(random.uniform(0.5, 1.5))
            else:
                # Fallback: Double click on the video container to like
                # This is risky if we click a link/hashtag, but safe in center of screen usually.
                # Let's try to find the video container.
                video_container = await self.page.query_selector('div[data-e2e="feed-video"]')
                if video_container:
                     # Double click center of video
                     box = await video_container.bounding_box()
                     if box:
                         await self.page.mouse.dblclick(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                         self.actions_performed["likes"] += 1
                         logger.info("Liked a video (double-tap).")
                else:
                    logger.debug("Wanted to like, but no button or video container found.")

        except Exception as e:
            logger.warning(f"Error attempting like: {e}")

    async def run_warmup(self, duration_minutes: int):
        """
        Main execution loop for warmup.
        """
        logger.info(f"Starting warmup for {duration_minutes} minutes.")
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        # Navigate to For You
        try:
            await self.page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 7)) # Initial load wait
        except Exception as e:
            logger.error(f"Failed to load For You page: {e}")
            return

        while time.time() < end_time:
            # 1. Watch video (wait)
            watch_time = random.uniform(5, 25) # Watch for 5-25 seconds
            logger.info(f"Watching video for {watch_time:.1f}s")
            await asyncio.sleep(watch_time)
            self.actions_performed["watched_seconds"] += watch_time
            
            # 2. Maybe move mouse
            if random.random() < 0.3:
                await self.human_mouse_move()

            # 3. Maybe like
            await self.maybe_like_video()

            # 4. Scroll to next
            await self.human_scroll()
            
            # Short pause after scroll
            await asyncio.sleep(random.uniform(0.5, 2.0))

        logger.info("Warmup duration reached.")


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
