import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

from fastapi import BackgroundTasks, FastAPI, UploadFile, File, Form, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse

# Import the upload function from your existing project
# Adjust this import path if your project structure is different
from tiktok_uploader.tiktok import upload_video as tiktok_upload_video
from tiktok_uploader.Config import Config
from tiktok_uploader.StealthBrowser import StealthBrowser
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import re
import json

app = FastAPI()

# Ensure logs directory exists
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "api.log"

# Configure logging
# We want to log to both console (stdout) and a file (logs/api.log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    ]
)
logger = logging.getLogger("api")

# Keep upload limits small enough to reject malformed requests before they touch TikTok logic.
MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", 250 * 1024 * 1024))
MAX_SESSION_BYTES = int(os.getenv("MAX_SESSION_FILE_BYTES", 512 * 1024))
ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/x-msvideo",
}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_UPLOAD_BYTES", 10 * 1024 * 1024))
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    "image/bmp",
    "image/tiff",
}
DEFAULT_IMAGE_FADE_DURATION_SECONDS = float(os.getenv("DEFAULT_IMAGE_FADE_DURATION_SECONDS", 5.0))
MAX_IMAGE_FADE_DURATION_SECONDS = float(os.getenv("MAX_IMAGE_FADE_DURATION_SECONDS", 60.0))
UPLOAD_SECRET = os.getenv("UPLOAD_SECRET")
SCRAPE_CONCURRENCY_LIMIT = int(os.getenv("SCRAPE_CONCURRENCY_LIMIT", 5))
scrape_semaphore = asyncio.Semaphore(SCRAPE_CONCURRENCY_LIMIT)

# --- Pydantic Models for Scraping ---

class ScrapeTask(BaseModel):
    id: str
    video_url: str
    proxy: Optional[str] = None

class ScrapeRequest(BaseModel):
    tasks: List[ScrapeTask]

class ScrapeResultData(BaseModel):
    play_count: int = 0
    digg_count: int = 0
    comment_count: int = 0
    share_count: int = 0

class ScrapeResult(BaseModel):
    id: str
    status: str  # success, video_removed, error, processing, scrape_failed
    data: Optional[ScrapeResultData] = None
    error_message: Optional[str] = None

class ScrapeResponse(BaseModel):
    results: List[ScrapeResult]

# ------------------------------------

# Initialize Config (if needed by tiktok_upload_video, otherwise can be removed)
# Ensure your Config class can be initialized without issues in an API context
# For example, if it reads from a config.txt, make sure that file is accessible
Config.get() 


def validate_secret_token(token: str | None) -> None:
    if not UPLOAD_SECRET:
        logger.error("UPLOAD_SECRET not configured; rejecting upload.")
        raise HTTPException(status_code=500, detail="Server configuration incomplete.")

    if not token or token != UPLOAD_SECRET:
        logger.warning("Unauthorized upload attempt.")
        raise HTTPException(status_code=401, detail="Unauthorized.")


def enforce_file_size(path: Path, limit: int, name: str) -> int:
    size = path.stat().st_size
    if size > limit:
        logger.warning("Rejected %s because size %d > %d.", name, size, limit)
        raise HTTPException(status_code=413, detail=f"{name} exceeds size limit.")
    return size


def ensure_content_type(content_type: str | None) -> None:
    if content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        logger.warning("Rejected upload because of content type %s.", content_type)
        raise HTTPException(status_code=400, detail="Unsupported video type.")


def ensure_image_content_type(content_type: str | None) -> None:
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        logger.warning("Rejected image because of content type %s.", content_type)
        raise HTTPException(status_code=400, detail="Unsupported image type.")


