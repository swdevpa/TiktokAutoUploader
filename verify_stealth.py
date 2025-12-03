from tiktok_uploader.StealthBrowser import StealthBrowser
import os

def test_stealth_browser():
    print("Testing StealthBrowser...")
    try:
        with StealthBrowser(headless=True) as browser:
            # Attach console listener
            browser.page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
            browser.page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))
            
            print("[+] Browser launched successfully")
            
            # Test 1: Stealth Check
            webdriver = browser.page.evaluate("navigator.webdriver")
            print(f"[*] navigator.webdriver = {webdriver}")
            if webdriver is not None:
                print("[-] FAIL: navigator.webdriver detected!")
            else:
                print("[+] PASS: navigator.webdriver is undefined")
                
            # Test 2: Signature Generation
            print("[*] Testing Signature Generation...")
            url = "https://www.tiktok.com/tiktok/web/project/post/v1/?app_name=tiktok_web&channel=tiktok_web&device_platform=web&aid=1988&msToken=test_token"
            
            # Check if window.generateBogus exists
            exists = browser.page.evaluate("typeof window.generateBogus")
            print(f"[*] window.generateBogus type: {exists}")
            
            sig = browser.get_signature(url)
            if sig and sig.get("signature") and sig.get("x_bogus"):
                print(f"[+] PASS: Generated Signature: {sig['signature'][:20]}...")
                print(f"[+] PASS: Generated X-Bogus: {sig['x_bogus']}")
            else:
                print("[-] FAIL: Signature generation failed")
                
    except Exception as e:
        print(f"[-] ERROR: {e}")

if __name__ == "__main__":
    test_stealth_browser()
