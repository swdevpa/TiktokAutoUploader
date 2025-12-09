# TikTok Auto Uploader - Technische Systembeschreibung (Maximaler Detailgrad)

## 1. Systemüberblick

Das **TikTok Auto Uploader System** ist eine hochspezialisierte Automatisierungslösung für das programmgesteuerte Hochladen von Videoinhalten auf TikTok. Es wurde entwickelt, um menschliches Verhalten zu simulieren und fortschrittliche Anti-Bot-Mechanismen zu umgehen. Das System basiert auf einer **Python-Backend-Architektur**, die über eine **FastAPI-Schnittstelle** und ein **CLI-Tool** gesteuert wird.

Kernstück ist der **Stealth-Browser-Engine** auf Basis von **Playwright**, der eine vollständige Browserumgebung emuliert, inklusive Fingerprinting-Schutz, Proxy-Management und Hardware-Spoofing.

---

## 2. Architektur & Komponenten

### 2.1 Backend API (`api.py`)
Die API dient als zentraler Einstiegspunkt für externe Dienste (z.B. Auto-Worker, Cloudflare Workers).

*   **Framework**: FastAPI (Asynchron, High-Performance).
*   **Server**: Uvicorn (ASGI).
*   **Logging**: Rotierende Logs (`logs/api.log`, max 5MB, 3 Backups) + Stdout.
*   **Endpoints**:

    #### `POST /upload`
    Hauptendpunkt für den Video-Upload.
    *   **Header**: `X-Upload-Auth` (Muss mit `UPLOAD_SECRET` übereinstimmen).
    *   **Body (Multipart/Form-Data)**:
        *   `video_file` (File): Das Video (MP4, MOV, AVI, MKV). Max Größe via `MAX_VIDEO_UPLOAD_BYTES` (Default 250MB).
        *   `session_file` (File): Die TikTok Session Cookies (`.cookie` Pickle-Datei). Max Größe 512KB.
        *   `caption` (String): Videobeschreibung inkl. Hashtags.
        *   `schedule_time` (Int): Unix Timestamp für geplanten Upload (0 = sofort).
        *   `allow_comment`, `allow_duet`, `allow_stitch` (Int): 1=Ja, 0=Nein.
        *   `visibility_type` (Int): 0=Public, 1=Private, 2=Friends.
        *   `brand_organic_type`, `branded_content_type` (Int): Flags für Werbekennzeichnung.
        *   `ai_label` (Int): 1=AI Generated Content.
        *   `proxy` (String): Optionaler Proxy (`user:pass@host:port`).
        *   `datacenter` (String): Optionaler Datacenter-Parameter.
    *   **Response**: JSON `{"message": "Video uploaded successfully!", "video_id": "..."}` oder HTTP 500 bei Fehler.

    #### `POST /fadein-from-image`
    Generiert aus Bildern MP4-Videos mit Fade-In-Effekten und Text-Overlays mittels FFmpeg.
    *   **Parameter**: `image_files` (List), `fade_duration`, `image_duration`, `transition_duration`, `header_text`.
    *   **Logik**: Nutzt FFmpeg `xfade` Filter für Übergänge und `drawtext` für Overlays.

    #### `POST /api/v1/analytics/scrape`
    Stateless Endpoint zum scrapen von Video-Metriken (Views, Likes, etc.) im Guest-Mode.
    *   **Payload** (JSON):
        ```json
        {
          "tasks": [
            {
              "id": "unique_id_1",
              "video_url": "https://www.tiktok.com/@user/video/123",
              "proxy": "user:pass@host:port" // Optional
            }
          ]
        }
        ```
    *   **Response** (JSON):
        ```json
        {
          "results": [
            {
              "id": "unique_id_1",
              "status": "success", // success, video_removed, error, processing, scrape_failed
              "data": {
                "play_count": 1000,
                "digg_count": 100,
                "comment_count": 10,
                "share_count": 5
              },
              "error_message": null
            }
          ]
        }
        ```
    *   **Logik**: Startet `StealthBrowser` im Guest-Mode (ohne Cookies), navigiert zur URL und extrahiert Daten.
        1.  Versucht JSON (`SIGI_STATE` oder `Universal Data`) zu parsen (zuverlässiger).
        2.  Fallback auf CSS-Selektoren (`[data-e2e="like-count"]` etc.) wenn JSON fehlt.
        3.  Erkennt "Video nicht verfügbar", Captchas oder andere Fehlerzustände.
    *   **Concurrency**: Limitiert durch `SCRAPE_CONCURRENCY_LIMIT` (Default: 5).