def cleanup_directory(path: str | Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def generate_fadein_video_with_ffmpeg(image_paths: list[Path], output_path: Path, fade_duration: float, image_duration: float, transition_duration: float = 1.0, audio_path: Path | None = None, header_text: str | None = None) -> None:
    # Prepare inputs
    inputs = []
    filter_complex_parts = []
    
    # Common scale and fps
    target_w = 1080
    target_h = 1920
    
    # 1. Prepare inputs and scale them
    for i, img_path in enumerate(image_paths):
        # Loop each image. Duration needs to be enough to cover transition overlap.
        # For xfade, we don't strictly need to loop if we set -t, but -loop 1 -t is safer.
        inputs.extend(["-loop", "1", "-t", str(image_duration), "-i", str(img_path)])
        
        # Scale and setsar
        filter_complex_parts.append(f"[{i}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];")
    
    # 2. Apply transitions (xfade) if more than 1 image
    if len(image_paths) > 1:
        # Chain xfades
        # [v0][v1]xfade=transition=fade:duration=1:offset=2[v01];
        # [v01][v2]xfade=transition=fade:duration=1:offset=4[v012];
        
        last_stream = "[v0]"
        current_offset = 0.0
        
        for i in range(1, len(image_paths)):
            next_stream = f"[v{i}]"
            out_stream = f"[v_x{i}]" if i < len(image_paths) - 1 else "[v_concat]"
            
            # Offset calculation:
            # The previous image displays for `image_duration`.
            # The transition starts at `image_duration - transition_duration` relative to the previous image start.
            # But wait, xfade offset is absolute time.
            # Start of img 0: 0
            # Start of img 1 (transition start): image_duration - transition_duration
            # Start of img 2: (image_duration - transition_duration) + (image_duration - transition_duration) ...
            
            # Actually, let's trace:
            # Img 0 starts at 0. Ends at image_duration.
            # Img 1 starts fading in at `image_duration - transition_duration`.
            # So offset for first transition is `image_duration - transition_duration`.
            # The resulting stream [v01] has duration: `image_duration + image_duration - transition_duration`.
            # The next transition should start at `(image_duration - transition_duration) + (image_duration - transition_duration)`.
            
            offset = i * (image_duration - transition_duration)
            
            filter_complex_parts.append(f"{last_stream}{next_stream}xfade=transition=fade:duration={transition_duration}:offset={offset}{out_stream};")
            last_stream = out_stream
    else:
        # Single image case, just map v0 to v_concat
        filter_complex_parts.append("[v0]copy[v_concat];")

    # 3. Apply initial Fade In to the result
    # Note: If we have transitions, the video starts with Img 0. We want to fade THAT in from black.
    # We can just apply the fade filter to the final output.
    
    # If header_text is present, we need to chain the fade output to the drawtext filter.
    fade_out_stream = "[v_faded]" if header_text else "[v_final]"
    
    filter_complex_parts.append(f"[v_concat]format=yuv420p,fade=t=in:st=0:d={fade_duration},fps=30{fade_out_stream}")
    
    # 4. Apply Header Text (if provided)
    if header_text:
        # Escape special characters for FFmpeg
        # : -> \:
        # ' -> ' (handled by python string formatting if wrapped in single quotes, but we need to be careful)
        # Actually, for drawtext text='...', we need to escape single quotes and colons.
        safe_text = header_text.replace(":", "\\:").replace("'", "'")
        
        # Note: We used [v_faded] as input, and output [v_final]
        # Using a semicolon before this filter because the previous one didn't have it if we just appended it.
        # Wait, the previous line `filter_complex_parts.append(...)` does NOT end with a semicolon.
        # So we need to add a semicolon to the previous part OR handle it here.
        # Let's adjust the previous append to include a semicolon if we are continuing.
        
        # Actually, let's just fix the previous line to NOT be the last one if header_text is there.
        # The easiest way is to append the semicolon to the previous string in the list, or just ensure the logic flows.
        
        # Let's rewrite step 3 slightly to be cleaner.
        pass # handled below in a cleaner way

    # Refactoring Step 3 & 4 for cleaner flow:
    # Remove the last append from above and do it here properly.
    filter_complex_parts.pop() 
    
    if header_text:
        filter_complex_parts.append(f"[v_concat]format=yuv420p,fade=t=in:st=0:d={fade_duration},fps=30[v_faded];")
        
        # Drawtext filter
        # text='{safe_text}'
        # fontcolor=white
        # fontsize=48
        # x=(w-text_w)/2
        # y=h*0.15
        # borderw=2
        # bordercolor=black
        # shadowx=2
        # shadowy=2
        
        safe_text = header_text.replace(":", "\\:").replace("'", "'")
        drawtext_filter = (
            f"[v_faded]drawtext=text='{safe_text}':fontcolor=white:fontsize=48:"
            "x=(w-text_w)/2:y=h*0.15:borderw=2:bordercolor=black:shadowx=2:shadowy=2[v_final]"
        )
        filter_complex_parts.append(drawtext_filter)
    else:
        filter_complex_parts.append(f"[v_concat]format=yuv420p,fade=t=in:st=0:d={fade_duration},fps=30[v_final]")
    
    filter_complex = "".join(filter_complex_parts)
    
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    
    # Audio input
    if audio_path:
        cmd.extend(["-stream_loop", "-1", "-i", str(audio_path)])
    
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v_final]",
        "-c:v", "libx264",
        "-preset", "medium",
    ])
    
    if audio_path:
        cmd.extend([
            "-map", f"{len(image_paths)}:a",
            "-c:a", "aac",
            "-shortest"
        ])
    
    cmd.extend([
        "-threads", "2",
        str(output_path),
    ])
    
    subprocess.run(cmd, check=True, capture_output=True, text=True)

