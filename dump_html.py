import asyncio
import logging
from tiktok_uploader.StealthBrowser import StealthBrowser

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def main():
    url = "https://www.tiktok.com/@ivywinthrt/video/7579735755702979871"
    async with StealthBrowser(headless=True) as browser:
        await browser.page.goto(url, wait_until="domcontentloaded")
        content = await browser.page.content()
        with open("tiktok_page.html", "w") as f:
            f.write(content)
        print("Page content saved to tiktok_page.html")

if __name__ == "__main__":
    asyncio.run(main())
