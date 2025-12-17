# TikTok Auto Uploader API

This project provides a FastAPI-based API to automate the uploading of videos to TikTok. It's designed to run on a server (like a Hetzner VPS) and allows external applications to trigger video uploads by sending the video file, a TikTok session cookie, and other metadata.

**New in v2.0:** Unified Playwright Architecture. The project now uses Playwright (Python) for both login and uploads, ensuring maximum stealth and eliminating the need for a separate Node.js signature service.

## Table of Contents

1.  [Features](#features)
2.  [Prerequisites](#prerequisites)
3.  [Installation](#installation)
    *   [System Setup (Ubuntu/Debian)](#system-setup-ubuntudebian)
    *   [Project Setup](#project-setup)
    *   [Systemd Service Configuration](#systemd-service-configuration)
    *   [Reinstalling & Updating](#reinstalling--updating)
4.  [GUI Usage](#gui-usage)
5.  [CLI Usage](#cli-usage)
6.  [API Usage](#api-usage)
    *   [Endpoint](#endpoint)
    *   [Request Parameters](#request-parameters)
    *   [Example cURL Command](#example-curl-command)
    *   [Image Fade-In Endpoint](#image-fade-in-endpoint)
7.  [Troubleshooting](#troubleshooting)
8.  [Project Structure](#project-structure)
9.  [Security Notes](#security-notes)

## 1. Features

*   **Stealth Uploads**: Uses Playwright with CDP patches to mimic a real browser, bypassing bot detection.
*   **Video Upload**: Uploads video files to TikTok.
*   **Session Management**: Uses provided TikTok session cookies (pickle files) for authentication.
*   **Customizable Captions**: Allows setting custom video captions.
*   **Scheduling**: Supports scheduling video uploads for a future time.
*   **Visibility Control**: Configures video visibility (public, private).
*   **Interaction Settings**: Controls comments, duets, and stitches.
*   **Branded Content & AI Labeling**: Options for branded content and AI-generated content labels.
*   **Image Fade-In Videos**: Converts single images into short fade-in MP4 clips through a dedicated endpoint for thumbnails or preview reels.
*   **YouTube Download**: Directly download and upload videos from YouTube URLs.
*   **Desktop GUI**: A user-friendly graphical interface for managing uploads and users.
*   **CLI Support**: Command-line interface for scripting and headless operations.
*   **Advanced Stealth Architecture (v2.2)**:
    *   **Smart WebRTC Mocking**: Instead of blocking WebRTC (which can trigger anti-fraud checks), the system mocks the API to appear functional but returns no IP candidates, effectively hiding your local IP without raising flags.
    *   **Dual-Source Proxy Sync**: Automatically detects proxy location using `ipapi.co` (Primary/HTTPS) and `ip-api.com` (Fallback) to ensure perfect synchronization with TikTok's Geo-IP databases.
    *   **Timezone Force-Override**: Allows manual enforcement of a specific timezone (e.g., "America/Chicago") via CLI for cases where even databases disagree.
    *   **Fingerprinting Protection**: Spoofs WebGL Vendor (Intel Iris), Canvas noise, AudioContext noise, and Font enumeration.
    *   **Hardware Spoofing**: Masks true CPU cores and RAM (reports 4 cores, 8GB RAM).
    *   **Signer Isolation**: Runs signature scripts in a separate, isolated background page to prevent interference with the main TikTok site.
    *   **Signer Isolation**: Runs signature scripts in a separate, isolated background page to prevent interference with the main TikTok site.
    *   **Safe Mode (Stability)**: `SignupBrowser` includes a "Safe Mode" for manual interactions (Login/Signup), essentially disabling aggressive WebGL/Codec spoofing to prevent browser crashes during CAPTCHA or verification challenges.
    *   **Advanced Account Warmup**: Automated warmup system (`WarmupBrowser`) implementing the "Advanced Humanization & Niche Training Protocol". Simulates human behavior with defined archetypes (Engaged, Skip), non-linear mouse paths (Bézier), and niche-specific content interactions.

## 2. Prerequisites

Before you begin, ensure your server (e.g., Hetzner VPS running Ubuntu/Debian) has the following:

*   **Python 3.8+**: The project is built with Python.
*   **pip**: Python package installer.
*   **git**: For cloning the repository.
*   **ffmpeg**: For video processing.
*   **Systemd**: For running the API as a background service.
*   **python3-tk**: Required for the GUI (on Linux).

*Note: Node.js is NO LONGER required.*

## 3. Installation

Follow these steps to set up the TikTok Auto Uploader API on your server.

### Automated installer script

If you are preparing a fresh Ubuntu/Debian server, you can run the bundled installer instead of typing each command manually.
From the repository root execute:

```bash
sudo ./scripts/install-ubuntu-api.sh
```

The script performs the full workflow described below: it updates the system, installs Python prerequisites, creates the `tiktokapi` user, installs the Python dependencies (including Playwright Chromium), writes `/etc/tiktok-uploader-api.env` with an `UPLOAD_SECRET`, deploys the recommended `systemd` unit, and enables the service. It prints the new upload secret so you can copy it into your worker.

Optional arguments let you customize file locations (see `--repo-dir`, `--env-file`, `--service-file`), seed your own `UPLOAD_SECRET`, or skip the systemd reload/enable step while still preparing the files.

The installer now creates a `.venv` inside the repository and runs `uvicorn` from that virtual environment so every deployment uses the exact Python dependencies that were installed for the project.

You can still follow the manual steps below if you prefer to control each phase yourself.

### System Setup (Ubuntu/Debian)

1.  **Update System Packages**:
    ```bash
    sudo apt update && sudo apt upgrade -y
    ```

2.  **Install Python, pip, git, and ffmpeg**:
    ```bash
    sudo apt install python3 python3-pip git ffmpeg -y
    ```

3.  **Create a dedicated system user**:
    It's best practice to run services under a non-root user.
    ```bash
    sudo adduser --system --no-create-home --group tiktokapi
    ```

### Project Setup

1.  **Clone the repository**:
    ```bash
    git clone git@github.com:swdevpa/TiktokAutoUploader.git /opt/TiktokAutoUploader
    ```
    *(Replace `https://github.com/your-repo/TiktokAutoUploader.git` with your actual repository URL)*

2.  **Change ownership of the project directory**:
    ```bash
    sudo chown -R tiktokapi:tiktokapi /opt/TiktokAutoUploader
    ```

3.  **Navigate to the project directory**:
    ```bash
    cd /opt/TiktokAutoUploader
    ```

4.  **Install Python dependencies**:
    ```bash
    sudo -H -u tiktokapi python3 -m pip install -r requirements.txt
    ```

5.  **Install Playwright Browsers**:
    The project now uses Playwright Python. You need to install the browser binaries.
    ```bash
    sudo -H -u tiktokapi python3 -m playwright install chromium
    ```

### Systemd Service Configuration

To ensure the API runs continuously and restarts automatically, set it up as a systemd service.

1.  **Create the systemd service file**:
    ```bash
    sudo nano /etc/systemd/system/tiktok-uploader-api.service
    ```

2.  **Add the following content to the file**:
    ```ini
    [Unit]
    Description=TikTok Uploader API Service
    After=network.target

    [Service]
    User=tiktokapi
    Group=tiktokapi
    WorkingDirectory=/opt/TiktokAutoUploader
    EnvironmentFile=/etc/tiktok-uploader-api.env
    ExecStart=/bin/bash -c "PATH=/opt/TiktokAutoUploader/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin /opt/TiktokAutoUploader/.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000"
    Restart=always
    RestartSec=10
    SyslogIdentifier=tiktok-uploader-api

    [Install]
    WantedBy=multi-user.target
    ```
    *Note: The `PLAYWRIGHT_BROWSERS_PATH` environment variable is no longer strictly required if you installed browsers globally or in the default location for the user, but if you used a custom location, ensure it's set.*

3.  **Reload systemd daemon**:
    ```bash
    sudo systemctl daemon-reload
    ```

4.  **Enable and start the service**:
    ```bash
    sudo systemctl enable tiktok-uploader-api
    sudo systemctl start tiktok-uploader-api
    ```

5.  **Check the service status**:
    ```bash
    sudo systemctl status tiktok-uploader-api
    ```
    You should see `Active: active (running)`.

6.  **Monitor logs for issues**:
    ```bash
    sudo journalctl -u tiktok-uploader-api -f
    ```

### Reinstalling & Updating

If you delete the `.venv` folder or need to pull a fresh version of the code, follow these steps from the `/opt/TiktokAutoUploader` directory on your server:

1.  **Stop the service so the files can be updated safely**:
    ```bash
    sudo systemctl stop tiktok-uploader-api
    ```

2.  **Pull the latest code** (adjust the branch name as needed):
    ```bash
    cd /opt/TiktokAutoUploader
    sudo -H -u tiktokapi git fetch --all
    sudo -H -u tiktokapi git pull --ff-only
    ```

3.  **Recreate the Python virtual environment** (install `python3-venv` first if necessary):
    ```bash
    sudo apt install -y python3-venv
    sudo -H -u tiktokapi python3 -m venv /opt/TiktokAutoUploader/.venv
    sudo chown -R tiktokapi:tiktokapi /opt/TiktokAutoUploader/.venv
    ```

4.  **Install or upgrade the Python dependencies inside that venv**:
    ```bash
    sudo -H -u tiktokapi /opt/TiktokAutoUploader/.venv/bin/python -m pip install --upgrade pip
    sudo -H -u tiktokapi /opt/TiktokAutoUploader/.venv/bin/python -m pip install -r /opt/TiktokAutoUploader/requirements.txt
    ```

5.  **Install Playwright Browsers**:
    ```bash
    sudo -H -u tiktokapi /opt/TiktokAutoUploader/.venv/bin/python -m playwright install chromium
    ```

6.  **Reload systemd and restart the service**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart tiktok-uploader-api
    ```

## 4. GUI Usage
 
 The project includes a Tkinter-based GUI for easy management.
 
 1.  **Run the GUI**:
     ```bash
     python3 gui.py
     ```
 
 2.  **Features**:
     *   **Upload Tab**: Select user, video (local or YouTube URL), caption, and scheduling options.
     *   **Users Tab**: Add or remove TikTok users (login via browser).
     *   **Videos Tab**: View available videos in the `VideosDirPath`.
 
 ## 5. CLI Usage
 
 The CLI allows for headless operations and scripting.
 
 1.  **Login**:
     ```bash
     python3 cli.py login -n <username>
     ```
 
 2.  **Upload**:
     ```bash
     python3 cli.py upload -u <username> -v <video_filename> -t "Caption"
     ```
     Or using a YouTube URL:
     ```bash
     python3 cli.py upload -u <username> -yt <youtube_url> -t "Caption"
     ```

     **Note on Proxies:**
     The `-p` or `--proxy` argument supports authenticated proxies in the format:
     `http://user:password@host:port`
     or
     `http://host:port` (for unauthenticated proxies).
 
 3.  **List Resources**:
     ```bash
     python3 cli.py show -u  # List users
     python3 cli.py show -v  # List videos
     ```
 
 ## 6. API Usage

The API exposes a single endpoint for uploading videos.

### Endpoint

`POST http://your_server_ip:8000/upload`

### Request Parameters

The API expects a `multipart/form-data` request with the following fields:

*   `video_file` (File): The video file to upload.
*   `session_file` (File): The TikTok session cookie file (e.g., `tiktok_session-yourusername.cookie`).
*   `caption` (String): The video caption.
*   `X-Upload-Auth` (Header): Upload secret header required by every endpoint (`X-Upload-Auth: <your secret>`).
*   `schedule_time` (Integer, optional, default: `0`): Unix timestamp for scheduling. `0` means immediate upload.
*   `allow_comment` (Integer, optional, default: `1`): `1` to allow comments, `0` to disallow.
*   `allow_duet` (Integer, optional, default: `0`): `1` to allow duets, `0` to disallow.
*   `allow_stitch` (Integer, optional, default: `0`): `1` to allow stitches, `0` to disallow.
*   `visibility_type` (Integer, optional, default: `0`): `0` for public, `1` for private.
*   `brand_organic_type` (Integer, optional, default: `0`): `0` for non-branded, `1` for branded.
*   `branded_content_type` (Integer, optional, default: `0`): `0` for non-branded, `1` for branded.
*   `ai_label` (Integer, optional, default: `0`): `0` for no AI label, `1` for AI-generated content label.
*   `proxy` (String, optional): Proxy string to use for the upload (e.g., `user:pass@host:port`).
*   `datacenter` (String, optional): Specific datacenter preference (if supported by backend logic).

### Response

The API returns a JSON object upon success:
```json
{
  "message": "Video uploaded successfully!",
  "video_id": "v09044g40000c..."
}
```

### Example cURL Command

Replace `5.161.110.4` with your server's IP address, and adjust file paths and parameters as needed.

```bash
curl -X POST "http://5.161.110.4:8000/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -H "X-Upload-Auth: <your secret>" \
  -F "video_file=@/Users/philipp/Documents/Projects/TiktokAutoUploader/VideosDirPath/upscaled/4efc3f04-c3a5-40fa-8570-1db4d94a6c47.mp4;type=video/mp4" \
  -F "session_file=@/Users/philipp/Documents/Projects/TiktokAutoUploader/CookiesDir/tiktok_session-lifewithmax.cookie;type=application/octet-stream" \
  -F "caption=Dies ist meine private Videobeschreibung #privat #apiupload" \
  -F "schedule_time=0" \
  -F "allow_comment=1" \
  -F "allow_duet=0" \
  -F "allow_stitch=0" \
  -F "visibility_type=1" \
  -F "brand_organic_type=0" \
  -F "branded_content_type=0" \
  -F "ai_label=0"
```

### Image Slideshow / Fade-In Endpoint
 
 `POST http://your_server_ip:8000/fadein-from-image`
 
 Use this endpoint to create a video from one or more images. It supports an initial fade-in from black and smooth crossfade transitions between multiple images. It returns an MP4 file.
 
 #### Request Parameters
 
 *   `image_file` (File): Single source image (for backward compatibility).
 *   `image_files` (File list): Multiple source images for a slideshow. You can pass this field multiple times (e.g., `-F "image_files=@img1.jpg" -F "image_files=@img2.jpg"`).
 *   `duration` (Float, optional, default: `0.0`): **Legacy parameter** for backward compatibility. If `fade_duration` and `image_duration` are not set, this value is used for both.
 *   `fade_duration` (Float, optional): **Initial fade-in duration** in seconds. Set to `0` to disable the start fade-in. If not provided, defaults to `duration`.
 *   `image_duration` (Float, optional): Duration in seconds for each image to be displayed. If not provided, defaults to `duration`.
 *   `transition_duration` (Float, optional, default: `0.3`): Duration of the crossfade transition between images.
 *   `header_text` (String, optional): Text to be overlaid on the top center of the video. Useful for titles or headers (e.g., "POV: ...").
 *   `X-Upload-Auth` (Header): Upload secret header (`X-Upload-Auth: <your secret>`).
 
 #### Examples
 
 **1. Single Image with Fade-In (Intro):**
 ```bash
 curl -X POST "http://5.161.110.4:8000/fadein-from-image" \
   -H "X-Upload-Auth: <your secret>" \
   -F "image_file=@/path/to/cover.jpg" \
   -F "fade_duration=5" \
   -o intro.mp4
 ```
 
 **2. Slideshow without Initial Fade-In:**
 To create a slideshow with 3-second images and 0.5-second transitions, but **no** fade-in from black at the start:
 ```bash
 curl -X POST "http://5.161.110.4:8000/fadein-from-image" \
   -H "X-Upload-Auth: <your secret>" \
   -F "image_files=@/path/to/image1.jpg" \
   -F "image_files=@/path/to/image2.jpg" \
   -F "fade_duration=0" \
   -F "image_duration=3" \
   -F "transition_duration=0.5" \
   -o slideshow.mp4
 ```

 **3. Video with Header Text:**
 To create a video with a text overlay at the top:
 ```bash
 curl -X POST "http://5.161.110.4:8000/fadein-from-image" \
   -H "X-Upload-Auth: <your secret>" \
   -F "image_file=@/path/to/image.jpg" \
   -F "header_text=POV: You found this hack" \
   -o video_with_text.mp4
 ```

### Analytics Scraper Endpoint

`POST http://your_server_ip:8000/api/v1/analytics/scrape`

Use this endpoint to scrape public video metrics (views, likes, comments, shares) from TikTok without logging in (Guest Mode).

#### Request Payload (JSON)

```json
{
  "tasks": [
    {
      "id": "unique_task_id",
      "video_url": "https://www.tiktok.com/@user/video/1234567890",
      "proxy": "user:pass@host:port"
    }
  ]
}
```

*   `id`: A unique identifier for the task (e.g., your database ID).
*   `video_url`: The full URL of the TikTok video.
*   `proxy`: (Optional but recommended) The proxy string to use for this specific scrape.

#### Response Payload (JSON)

```json
{
  "results": [
    {
      "id": "unique_task_id",
      "status": "success",
      "data": {
        "play_count": 10500,
        "digg_count": 1200,
        "comment_count": 50,
        "share_count": 10
      }
    }
  ]
}
```

*   `status`: `success`, `video_removed`, `processing`, `scrape_failed`, or `error`.
*   `data`: Contains the metrics if status is `success`.

### Account Warmup Endpoint

`POST http://your_server_ip:8000/warmup`

`POST http://your_server_ip:8000/warmup`

Starts a background process to warm up an account using the **Advanced Humanization Protocol**.

*   **Watchtime Archetypes**: Simulates different viewer types ("Instant Skip", "Drop-Off", "Engaged View").
*   **Niche Training**: Scans video content for keywords (e.g., `#tech`, `#iphone`) to boost engagement for target niches and skip irrelevant content.
*   **Humanized Input**: Uses Bézier curves for mouse movement and realistic jitter.
*   **Conditional Liking**: Likes only occur if the video was significantly watched (>70%).
*   **Advanced Interactions**: Includes "Share-Trick" (fake sharing), "Profile Deep-Dive", and "Scroll-Back" moves.

#### Request Parameters

*   `session_file` (File): The TikTok session cookie file.
*   `proxy` (String): The proxy string (`user:pass@host:port`).
*   `duration_minutes` (Integer, optional, default: `15`): Duration of the warmup session.
*   `callback_url` (String, optional): A webhook URL to receive the result JSON upon completion.
*   `X-Upload-Auth` (Header): Upload secret.

#### Webhook Payload (on completion)

```json
{
  "status": "success",
  "proxy": "...",
  "session": "...",
  "actions": {
    "watched_seconds": 840,
    "scrolls": 50,
    "likes": 2
  }
}
```

#### Example cURL

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/scrape" \
  -H "X-Upload-Auth: <your secret>" \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "id": "test_1",
        "video_url": "https://www.tiktok.com/@user/video/...",
        "proxy": "user:pass@host:port"
      }
    ]
  }'
```

## 7. Troubleshooting

*   **`ModuleNotFoundError: No module named 'playwright'`**:
    Ensure you installed the requirements: `pip install -r requirements.txt`.

*   **`playwright._impl._api_types.Error: Executable doesn't exist at ...`**:
    You need to install the browser binaries: `playwright install chromium`.

*   **`Error during upload: [Errno 2] No such file or directory: 'ffmpeg'`**:
    `ffmpeg` is not installed or not in the system's PATH. Install it using `sudo apt install ffmpeg -y`.

*   **`fastapi` raises `RuntimeError: Form data requires `python-multipart` to be installed`**:
    FastAPI’s form parsing requires `python-multipart`. That dependency is now in `requirements.txt`.

*   **`Page.goto: Timeout 120000ms exceeded`**:
    This usually indicates a slow proxy connection or incorrect proxy credentials.
    *   Ensure your proxy string follows the `http://user:pass@host:port` format.
    *   Try a different proxy location or provider if the connection is too slow.
    *   The script is optimized to wait only for the initial connection (`commit`), so persistent timeouts suggest a network block or failure.

## 8. Project Structure

```
/opt/TiktokAutoUploader/
├── api.py                  # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── tiktok_uploader/
│   ├── __init__.py
│   ├── basics.py
│   ├── bot_utils.py
│   ├── StealthBrowser.py   # NEW: Handles browser automation with Playwright & CDP Stealth
│   ├── Config.py
│   ├── cookies.py
│   ├── gemini_caption.py
│   ├── metadata_spoofing.py
│   ├── tiktok.py           # Core TikTok upload logic (Refactored)
│   ├── Video.py
│   ├── videotoolbox_upscale.py
│   └── tiktok-signature/   # JavaScript files for signature generation (injected into browser)
│       ├── javascript/
│       │   ├── signer.js
│       │   ├── webmssdk.js
│       │   └── xbogus.js
├── CookiesDir/             # Directory to store TikTok session cookie files
├── VideosDirPath/          # Directory for video files (e.g., upscaled videos)
└── ... (other project files)
```

## 9. Security Notes

### Upload secret (`UPLOAD_SECRET`)

The `/upload` endpoint now rejects any request missing the shared secret in the `X-Upload-Auth` header. Only callers that know the secret (your Cloudflare Worker plus any trusted scripts) will succeed.

1.  Generate a strong secret on your Hetzner server:
    ```bash
    openssl rand -hex 32
    ```

2.  Store it in a root-owned file so systemd can inject it:
    ```bash
    sudo tee /etc/tiktok-uploader-api.env <<'EOF'
    UPLOAD_SECRET=your_generated_secret_here
    EOF
    ```
    Replace `your_generated_secret_here` with the value from step 1.

3.  Lock down the file:
    ```bash
    sudo chmod 600 /etc/tiktok-uploader-api.env
    sudo chown root:root /etc/tiktok-uploader-api.env
    ```

4.  Reload systemd and restart the service so it picks up the secret:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart tiktok-uploader-api
    ```

5.  Configure your worker to send `X-Upload-Auth: your_generated_secret_here` when calling `/upload`.

To rotate the secret later, update `/etc/tiktok-uploader-api.env`, repeat step 4, and push the new secret to the worker.

## 10. Cloudflare Tunnel (empfohlen)

Ein Cloudflare Tunnel erlaubt deinem Worker oder einem Browser, `https://your-domain/upload` zu erreichen, während du intern weiter `uvicorn` auf `http://localhost:8000` laufen lässt.

1.  **Installiere `cloudflared`** auf dem Hetzner-Server:
    ```bash
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
    sudo dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    ```

2.  **Authentifiziere dich bei Cloudflare** (öffne den Link im Browser, wähle deine Zone aus):
    ```bash
    cloudflared login
    ```

3.  **Erstelle einen benannten Tunnel**:
    ```bash
    cloudflared tunnel create tiktok-uploader
    ```

4.  **Definiere eine Tunnel-Konfiguration** in `/etc/cloudflared/config.yml`:
    ```yaml
    tunnel: <Tunnel-ID>          # aus cloudflared tunnel create
    credentials-file: /root/.cloudflared/<Tunnel-ID>.json

    ingress:
      - hostname: upload.example.com
        service: http://localhost:8000
      - service: http_status:404
    ```
    Ersetze `upload.example.com` mit der Domain/Subdomain, die dein Worker anspricht.

5.  **Füge eine DNS-Route hinzu** (wenn du Cloudflare DNS verwendest):
    ```bash
    cloudflared tunnel route dns tiktok-uploader upload.example.com
    ```

6.  **Starte den Tunnel als Systemd-Service**:
    ```bash
    sudo cloudflared service install
    sudo systemctl enable cloudflared
    sudo systemctl start cloudflared
    ```

7.  **Teste die Verbindung**: `curl https://upload.example.com/upload` (mit `X-Upload-Auth`) sollte deine FastAPI-Richtlinie treffen.

8.  **Aktualisiere den Cloudflare Worker** so, dass er `fetch("https://upload.example.com/upload", { headers: {"X-Upload-Auth": "..."} })` nutzt. TLS und das Cloudflare-Edge-Netzwerk sind jetzt inklusive.

Mit diesem Setup musst du keine eigenen TLS-Zertifikate verwalten. Der Tunnel macht deine lokale API über eine dedizierte Cloudflare-Domain erreichbar, und dein Worker bleibt der einzige autorisierte Client dank `UPLOAD_SECRET`.