### 2.2 Command Line Interface (`cli.py`)
Ermöglicht die manuelle Steuerung und Verwaltung via Terminal.
*   **Dependencies**: `argparse`, `asyncio`.
*   **Commands**:
    *   `login -n <name>`: Startet Headed-Browser. Wartet auf `sessionid` Cookie. Speichert in `CookiesDir/tiktok_session-<name>.cookie`.
    *   `upload -u <user> -v <video> ...`: Startet Headless-Upload. Unterstützt YouTube-URLs (`-yt`) via `yt-dlp`.
    *   `show -u | -v`: Listet verfügbare User-Sessions und Videos.

### 2.3 Core Engine (`tiktok_uploader/`)

#### A. Stealth Browser (`StealthBrowser.py`)
Die kritischste Komponente für die Umgehung von Bot-Erkennung.
*   **Klasse**: `StealthBrowser` (Context Manager).
*   **Technologie**: Microsoft Playwright (Chromium).
*   **Browser-Argumente**: `--disable-blink-features=AutomationControlled`, `--no-sandbox`, `--disable-infobars`.
*   **Guest Mode**: Optionaler Modus (`guest_mode=True`), der das Laden von Cookies verhindert und eine saubere Session garantiert.
*   **Proxy-Detection**: Fragt `http://ip-api.com/json` ab, um Zeitzone, Locale und Geolocation des Proxies zu ermitteln und den Browser-Kontext (`browser.new_context`) exakt darauf einzustellen.
*   **Stealth-Injections (JavaScript)**:
    1.  **Navigator**: Überschreibt `navigator.webdriver` mit `undefined`.
    2.  **Chrome Object**: Mockt `window.chrome`.
    3.  **Permissions**: Mockt `navigator.permissions.query` für Notifications.
    4.  **Plugins**: Mockt `navigator.plugins` Array.
    5.  **WebGL Spoofing**:
        *   `UNMASKED_VENDOR_WEBGL` -> "Intel Inc."
        *   `UNMASKED_RENDERER_WEBGL` -> "Intel Iris OpenGL Engine"
    6.  **Canvas Noise**: Überschreibt `toDataURL` und `getImageData`. Addiert zufälliges Rauschen (Noise) zu RGB-Werten, um Canvas-Fingerprinting zu verfälschen.
    7.  **AudioContext Noise**: Modifiziert `getChannelData` mit minimalem Rauschen.
    8.  **Hardware Spoofing**: `hardwareConcurrency` = 4, `deviceMemory` = 8.
    9.  **Font Enumeration**: Fügt Rauschen zu `offsetWidth`/`offsetHeight` hinzu.
    10. **WebRTC**: Entfernt `RTCPeerConnection` Objekte.

#### B. Upload Logic (`tiktok.py`)
Implementiert den Reverse-Engineered Upload-Flow der TikTok Web-Version.
*   **Methode**: `upload_video(...)`
*   **Ablauf**:
    1.  **Login Check**: Lädt Cookies, prüft Existenz von `sessionid`.
    2.  **Navigation**: Geht auf `tiktok.com` (WaitUntil: `commit`) für korrekten Referer.
    3.  **Project Creation**: `POST /api/v1/web/project/create/?type=1&aid=1988`. Erhält `project_id`.
    4.  **Upload Auth**: `GET /api/v1/video/upload/auth/`. Erhält `video_token_v5` (AWS Credentials).
    5.  **AWS S3 Upload (SigV4)**:
        *   Nutzt `requests_auth_aws_sigv4` für Signierung.
        *   `GET ...?Action=ApplyUploadInner...`: Initialisiert Upload bei TikToks VOD-Service.
        *   Erhält `UploadHost`, `StoreUri`, `Auth`, `SessionKey`.
        *   **Chunked Upload**: Teilt Video in 5MB Chunks.
        *   **CRC32**: Berechnet Checksumme für jeden Chunk (`zlib.crc32`).
        *   `POST https://{UploadHost}/{StoreUri}?partNumber=...`: Lädt Chunks hoch.
        *   `POST ...?phase=finish`: Finalisiert den Upload.
        *   `POST ...?Action=CommitUploadInner`: Bestätigt Upload beim VOD-Service.
    6.  **Publishing**:
        *   Erstellt Payload mit `post_common_info` (Privacy, Schedule) und `single_post_req_list` (Titel).
        *   **Signature Generation**: Ruft `window.generateSignature(url)` im Browser-Kontext auf.
            *   Nutzt injizierte Skripte: `signer.js`, `webmssdk.js`, `xbogus.js`.
            *   Generiert `_signature`, `X-Bogus`, `verifyFp`.
        *   `POST /tiktok/web/project/post/v1/`: Veröffentlicht das Video.
        *   **Return**: Gibt bei Erfolg die `video_id` (Vid) zurück.

