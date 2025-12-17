import time
import requests
import json
import os
import sys
import uuid
import zlib
import random
import string
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from tiktok_uploader.StealthBrowser import StealthBrowser
from .SignupBrowser import SignupBrowser
from tiktok_uploader import Config
from tiktok_uploader.metadata_spoofing import prepare_video_for_upload, MetadataProcessingError
from requests_auth_aws_sigv4 import AWSSigV4

# Load environment variables
load_dotenv()

async def login(login_name: str, proxy: str = None):
    """
    Logs in to TikTok using StealthBrowser and saves the session.
    """
    # Prefer JSON, but might be legacy
    cookies_dir = Config.get().cookies_dir
    session_file = os.path.join(cookies_dir, f"tiktok_session-{login_name}.json")
    legacy_file = os.path.join(cookies_dir, f"tiktok_session-{login_name}.cookie")
    
    # If legacy exists but JSON doesn't, we'll migrate during save
    target_file = session_file
    if os.path.exists(legacy_file) and not os.path.exists(session_file):
        print(f"Detected legacy session file: {legacy_file}. Will migrate to JSON after login.")

    
    print(f"Logging in as {login_name}...")
    if proxy:
        print(f"Using Proxy: {proxy}")
    
    # Start browser in HEADED mode for user interaction
    # User requested to use SignupBrowser for login (more stable)
    async with SignupBrowser(headless=False, proxy=proxy, safe_mode=True) as browser:
        await browser.page.goto(os.getenv("TIKTOK_LOGIN_URL", "https://www.tiktok.com/login"), timeout=120000, wait_until='domcontentloaded')
        
        print("Please log in to TikTok in the browser window.")
        print("Waiting for session cookies...")
        
        # Wait for sessionid cookie
        logged_in = False
        while not logged_in:
            cookies = await browser.context.cookies()
            for cookie in cookies:
                if cookie["name"] == "sessionid":
                    logged_in = True
                    break
            await asyncio.sleep(1)
        
        print("Login successful! Saving session...")
        await browser.save_session(target_file)
        
    return True

async def create_account(proxy: str, save_name: str, timezone: str = None):
    """
    Launches a browser to create a new account with strict safety checks.
    """
    if not proxy:
        print("[-] Error: A proxy is REQUIRED for account creation to ensure safety.")
        return False
        
    print(f"Initializing for ACCOUNT CREATION with proxy: {proxy}")
    
    # 1. Start Browser (Headed)
    async with SignupBrowser(headless=False, proxy=proxy, timezone_id=timezone, safe_mode=True) as browser:
        
        # 2. Pre-flight Safety Check
        print("Performing Safety Pre-flight Check...")
        try:
            # Check IP location
            check_page = await browser.page.context.new_page()
            response = await check_page.goto("http://ip-api.com/json", timeout=15000)
            data = await response.json()
            
            country_code = data.get("countryCode")
            ip = data.get("query")
            
            print(f"DETECTED LOCATION: {data.get('city')}, {data.get('country')} ({country_code}) - IP: {ip}")
            
            # KILL SWITCH: Abort if Germany (DE) is detected
            if country_code == "DE":
                print("\n!!! CRITICAL SECURITY ALERT !!!")
                print(f"Detected Country is GERMANY ({country_code}).")
                print("ABORTING IMMEDIATELY TO PROTECT IDENTITY.")
                return False
                
            await check_page.close()
            
        except Exception as e:
            print(f"\n!!! SAFETY CHECK FAILED: {e}")
            print("ABORTING DUE TO FAILED SAFETY CHECK.")
            return False

        # 3. Visual Confirmation
        print("Opening Safety Verification Page...")
        try:
            # Open whoer.net for visual verification
            await browser.page.goto("https://whoer.net", timeout=60000)
        except Exception as e:
            print(f"Warning: Could not load whoer.net: {e}")

        print("\n" + "="*60)
        print("PLEASE VISUALLY VERIFY THE BROWSER WINDOW")
        print("1. Check IP, DNS, and WebRTC status on whoer.net (or checks displayed)")
        print("2. Ensure everything is GREEN and location is correct.")
        print("="*60)
        
        # We need to pause here. Since this is async and likely running in a terminal, 
        # we can use input().
        confirm = input("Type 'SAFE' to proceed to TikTok, or anything else to ABORT: ")
        if confirm.strip().upper() != "SAFE":
            print("Aborted by user.")
            return False

        # 4. Navigate to TikTok Signup
        print("Safety confirmed. Navigating to TikTok Signup...")
        await browser.page.goto("https://www.tiktok.com/signup", timeout=60000)
        
        print("Please complete the signup process in the browser.")
        print("NOTE: TikTok assigns session IDs to guests too. We cannot auto-detect login reliable.")
        print("BUT: The browser is fresh/incognito.")

        # Interactive API helper
        use_api = input("Do you want to use the API to send a verification code? (y/N): ")
        if use_api.strip().lower() == 'y':
            email_addr = input("Enter email address: ")
            if email_addr:
                print(f"Attempting to send code to {email_addr} via API...")
                result = await browser.request_email_code(email_addr)
                print(f"API Result: {result}")
        

        # 5. Wait for User Confirmation
        while True:
            confirm = input("Type 'DONE' when you are successfully logged in and see your feed: ")
            if confirm.strip().upper() == "DONE":
                break
            print("Invalid input. Type 'DONE' via keyboard when ready.")
            
        print(f"Saving session to {save_name}...")
        cookies_dir = Config.get().cookies_dir
        save_file = os.path.join(cookies_dir, f"tiktok_session-{save_name}.json")
        await browser.save_session(save_file)
        # Wait a bit and save again to ensure all tokens are captured
        await asyncio.sleep(3)
        await browser.save_session(save_file) 
        print(f"Session saved successfully to {save_file}.")
            
    return True

