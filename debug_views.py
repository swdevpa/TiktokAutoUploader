import asyncio
import logging
from tiktok_uploader.StealthBrowser import StealthBrowser

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def main():
    url = "https://www.tiktok.com/@ivywinthrt/video/7579735755702979871"
    async with StealthBrowser(headless=True) as browser:
        await browser.page.goto(url, wait_until="domcontentloaded")
        
        try:
            # Wait for like count to ensure page load
            await browser.page.wait_for_selector('[data-e2e="like-count"]', timeout=10000)
            
            # Dump body text
            body_text = await browser.page.inner_text("body")
            print(f"Body Text Snippet: {body_text[:500]}...")
            
            if "74" in body_text:
                print("Text '74' found in body text!")
            else:
                print("Text '74' NOT found in body text.")

            # Check for JSON elements
            universal = await browser.page.query_selector('#__UNIVERSAL_DATA_FOR_REHYDRATION__')
            if universal:
                import json
                content = await universal.inner_text()
                try:
                    data = json.loads(content)
                    print("UNIVERSAL_DATA parsed successfully.")
                    
                    # Try to find stats
                    found_stats = False
                    if "__DEFAULT_SCOPE__" in data:
                        scope = data["__DEFAULT_SCOPE__"]
                        print(f"Keys in __DEFAULT_SCOPE__: {list(scope.keys())}")
                        
                        # Check for video detail
                        if "webapp.video-detail" in scope:
                            detail = scope["webapp.video-detail"]
                            if "itemInfo" in detail:
                                item_info = detail["itemInfo"]
                                if "itemStruct" in item_info:
                                    stats = item_info["itemStruct"].get("stats")
                                    print(f"Stats found in itemStruct: {stats}")
                                    found_stats = True
                                else:
                                    print("itemStruct NOT found in itemInfo")
                            else:
                                print("itemInfo NOT found in webapp.video-detail")
                        else:
                            print("webapp.video-detail NOT found in __DEFAULT_SCOPE__")
                    else:
                        print("__DEFAULT_SCOPE__ NOT found in data")
                        
                    if not found_stats:
                        # Dump a bit of structure to help debug
                        print(f"Top level keys: {list(data.keys())}")

                except Exception as e:
                    print(f"Error parsing JSON: {e}")
            else:
                print("UNIVERSAL_DATA NOT found")
                
        except Exception as e:
            print(f"Error inspecting page: {e}")

if __name__ == "__main__":
    asyncio.run(main())