@app.post("/upload")
async def upload_tiktok_video(
    request: Request,
    video_file: UploadFile = File(...),
    session_file: UploadFile = File(...),
    caption: str = Form(...),
    schedule_time: int = Form(0),
    allow_comment: int = Form(1),
    allow_duet: int = Form(0),
    allow_stitch: int = Form(0),
    visibility_type: int = Form(0),
    brand_organic_type: int = Form(0),
    branded_content_type: int = Form(0),
    ai_label: int = Form(0),
    proxy: str = Form(None),
    datacenter: str = Form(None),
    auth_token: str = Header(None, alias="X-Upload-Auth"),
):
    client_ip = request.client.host if request.client else "unknown"
    validate_secret_token(auth_token)
    ensure_content_type(video_file.content_type)

    temp_dir = None
    video_path = None
    session_path = None

    try:
        # Create a temporary directory for this upload
        temp_dir = tempfile.mkdtemp()
        
        # Save the uploaded video file
        video_path = Path(temp_dir) / video_file.filename
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        video_size = enforce_file_size(video_path, MAX_VIDEO_BYTES, "video")

        # Save the uploaded session file
        session_path = Path(temp_dir) / session_file.filename
        with open(session_path, "wb") as buffer:
            shutil.copyfileobj(session_file.file, buffer)

        enforce_file_size(session_path, MAX_SESSION_BYTES, "session file")

        logger.info(
            "Upload request from %s: %s (%d bytes)",
            client_ip,
            video_file.filename,
            video_size,
        )

        # Call the existing upload function
        # The upload_video function needs to be adapted to accept the session_path directly
        # instead of a session_user string. This will be the next step.
        
        def log_status(msg):
            logger.info(f"[TikTokUpload] {msg}")

        video_id = await tiktok_upload_video(
            session_file_path=str(session_path), # Pass the path to the session file
            video=str(video_path),
            title=caption,
            schedule_time=schedule_time,
            allow_comment=allow_comment,
            allow_duet=allow_duet,
            allow_stitch=allow_stitch,
            visibility_type=visibility_type,
            brand_organic_type=brand_organic_type,
            branded_content_type=branded_content_type,
            ai_label=ai_label,
            proxy=proxy,
            datacenter=datacenter,
            status_callback=log_status
        )

        if video_id:
            logger.info("Upload completed for %s from %s. Video ID: %s", video_file.filename, client_ip, video_id)
            return JSONResponse(status_code=200, content={
                "message": "Video uploaded successfully!",
                "video_id": video_id
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to upload video to TikTok.")

    except Exception as e:
        print(f"Error during upload: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        # Clean up the temporary directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@app.post("/fadein-from-image")
async def create_fadein_video_from_image(
    request: Request,
    background_tasks: BackgroundTasks,
    image_file: UploadFile = File(None),
    image_files: list[UploadFile] = File(None),
    duration: float = Form(0.0),
    fade_duration: float = Form(None),
    image_duration: float = Form(None),
    transition_duration: float = Form(0.3),
    header_text: str = Form(None),
    auth_token: str = Header(None, alias="X-Upload-Auth"),
):
    client_ip = request.client.host if request.client else "unknown"
    validate_secret_token(auth_token)
    
    # Collect all images
    all_images = []
    if image_file:
        all_images.append(image_file)
    if image_files:
        all_images.extend(image_files)
        
    if not all_images:
        raise HTTPException(status_code=400, detail="No images provided.")

    for img in all_images:
        ensure_image_content_type(img.content_type)

    if duration < 0 or duration > MAX_IMAGE_FADE_DURATION_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Duration must be between 0 and {MAX_IMAGE_FADE_DURATION_SECONDS} seconds.",
        )
        
    # Default fade_duration if not provided (backward compatibility)
    final_fade_duration = fade_duration if fade_duration is not None else duration
    
    # Default image_duration to duration if not provided (backward compatibility logic)
    # If multiple images, user might want faster slides, but if not specified, we use 'duration' 
    # which was originally the total video length (approx) for 1 image.
    final_image_duration = image_duration if image_duration is not None else duration

    # Validate transition duration
    if len(all_images) > 1:
        if transition_duration >= final_image_duration:
             raise HTTPException(
                status_code=400,
                detail=f"Transition duration ({transition_duration}s) must be less than image duration ({final_image_duration}s).",
            )

    temp_dir = tempfile.mkdtemp()
    try:
        saved_image_paths = []
        for i, img in enumerate(all_images):
            uploaded_basename = Path(img.filename or f"image_{i}").name
            image_path = Path(temp_dir) / f"{i}_{uploaded_basename}"
            with open(image_path, "wb") as buffer:
                shutil.copyfileobj(img.file, buffer)
            enforce_file_size(image_path, MAX_IMAGE_BYTES, f"image_{i}")
            saved_image_paths.append(image_path)

        video_path = Path(temp_dir) / "output_fadein.mp4"
        
        # Check for audio.mp3 in the project root
        audio_path = Path("audio.mp3").resolve()
        if not audio_path.exists():
             audio_path = None
             
        generate_fadein_video_with_ffmpeg(
            saved_image_paths, 
            video_path, 
            fade_duration=final_fade_duration, 
            image_duration=final_image_duration,
            transition_duration=transition_duration,
            audio_path=audio_path,
            header_text=header_text
        )

        background_tasks.add_task(cleanup_directory, temp_dir)
        logger.info(
            "Generated fade-in video for %s from %d images (fade: %.2fs, img_dur: %.2fs) at %s",
            client_ip,
            len(saved_image_paths),
            final_fade_duration,
            final_image_duration,
            video_path,
        )
        return FileResponse(
            str(video_path),
            media_type="video/mp4",
            filename=video_path.name,
        )

    except HTTPException:
        cleanup_directory(temp_dir)
        raise
    except subprocess.CalledProcessError as exc:
        cleanup_directory(temp_dir)
        logger.exception(
            "FFmpeg failed to create fade-in video: %s",
            exc.stderr or exc,
        )
        raise HTTPException(status_code=500, detail="Failed to render fade-in video.")
    except Exception as exc:
        cleanup_directory(temp_dir)
        logger.exception("Failed to create fade-in video: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create fade-in video: {exc}")


async def parse_count(text: str) -> int:
    """
    Parses a count string like '1.2M', '10K', '1,234' into an integer.
    """
    if not text:
        return 0
    
    text = text.strip().upper()
    multiplier = 1
    
    if text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
        
    try:
        # Remove commas and convert to float, then int
        value = float(text.replace(",", ""))
        return int(value * multiplier)
    except ValueError:
        return 0

async def scrape_single_video(task: ScrapeTask) -> ScrapeResult:
    async with scrape_semaphore:
        logger.info(f"Starting scrape for {task.id}: {task.video_url}")
        try:
            async with StealthBrowser(headless=True, proxy=task.proxy, guest_mode=True) as browser:
                # 1. Navigation
                try:
                    await browser.page.goto(task.video_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"Timeout or navigation error for {task.id}: {e}")
                    return ScrapeResult(id=task.id, status="error", error_message=str(e))

                # 1.5 Handle Popups/Modals (Login, Keyboard Shortcuts, etc.)
                # 1.5 Handle Popups/Modals (Login, TikTok Shop, Keyboard Shortcuts, etc.)
                try:
                    # 1. Try sending Escape key (often closes modals)
                    await browser.page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)

                    # 2. Common selector for "X" close button on modals
                    close_btn = await browser.page.wait_for_selector('[data-e2e="modal-close-inner-button"]', state="visible", timeout=2000)
                    if close_btn:
                        logger.info(f"Scrape {task.id} - Found modal close button. Clicking...")
                        await close_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                try:
                    # 3. Generic "Close" / "Not now" buttons (for Shop, specific promos)
                    # Broadened selector to catch divs/links, not just buttons
                    potential_close_texts = ["Close", "Not now", "Skip", "Maybe later", "Guest", "Continue as guest"]
                    for text in potential_close_texts:
                        try:
                            # Look for any clickable element with this text
                            # We use a broader selector: button, or div/a/span with role=button or just text
                            # Prioritize explicit buttons first
                            btn = await browser.page.wait_for_selector(f'button:has-text("{text}"), div[role="button"]:has-text("{text}"), [data-e2e="modal-close-inner-button"]', state="visible", timeout=1000)
                            
                            if not btn:
                                # Fallback to any element with the text if it looks like a control
                                btn = await browser.page.wait_for_selector(f':text("{text}")', state="visible", timeout=500)

                            if btn:
                                logger.info(f"Scrape {task.id} - Found element with text '{text}'. Clicking...")
                                await btn.click()
                                await asyncio.sleep(0.5)
                        except:
                            continue
                            
                    # 4. Icon-based close buttons (often aria-label="Close")
                    try:
                        icon_btn = await browser.page.wait_for_selector('button[aria-label="Close"], svg[aria-label="Close"]', state="visible", timeout=500)
                        if icon_btn:
                            logger.info(f"Scrape {task.id} - Found icon with aria-label='Close'. Clicking...")
                            await icon_btn.click()
                            await asyncio.sleep(0.5)
                    except:
                        pass
                except Exception:
                    pass

                try:
                    # "Continue as guest" button
                    guest_btn = await browser.page.wait_for_selector('div:has-text("Continue as guest")', state="visible", timeout=2000)
                    if guest_btn:
                        logger.info(f"Scrape {task.id} - Found 'Continue as guest'. Clicking...")
                        await guest_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                # 2. Wait for key elements (success or failure)
                try:
                    # Wait for either the like count (success) or an error message container
                    # We can't easily wait for "text", so we wait for the page to settle a bit or check specifically.
                    # Let's wait for the like count with a timeout.
                    await browser.page.wait_for_selector('[data-e2e="like-count"]', timeout=10000)
                    is_success = True
                except Exception:
                    is_success = False

                # 3. Status Detection (if success selector not found)
                if not is_success:
                    body_text = await browser.page.inner_text("body")
                    final_url = browser.page.url
                    logger.info(f"Scrape {task.id} - Success selector not found. Checking errors. URL: {final_url}")
                    
                    # Debug: Screenshot
                    try:
                        await browser.page.screenshot(path=f"debug_scrape_{task.id}.png")
                    except:
                        pass

                    if "Video currently unavailable" in body_text or "Page not available" in body_text:
                        logger.info(f"Scrape {task.id} - 'Video currently unavailable' or 'Page not available' found in body text.")
                        return ScrapeResult(id=task.id, status="video_removed", error_message="Video unavailable in body text")
                    
                    if "video_not_found" in final_url:
                        return ScrapeResult(id=task.id, status="video_removed")
                    
                    if "captcha" in body_text.lower():
                        logger.warning(f"Scrape {task.id} - Captcha detected in body text.")
                        return ScrapeResult(id=task.id, status="scrape_failed", error_message="Captcha detected")
                        
                    # If we are here, we loaded the page but didn't find the like count and didn't find an explicit error.
                    # It might be a layout change or a different error.
                    logger.warning(f"Scrape {task.id} - Unknown state. URL: {final_url}. Body text snippet: {body_text[:200]}")
                    return ScrapeResult(id=task.id, status="error", error_message=f"Unknown state: {body_text[:100]} ... URL: {final_url}")

                # 4. Scraping Logic (Success)
                # Try to extract from JSON data first (more reliable for views)
                try:
                    # Look for SIGI_STATE or __UNIVERSAL_DATA_FOR_REHYDRATION__
                    json_data = await browser.page.evaluate("""() => {
                        const el = document.getElementById('SIGI_STATE') || document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        return el ? JSON.parse(el.textContent) : null;
                    }""")

                    if json_data:
                        # Navigate JSON structure
                        stats = None
                        
                        # Path 1: SIGI_STATE
                        if "ItemModule" in json_data:
                            for key, item in json_data["ItemModule"].items():
                                if "stats" in item:
                                    stats = item["stats"]
                                    break
                        
                        # Path 2: Universal Data
                        if not stats and "__DEFAULT_SCOPE__" in json_data:
                            try:
                                stats = json_data["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemInfo"]["itemStruct"]["stats"]
                            except KeyError:
                                pass
                        
                        if stats:
                            return ScrapeResult(
                                id=task.id,
                                status="success",
                                data=ScrapeResultData(
                                    play_count=int(stats.get("playCount", 0)),
                                    digg_count=int(stats.get("diggCount", 0)),
                                    comment_count=int(stats.get("commentCount", 0)),
                                    share_count=int(stats.get("shareCount", 0))
                                )
                            )
                except Exception as e:
                    logger.warning(f"JSON parsing failed for {task.id}: {e}")

                # Fallback to Selectors
                play_count = 0
                digg_count = 0
                comment_count = 0
                share_count = 0
                
                # Likes
                el_like = await browser.page.query_selector('[data-e2e="like-count"]')
                if el_like:
                    digg_count = await parse_count(await el_like.inner_text())
                
                # Comments
                el_comment = await browser.page.query_selector('[data-e2e="comment-count"]')
                if el_comment:
                    comment_count = await parse_count(await el_comment.inner_text())
                
                # Shares
                el_share = await browser.page.query_selector('[data-e2e="share-count"]')
                if el_share:
                    share_count = await parse_count(await el_share.inner_text())
                
                return ScrapeResult(
                    id=task.id,
                    status="success",
                    data=ScrapeResultData(
                        play_count=play_count, # Might be 0 if not found via JSON
                        digg_count=digg_count,
                        comment_count=comment_count,
                        share_count=share_count
                    )
                )

        except Exception as e:
            logger.exception(f"Scrape error for {task.id}: {e}")
            return ScrapeResult(id=task.id, status="error", error_message=str(e))


@app.post("/api/v1/analytics/scrape", response_model=ScrapeResponse)
async def scrape_analytics(
    request: ScrapeRequest,
    auth_token: str = Header(None, alias="X-Upload-Auth"),
):
    validate_secret_token(auth_token)
    
    tasks = []
    for task in request.tasks:
        tasks.append(scrape_single_video(task))
    
    results = await asyncio.gather(*tasks)
    return ScrapeResponse(results=results)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
