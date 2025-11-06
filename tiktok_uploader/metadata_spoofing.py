import random
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Tuple

from .Config import Config


class MetadataProcessingError(RuntimeError):
    """Raised when spoofing or C2PA stripping fails."""


_DEVICE_PROFILES: Tuple[Dict[str, str], ...] = (
    {"make": "Apple", "model": "iPhone 15 Pro Max", "software": "iOS 17.4"},
    {"make": "Apple", "model": "iPhone 15 Pro", "software": "iOS 17.4"},
    {"make": "Apple", "model": "iPhone 15 Plus", "software": "iOS 17.3"},
    {"make": "Apple", "model": "iPhone 15", "software": "iOS 17.3"},
    {"make": "Apple", "model": "iPhone 14 Pro Max", "software": "iOS 17.2"},
    {"make": "Apple", "model": "MacBook Pro 16-inch (M3 Max)", "software": "macOS 14.3"},
    {"make": "Apple", "model": "MacBook Pro 14-inch (M3 Pro)", "software": "macOS 14.3"},
    {"make": "Apple", "model": "MacBook Air 15-inch (M3)", "software": "macOS 14.2"},
    {"make": "Apple", "model": "iMac 24-inch (M3)", "software": "macOS 14.2"},
    {"make": "Apple", "model": "Mac Studio (M2 Ultra)", "software": "macOS 14.1"},
)

_LOCATION_CANDIDATES: Tuple[Dict[str, str], ...] = (
    {"name": "New York, NY", "iso6709": "+40.7128-074.0060+000.00/"},
    {"name": "Los Angeles, CA", "iso6709": "+34.0522-118.2437+000.00/"},
    {"name": "London, UK", "iso6709": "+51.5072-000.1276+000.00/"},
    {"name": "Paris, France", "iso6709": "+48.8566+002.3522+000.00/"},
    {"name": "Berlin, Germany", "iso6709": "+52.5200+013.4050+000.00/"},
    {"name": "Tokyo, Japan", "iso6709": "+35.6764+139.6500+000.00/"},
    {"name": "Seoul, South Korea", "iso6709": "+37.5665+126.9780+000.00/"},
    {"name": "Sydney, Australia", "iso6709": "-33.8688+151.2093+000.00/"},
    {"name": "Toronto, Canada", "iso6709": "+43.6532-079.3832+000.00/"},
    {"name": "São Paulo, Brazil", "iso6709": "-23.5505-046.6333+000.00/"},
)

_FOCAL_LENGTHS_MM = (13.0, 15.0, 18.0, 24.0, 26.0, 28.0, 35.0, 48.0)
_ISO_RANGE = (50, 200, 320, 400, 640, 800, 1250, 2000)
_SHUTTER_DENOMINATORS = (30, 50, 60, 80, 100, 120, 240, 500)


def _resolve_source_path(video_path: str) -> Path:
    """Resolve the absolute path for the incoming video."""
    candidate = Path(video_path)
    if candidate.is_absolute():
        return candidate

    cwd = Path.cwd()
    config = Config.get()
    videos_dir = Path(config.videos_dir)
    if not videos_dir.is_absolute():
        videos_dir = cwd / videos_dir

    potential = videos_dir / candidate
    if potential.exists():
        return potential

    # Fall back to treating the path as relative to cwd.
    return (cwd / candidate).resolve()


def _output_directory() -> Path:
    config = Config.get()
    base_dir = Path(config.post_processing_video_path)
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    target_dir = base_dir / "sanitized"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _random_creation_time() -> str:
    """Return a random UTC timestamp within the past 180 days."""
    now = datetime.now(timezone.utc)
    earliest = now - timedelta(days=180)
    random_seconds = random.uniform(0, (now - earliest).total_seconds())
    creation_time = earliest + timedelta(seconds=random_seconds)
    return creation_time.strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_metadata() -> Dict[str, str]:
    device_profile = random.choice(_DEVICE_PROFILES)
    creation_time = _random_creation_time()
    iso_value = str(random.choice(_ISO_RANGE))
    shutter_value = f"1/{random.choice(_SHUTTER_DENOMINATORS)}"
    focal_length = f"{random.choice(_FOCAL_LENGTHS_MM):.1f}mm"

    metadata = {
        "creation_time": creation_time,
        "com.apple.quicktime.make": device_profile["make"],
        "com.apple.quicktime.model": device_profile["model"],
        "com.apple.quicktime.software": device_profile["software"],
        "com.apple.quicktime.camera.iso_speed": iso_value,
        "com.apple.quicktime.camera.shutter_speed": shutter_value,
        "com.apple.quicktime.camera.focal_length": focal_length,
    }

    if random.random() >= 0.2:
        location_profile = random.choice(_LOCATION_CANDIDATES)
        metadata["com.apple.quicktime.location.ISO6709"] = location_profile["iso6709"]
        metadata["com.apple.quicktime.location.name"] = location_profile["name"]

    return metadata


def prepare_video_for_upload(video_path: str) -> str:
    """
    Strip C2PA artefacts and spoof metadata for the given video.

    Returns the absolute path to the sanitized video that should be used for upload.
    """
    source = _resolve_source_path(video_path)
    if not source.exists():
        raise MetadataProcessingError(f"Video source not found: {video_path}")

    output_dir = _output_directory()
    output_path = output_dir / f"{source.stem}_spoofed{source.suffix or '.mp4'}"

    # Ensure we don't overwrite an existing spoofed artefact.
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{source.stem}_spoofed_{counter}{source.suffix or '.mp4'}"
        counter += 1

    metadata_overrides = _generate_metadata()

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0",
        "-c",
        "copy",
        "-map_metadata",
        "-1",
        "-movflags",
        "use_metadata_tags+faststart",
    ]

    for key, value in metadata_overrides.items():
        ffmpeg_cmd.extend(["-metadata", f"{key}={value}"])

    ffmpeg_cmd.append(str(output_path))

    completed = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise MetadataProcessingError(
            f"Failed to spoof metadata: {completed.stderr.strip() or 'Unknown ffmpeg error'}"
        )

    return str(output_path.resolve())