#### C. Metadata Spoofing (`metadata_spoofing.py`)
Bereinigt und manipuliert Video-Metadaten vor dem Upload.
*   **Profiles**: Liste von echten Geräten (z.B. iPhone 15 Pro Max, iOS 17.4).
*   **Locations**: Liste von Großstädten mit ISO6709 Koordinaten.
*   **Prozess**:
    *   Wählt zufälliges Device-Profil und (mit 20% Wahrscheinlichkeit) eine Location.
    *   Generiert zufälligen `creation_time` (letzte 180 Tage).
    *   Setzt Kamera-Werte: ISO (50-2000), Shutter (1/30-1/500), Focal Length.
    *   Führt `ffmpeg` Befehl aus: `-map_metadata -1` (löscht alles), dann `-metadata key=value` für neue Werte.

---

## 3. Datenstrukturen & Abhängigkeiten

### 3.1 Wichtige Python-Pakete (`requirements.txt`)
*   `fastapi`, `uvicorn`: API Server.
*   `playwright`: Browser Automation.
*   `requests`, `requests-auth-aws-sigv4`: HTTP & AWS Auth.
*   `yt-dlp`: YouTube Download.
*   `imageio-ffmpeg`, `moviepy`: Videobearbeitung (Legacy/Fallback).
*   `pillow`: Bildverarbeitung.

### 3.2 Dateisystem-Struktur
```
/opt/TiktokAutoUploader/
├── api.py                  # FastAPI Entrypoint
├── cli.py                  # CLI Entrypoint
├── requirements.txt        # Dependencies
├── tiktok_uploader/        # Core Package
│   ├── StealthBrowser.py   # Playwright Wrapper & Stealth Injections
│   ├── tiktok.py           # Upload Flow Implementation
│   ├── metadata_spoofing.py# FFmpeg Metadata Logic
│   ├── bot_utils.py        # Helper (CRC32, Regex)
│   ├── Config.py           # Configuration Manager
│   └── tiktok-signature/   # JS Signature Scripts
│       └── javascript/
│           ├── signer.js
│           ├── webmssdk.js
│           └── xbogus.js
├── CookiesDir/             # Gespeicherte Sessions (*.cookie)
├── VideosDirPath/          # Quell-Videos
└── logs/                   # Log-Dateien
```

---

## 4. Konfiguration (`Config.py`)

Das System nutzt eine Singleton-Klasse `Config`, die Optionen aus `config.txt` oder Environment-Variables lädt.
*   `COOKIES_DIR`: Pfad zu Session-Dateien.
*   `VIDEOS_DIR`: Pfad zu Quellvideos.
*   `TIKTOK_VIDEO_SIZE`: Zielauflösung (1920x1080).
*   `IMAGEMAGICK_*`: Einstellungen für Text-Overlays (Legacy).

## 5. Sicherheit & Limits
*   **Upload Secret**: API-Zugriff nur mit korrektem `X-Upload-Auth` Header.
*   **File Limits**:
    *   Video: 250MB (konfigurierbar via ENV).
    *   Session: 512KB.
    *   Image: 10MB.
*   **Validation**: Whitelist für MIME-Types (`video/mp4`, `video/quicktime`, etc.).

---

## 6. Deployment Workflow
1.  **System**: Ubuntu/Debian Server.
2.  **User**: Dedizierter `tiktokapi` User.
3.  **Service**: Systemd Unit `tiktok-uploader-api.service`.
4.  **Network**: Empfohlen hinter Cloudflare Tunnel für SSL/TLS und DDoS-Schutz.