async def upload_video(session_file_path, video, title, schedule_time=0, allow_comment=1, allow_duet=0, allow_stitch=0, visibility_type=0, brand_organic_type=0, branded_content_type=0, ai_label=0, proxy=None, datacenter=None, status_callback=None):
    """
    Uploads a video to TikTok using StealthBrowser (Playwright).
    """
    def _report_status(message):
        if status_callback:
            try:
                status_callback(message)
            except Exception:
                pass
        else:
            print(message)

    _report_status("Initializing Stealth Browser...")
    
    # Initialize StealthBrowser (Headless by default, unless debugging)
    async with StealthBrowser(headless=True, proxy=proxy, storage_state_path=session_file_path) as browser:
        
        # Load session (JSON or Legacy migration handled by browser.load_session or internally by storage_state_path)
        # If storage_state_path was passed to init, it might auto-load if JSON.
        # But we also have load_session which handles migration logic explicitly.
        await browser.load_session(session_file_path)

        
        # Validate session
        cookies = await browser.context.cookies()
        session_id = next((c["value"] for c in cookies if c["name"] == 'sessionid'), None)
        if not session_id:
            raise RuntimeError("No sessionid found. Please login first.")
            
        _report_status("User successfully logged in (Cookies Loaded).")

        # Navigate to TikTok to set correct origin/referer/cookies
        try:
            await browser.page.goto("https://www.tiktok.com/", timeout=120000, wait_until='commit')
        except Exception as e:
            error_msg = str(e)
            if "ERR_TIMED_OUT" in error_msg or "Timeout" in error_msg:
                raise RuntimeError(f"Proxy Connection Failed: The proxy {proxy} could not connect to TikTok. Please check your proxy settings.") from e
            raise RuntimeError(f"Failed to load TikTok: {e}") from e
        
        # Prepare Video
        try:
            processed_video = prepare_video_for_upload(video)
        except MetadataProcessingError as exc:
            raise RuntimeError(str(exc)) from exc
            
        cleanup_target = processed_video

        try:
            # 1. Create Project
            _report_status("Creating Project...")
            creation_id = _generate_random_string(21, True)
            project_url = f"https://www.tiktok.com/api/v1/web/project/create/?creation_id={creation_id}&type=1&aid=1988"
            
            response = await browser.page.request.post(project_url)
            
            if not response.ok:
                _report_status(f"[-] Project creation failed: {response.status} {response.status_text}")
                return False
                
            project_payload = await response.json()
            project_id = project_payload.get("project", {}).get("project_id")
            
            if not project_id:
                _report_status(f"[-] Could not get project_id: {project_payload}")
                return False

            # 2. Get Upload Auth
            _report_status("Getting Upload Auth...")
            auth_url = "https://www.tiktok.com/api/v1/video/upload/auth/?aid=1988"
            response = await browser.page.request.get(auth_url)
            if not response.ok:
                _report_status("[-] Failed to get upload auth")
                return False
            
            auth_data = await response.json()
            video_token = auth_data.get("video_token_v5")
            
            # 3. Upload to AWS (TikTok's S3)
            video_path = _resolve_video_path(processed_video)
            file_size = os.path.getsize(video_path)
            
            aws_auth = AWSSigV4(
                "vod",
                region="ap-singapore-1",
                aws_access_key_id=video_token["access_key_id"],
                aws_secret_access_key=video_token["secret_acess_key"],
                aws_session_token=video_token["session_token"],
            )
            
            apply_url = f"https://www.tiktok.com/top/v1?Action=ApplyUploadInner&Version=2020-11-19&SpaceName=tiktok&FileType=video&IsInner=1&FileSize={file_size}&s=g158iqx8434"
            
            # Sign headers
            req = requests.Request('GET', apply_url)
            prepped = req.prepare()
            aws_auth(prepped) 
            
            # Execute with Playwright
            response = await browser.page.request.get(apply_url, headers=dict(prepped.headers))
            
            if not response.ok:
                _report_status("[-] ApplyUploadInner failed")
                return False
                
            apply_response_json = await response.json()
            # DEBUG: Use print or logging to inspect the full response
            _report_status(f"[TikTokUpload] ApplyUploadInner Response: {json.dumps(apply_response_json)}") 
            
            upload_node = apply_response_json["Result"]["InnerUploadAddress"]["UploadNodes"][0]
            upload_host = upload_node["UploadHost"]
            
            store_info = upload_node["StoreInfos"][0]
            store_uri = store_info["StoreUri"]
            video_auth = store_info["Auth"]
            
            # CRITICAL FIX: Use the UploadID provided by TikTok, do not generate a random one.
            upload_id = store_info.get("UploadID")
            if not upload_id:
                 # Fallback if not present, though logs suggest it is.
                 upload_id = str(uuid.uuid4())
            
            # Extract UploadHeader (e.g., X-Logical-Part-Mode)
            upload_headers = store_info.get("UploadHeader", {})
            
            session_key = upload_node["SessionKey"]
            
            # 4. Upload Chunks
            _report_status(f"Uploading Video Chunks (UploadID: {upload_id})...")
            chunk_size = 5242880 # 5MB
            
            crcs = []
            
            with open(video_path, "rb") as f:
                i = 0
                part_number = 1
                
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                        
                    crc = _crc32(chunk)
                    crcs.append(crc)
                    
                    upload_chunk_url = f"https://{upload_host}/{store_uri}?partNumber={part_number}&uploadID={upload_id}&phase=transfer"
                    
                    headers = {
                        "Authorization": video_auth,
                        "Content-Type": "application/octet-stream",
                        "Content-Disposition": f'attachment; filename="{uuid.uuid4()}.mp4"',
                        "Content-Crc32": crc,
                    }
                    # Add dynamic headers from ApplyUploadInner
                    headers.update(upload_headers)
                    
                    resp = await browser.page.request.post(upload_chunk_url, headers=headers, data=chunk)
                    if not resp.ok:
                        _report_status(f"[-] Chunk {part_number} upload failed")
                        return False

                    part_number += 1
                    i += len(chunk)

            # 5. Commit Upload
            finish_url = f"https://{upload_host}/{store_uri}?uploadID={upload_id}&phase=finish&uploadmode=part"
            headers = {
                "Authorization": video_auth,
                "Content-Type": "text/plain;charset=UTF-8",
            }
            # Add dynamic headers from ApplyUploadInner
            headers.update(upload_headers)
            
            data_body = ",".join([f"{i + 1}:{crcs[i]}" for i in range(len(crcs))])
            
            
            resp = await browser.page.request.post(finish_url, headers=headers, data=data_body)
            if not resp.ok:
                try:
                    error_text = await resp.text()
                except Exception:
                    error_text = "Could not read error text"
                _report_status(f"[-] Commit upload failed: {resp.status} {error_text}")
                return False

            # 6. CommitUploadInner
            commit_inner_url = "https://www.tiktok.com/top/v1?Action=CommitUploadInner&Version=2020-11-19&SpaceName=tiktok"
            data_inner = json.dumps({"SessionKey": session_key, "Functions": [{"name": "GetMeta"}]})
            
            req = requests.Request('POST', commit_inner_url, data=data_inner)
            prepped = req.prepare()
            aws_auth(prepped)
            
            resp = await browser.page.request.post(commit_inner_url, headers=dict(prepped.headers), data=data_inner)
            if not resp.ok:
                _report_status("[-] CommitUploadInner failed")
                return False

            # 7. Publish
            _report_status("Publishing...")
            
            payload = {
                "post_common_info": {
                    "creation_id": creation_id,
                    "enter_post_page_from": 1,
                    "post_type": 3
                },
                "feature_common_info_list": [{
                    "geofencing_regions": [],
                    "playlist_name": "",
                    "playlist_id": "",
                    "tcm_params": "{\"commerce_toggle_info\":{}}",
                    "sound_exemption": 0,
                    "anchors": [],
                    "vedit_common_info": {
                        "draft": "",
                        "video_id": upload_node["Vid"]
                    },
                    "privacy_setting_info": {
                        "visibility_type": visibility_type,
                        "allow_duet": allow_duet,
                        "allow_stitch": allow_stitch,
                        "allow_comment": allow_comment
                    }
                }],
                "single_post_req_list": [{
                    "batch_index": 0,
                    "video_id": upload_node["Vid"],
                    "is_long_video": 0,
                    "single_post_feature_info": {
                        "text": title,
                        "text_extra": [],
                        "markup_text": title,
                        "music_info": {},
                        "poster_delay": 0,
                    }
                }]
            }
            
            if schedule_time > 0:
                payload["feature_common_info_list"][0]["schedule_time"] = schedule_time + int(time.time())

            # TikTok expects brand flags inside the commerce toggle payload.
            toggle_info = {}
            if brand_organic_type:
                toggle_info["brand_organic_type"] = brand_organic_type
            if branded_content_type:
                toggle_info["branded_content_type"] = branded_content_type
            
            payload["feature_common_info_list"][0]["tcm_params"] = json.dumps(
                {"commerce_toggle_info": toggle_info if toggle_info else {}}
            )

            if ai_label:
                aigc_payload = {"aigc_label_type": ai_label}
                payload["feature_common_info_list"][0]["aigc_info"] = dict(aigc_payload)
                payload["single_post_req_list"][0]["single_post_feature_info"]["aigc_info"] = dict(aigc_payload)

            # Generate Signature
            cookies = await browser.context.cookies()
            ms_token = next((c["value"] for c in cookies if c["name"] == "msToken"), None)
            if not ms_token:
                try:
                    await browser.page.goto("https://www.tiktok.com/", timeout=120000, wait_until='commit')
                except Exception as e:
                    print(f"Warning: Failed to refresh msToken: {e}")
                    # We continue, hoping the existing cookies or context are enough, or it will fail later at signing.
                cookies = await browser.context.cookies()
                ms_token = next((c["value"] for c in cookies if c["name"] == "msToken"), "dummy_token")
            
            base_url = "https://www.tiktok.com/tiktok/web/project/post/v1/"
            params = {
                "app_name": "tiktok_web",
                "channel": "tiktok_web",
                "device_platform": "web",
                "aid": 1988,
                "msToken": ms_token
            }
            
            query_params = "&".join([f"{k}={v}" for k, v in params.items()])
            url_to_sign = f"{base_url}?{query_params}"
            
            sig_data = await browser.get_signature(url_to_sign)
            if not sig_data:
                _report_status("[-] Failed to generate signature")
                return False
                
            params["X-Bogus"] = sig_data["x_bogus"]
            params["_signature"] = sig_data["signature"]
            params["verifyFp"] = sig_data["verify_fp"]
            
            resp = await browser.page.request.post(base_url, params=params, data=payload)
            
            if not resp.ok:
                _report_status(f"[-] Publish failed: {resp.status}")
                return False
                
            result = await resp.json()
            if result.get("status_code") == 0:
                _report_status("Video Published Successfully!")
                # Attempt to get the public video ID
                public_id = result.get("aweme_id") or result.get("item_id")
                
                # Check inside single_post_resp_list
                if not public_id and "single_post_resp_list" in result:
                    resp_list = result["single_post_resp_list"]
                    if resp_list and isinstance(resp_list, list):
                        # Try to find video_id, aweme_id, or item_id in the first item
                        first_item = resp_list[0]
                        public_id = first_item.get("video_id") or first_item.get("aweme_id") or first_item.get("item_id")
                        if not public_id and "single_post_feature_info" in first_item:
                             # Sometimes it might be nested further? Unlikely but possible.
                             pass

                if public_id:
                    _report_status(f"Public Video ID found: {public_id}")
                    return public_id
                
                # Fallback to Vid if public ID not found
                _report_status(f"Warning: Public Video ID not found in response. Response keys: {list(result.keys())}")
                if "single_post_resp_list" in result:
                     _report_status(f"single_post_resp_list content: {result['single_post_resp_list']}")

                return upload_node["Vid"]
            else:
                _report_status(f"[-] Publish Error: {result}")
                return False

        finally:
            _cleanup_processed_video(cleanup_target)

