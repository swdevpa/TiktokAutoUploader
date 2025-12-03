from tiktok_uploader.StealthBrowser import StealthBrowser
import os

import asyncio

async def test_stealth_browser():
    print("Testing StealthBrowser...")
    try:
        async with StealthBrowser(headless=True) as browser:
            # Attach console listener
            browser.page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
            browser.page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))
            
            print("[+] Browser launched successfully")
            
            # Test 1: Stealth Check
            webdriver = await browser.page.evaluate("navigator.webdriver")
            print(f"[*] navigator.webdriver = {webdriver}")
            if webdriver is not None:
                print("[-] FAIL: navigator.webdriver detected!")
            else:
                print("[+] PASS: navigator.webdriver is undefined")
                
            # Test 2: Signature Generation
            print("[*] Testing Signature Generation...")
            url = "https://www.tiktok.com/tiktok/web/project/post/v1/?app_name=tiktok_web&channel=tiktok_web&device_platform=web&aid=1988&msToken=test_token"
            
            # Check if window.generateBogus exists
            exists = await browser.page.evaluate("typeof window.generateBogus")
            print(f"[*] window.generateBogus type: {exists}")
            
            # Test 3: AudioContext Noise
            print("[*] Testing AudioContext Noise...")
            audio_noise = await browser.page.evaluate("""() => {
                try {
                    const ctx = new (window.AudioContext || window.webkitAudioContext)();
                    const buffer = ctx.createBuffer(1, 1000, 44100);
                    const data = buffer.getChannelData(0);
                    // Check if noise was injected (sum should not be exactly 0 if initialized, 
                    // but here we rely on the getter modification. 
                    // Let's check if the getter code string contains our injection or if values change.)
                    return AudioBuffer.prototype.getChannelData.toString().includes('random');
                } catch(e) { return false; }
            }""")
            if audio_noise:
                print("[+] PASS: AudioContext noise injection detected")
            else:
                print("[-] FAIL: AudioContext noise not detected")

            # Test 4: Hardware Concurrency
            concurrency = await browser.page.evaluate("navigator.hardwareConcurrency")
            print(f"[*] navigator.hardwareConcurrency = {concurrency}")
            if concurrency == 4:
                print("[+] PASS: Hardware Concurrency spoofed to 4")
            else:
                print(f"[-] FAIL: Hardware Concurrency is {concurrency}")

            # Test 5: WebRTC
            webrtc = await browser.page.evaluate("window.RTCPeerConnection")
            print(f"[*] window.RTCPeerConnection = {webrtc}")
            if webrtc is None:
                print("[+] PASS: WebRTC is disabled/undefined")
            else:
                print("[-] FAIL: WebRTC is still available")

            sig = await browser.get_signature(url)
            if sig and sig.get("signature") and sig.get("x_bogus"):
                print(f"[+] PASS: Generated Signature: {sig['signature'][:20]}...")
                print(f"[+] PASS: Generated X-Bogus: {sig['x_bogus']}")
            else:
                print("[-] FAIL: Signature generation failed")
                
    except Exception as e:
        print(f"[-] ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_stealth_browser())
