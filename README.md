# TikTok Auto Uploader API

This project provides a FastAPI-based API to automate the uploading of videos to TikTok. It's designed to run on a server (like a Hetzner VPS) and allows external applications to trigger video uploads by sending the video file, a TikTok session cookie, and other metadata.

## Table of Contents

1.  [Features](#features)
2.  [Prerequisites](#prerequisites)
3.  [Installation](#installation)
    *   [System Setup (Ubuntu/Debian)](#system-setup-ubuntudebian)
    *   [Project Setup](#project-setup)
    *   [Node.js and Playwright Setup](#nodejs-and-playwright-setup)
    *   [Systemd Service Configuration](#systemd-service-configuration)
4.  [API Usage](#api-usage)
    *   [Endpoint](#endpoint)
    *   [Request Parameters](#request-parameters)
    *   [Example cURL Command](#example-curl-command)
    *   [Image Fade-In Endpoint](#image-fade-in-endpoint)
5.  [Troubleshooting](#troubleshooting)
6.  [Project Structure](#project-structure)
7.  [Security Notes](#security-notes)

## 1. Features

*   **Video Upload**: Uploads video files to TikTok.
*   **Session Management**: Uses provided TikTok session cookies (pickle files) for authentication.
*   **Customizable Captions**: Allows setting custom video captions.
*   **Scheduling**: Supports scheduling video uploads for a future time.
*   **Visibility Control**: Configures video visibility (public, private).
*   **Interaction Settings**: Controls comments, duets, and stitches.
*   **Branded Content & AI Labeling**: Options for branded content and AI-generated content labels.
*   **Image Fade-In Videos**: Converts single images into short fade-in MP4 clips through a dedicated endpoint for thumbnails or preview reels.

## 2. Prerequisites

Before you begin, ensure your server (e.g., Hetzner VPS running Ubuntu/Debian) has the following:

*   **Python 3.8+**: The project is built with Python.
*   **pip**: Python package installer.
*   **Node.js and npm**: Required for Playwright's signature helper. Node.js 18 or higher is recommended.
*   **git**: For cloning the repository.
*   **ffmpeg**: For video processing.
*   **Systemd**: For running the API as a background service.

## 3. Installation

Follow these steps to set up the TikTok Auto Uploader API on your server.

### Automated installer script

If you are preparing a fresh Ubuntu/Debian server, you can run the bundled installer instead of typing each command manually.
From the repository root execute:

```bash
sudo ./scripts/install-ubuntu-api.sh
```

The script performs the full workflow described below: it updates the system, installs Python/Node.js prerequisites, creates the `tiktokapi` user, installs the Python and Node dependencies (including Playwright Chromium), writes `/etc/tiktok-uploader-api.env` with an `UPLOAD_SECRET`, deploys the recommended `systemd` unit, and enables the service. It prints the new upload secret so you can copy it into your worker.

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

### Node.js and Playwright Setup

The TikTok signature helper requires Node.js and Playwright browser binaries.

1.  **Install Node.js (if not already installed or if an older version is present)**:
    It's crucial to have a recent version of Node.js (18+).
    ```bash
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
    ```
    *Note: If you encounter issues with `libnode-dev` during Node.js installation, you might need to remove the old `libnode-dev` package first: `sudo apt remove libnode-dev`.*

2.  **Install Playwright browser binaries**:
    Navigate to the `tiktok-signature` directory and install Chromium.
    ```bash
    cd /opt/TiktokAutoUploader/tiktok_uploader/tiktok-signature
    sudo -H -u tiktokapi PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers npx playwright install chromium
    ```
    This command installs the browser binaries into a local directory (`.playwright-browsers`) within the `tiktok-signature` folder, ensuring they are accessible to the `tiktokapi` user.

3.  **Verify Playwright installation (optional)**:
    You can check if the browsers are installed correctly by listing the contents of the `.playwright-browsers` directory.
    ```bash
    ls -l /opt/TiktokAutoUploader/tiktok_uploader/tiktok-signature/.playwright-browsers
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
Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/TiktokAutoUploader/tiktok_uploader/tiktok-signature/.playwright-browsers"
ExecStart=/bin/bash -c "PATH=/opt/TiktokAutoUploader/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin /opt/TiktokAutoUploader/.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000"
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=tiktok-uploader-api

    [Install]
    WantedBy=multi-user.target
    ```
    *Note the `Environment="PLAYWRIGHT_BROWSERS_PATH=..."` line. This is crucial for the systemd service to find the Playwright browser binaries.*

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

7.  **Install Python dependencies inside the virtualenv as `tiktokapi` before starting the service**:
    ```bash
    sudo -H -u tiktokapi /opt/TiktokAutoUploader/.venv/bin/python -m pip install -r /opt/TiktokAutoUploader/requirements.txt
    ```

## 4. API Usage

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

### Image Fade-In Endpoint

`POST http://your_server_ip:8000/fadein-from-image`

Use this endpoint when you need a smooth 5-second fade from black to an image (for intro slides, thumbnails, or preview reels). It returns an MP4 file with the fade effect. The server calls the system `ffmpeg` binary to build the video at 24 fps, so make sure the `ffmpeg` package is installed and on the same `PATH` that the systemd service uses.

#### Request Parameters

*   `image_file` (File): The source image that should appear after the fade-in. Supported MIME types are JPEG, PNG, WEBP, GIF, SVG, BMP, and TIFF.
*   `duration` (Float, optional, default: `5.0`): Fade duration in seconds. The endpoint enforces `0 < duration ≤ 60` unless you override the `MAX_IMAGE_FADE_DURATION_SECONDS` env var.
*   `X-Upload-Auth` (Header): Same upload secret header as `/upload`. Every request must include `X-Upload-Auth: <your secret>`.

The server also validates `MAX_IMAGE_UPLOAD_BYTES` (defaults to 10 MB) and pads the video to a 16-pixel-aligned resolution to satisfy encoder constraints.

#### Example cURL Command

```bash
curl -X POST "http://5.161.110.4:8000/fadein-from-image" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -H "X-Upload-Auth: <your secret>" \
  -F "image_file=@/Users/philipp/Documents/Projects/TiktokAutoUploader/temp_images/cover.jpg;type=image/jpeg" \
  -F "duration=5"
```

## 5. Troubleshooting

*   **`ModuleNotFoundError: No module named 'fake_useragent'`**:
    This indicates that Python dependencies are not installed or not accessible to the user running the API. Ensure you ran `sudo -H -u tiktokapi python3 -m pip install -r requirements.txt` correctly.

*   **`Error during upload: [Errno 2] No such file or directory: 'ffmpeg'`**:
    `ffmpeg` is not installed or not in the system's PATH. Install it using `sudo apt install ffmpeg -y`. If it's installed but still not found, ensure the `PATH` environment variable in your systemd service file includes the directory where `ffmpeg` is located (e.g., `/usr/bin`).

*   **`Playwright browser binaries are missing. Run 'npx playwright install chromium' inside tiktok_uploader/tiktok-signature.`**:
    This means Playwright cannot find the browser it needs. Ensure you have:
    1.  Installed Node.js and npm.
    2.  Navigated to `/opt/TiktokAutoUploader/tiktok_uploader/tiktok-signature`.
    3.  Run `sudo -H -u tiktokapi PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers npx playwright install chromium`.
    4.  Added `Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/TiktokAutoUploader/tiktok_uploader/tiktok-signature/.playwright-browsers"` to your systemd service file.
    5.  Reloaded and restarted the systemd service.

*   **`Failed at step USER spawning /usr/bin/python3: No such process` (systemd error)**:
    This usually means the `User` or `Group` specified in the systemd service file is incorrect or the user doesn't have permissions to execute the `ExecStart` command.
    1.  Verify the `tiktokapi` user exists (`id tiktokapi`).
    2.  Ensure `User=tiktokapi` and `Group=tiktokapi` are correctly set in `/etc/systemd/system/tiktok-uploader-api.service`.
    3.  Confirm the `WorkingDirectory` is correct and owned by `tiktokapi`.
    4.  Ensure the `ExecStart` command is correct and the `python3` executable path is valid (`which python3`).

*   **`Node.js 12.22.9. Playwright requires Node.js 14 or higher.`**:
    Your Node.js version is too old. Follow the Node.js installation steps in [Node.js and Playwright Setup](#nodejs-and-playwright-setup) to upgrade to a supported version (e.g., Node.js 18).

## 6. Project Structure

```
/opt/TiktokAutoUploader/
├── api.py                  # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── tiktok_uploader/
│   ├── __init__.py
│   ├── basics.py
│   ├── bot_utils.py
│   ├── Browser.py          # Handles browser automation with Playwright
│   ├── Config.py
│   ├── cookies.py
│   ├── gemini_caption.py
│   ├── metadata_spoofing.py
│   ├── tiktok.py           # Core TikTok upload logic
│   ├── Video.py
│   ├── videotoolbox_upscale.py
│   └── tiktok-signature/   # Node.js project for TikTok signature generation
│       ├── browser.js
│       ├── index.js
│       ├── package-lock.json
│       ├── package.json
│       ├── utils.js
│       ├── javascript/
│       │   ├── signer.js
│       │   ├── webmssdk.js
│       │   └── xbogus.js
│       └── .playwright-browsers/ # Playwright browser binaries installed here
├── CookiesDir/             # Directory to store TikTok session cookie files
├── VideosDirPath/          # Directory for video files (e.g., upscaled videos)
└── ... (other project files)

## 7. Security Notes

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

## 8. Cloudflare Tunnel (empfohlen)

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