def _resolve_video_path(video_file: str) -> Path:
    path = Path(video_file)
    if path.is_absolute() and path.exists():
        return path
    config = Config.get()
    base_dir = Path(config.videos_dir)
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    fallback = Path.cwd() / path
    if fallback.exists():
        return fallback
    return candidate

def _cleanup_processed_video(processed_video: str):
    if not processed_video:
        return
    try:
        path = Path(processed_video)
        if path.parent.name == "sanitized" and path.exists():
            path.unlink()
    except Exception:
        pass

def _generate_random_string(length, digits=False):
    chars = string.ascii_lowercase + string.digits if digits else string.ascii_letters
    return ''.join(random.choice(chars) for _ in range(length))

def _crc32(content):
    prev = 0
    prev = zlib.crc32(content, prev)
    return "%08x" % (prev & 0xFFFFFFFF)

async def interactive_session(session_name: str, proxy: str):
    """
    Opens a headed browser with the loaded session for manual interaction.
    Enforces proxy usage and Stealth/SignupBrowser for safety.
    """
    if not proxy:
        print("[-] Error: A proxy is REQUIRED for interactive mode to prevent IP leaks.")
        return False

    print(f"Starting Interactive Session for {session_name}...")
    
    # Resolve paths
    cookies_dir = Config.get().cookies_dir
    session_file = os.path.join(cookies_dir, f"tiktok_session-{session_name}.json")
    
    # Check if session exists
    if not os.path.exists(session_file):
        # Fallback check
        if os.path.exists(session_file.replace(".json", ".cookie")):
             print("Legacy cookie file found. It will be migrated if you save.")
             # We let load_session handle the fallback, but warn the user.
        else:
             print(f"[-] Warning: Session file {session_file} not found. Starting with a FRESH session.")

    # Start Browser (Headed, Proxy Enforced)
    # CRITICAL: We MUST pass storage_state_path to init so Playwright loads localStorage during context creation.
    # Manual load_session only adds cookies.
    async with SignupBrowser(headless=False, proxy=proxy, storage_state_path=session_file) as browser:
        # Load session (Redundant check/cookie load, but safe)
        await browser.load_session(session_file)
        
        print("Session loaded.")
        print("Navigating to TikTok (For You)...")
        
        try:
            await browser.page.goto("https://www.tiktok.com/foryou", timeout=60000, wait_until='domcontentloaded')
        except Exception as e:
            print(f"Error loading page: {e}")

        print("\n" + "="*60)
        print("INTERACTIVE MODE ACTIVE")
        print("1. You can now browse, like, and warm up manually.")
        print("2. The browser is using the proxy and stealth settings.")
        print("3. When finished, come back here and press ENTER.")
        print("="*60)
        
        input("Press ENTER to close session and save changes: ")
        
        print(f"Saving session to {session_file}...")
        await browser.save_session(session_file)
        # Double save safety
        await asyncio.sleep(2)
        await browser.save_session(session_file)
        
    print("Session saved. Browser closed.")
    return True

if __name__ == "__main__":
    pass
