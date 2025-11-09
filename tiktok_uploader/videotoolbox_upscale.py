import platform
import shutil
import subprocess
from pathlib import Path

from .Config import Config


SUPER_SCALE_FACTOR = 2.0


def _base_output_dir() -> Path:
    config = Config.get()
    base = Path(config.post_processing_video_path or "./VideosDirPath")
    if not base.is_absolute():
        base = Path.cwd() / base
    target_dir = base / "upscaled"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _ffmpeg_binary() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the VideoToolbox upscaling step.")
    return ffmpeg


def _build_output_path(source: Path) -> Path:
    suffix = source.suffix or ".mp4"
    factor = int(SUPER_SCALE_FACTOR) if SUPER_SCALE_FACTOR.is_integer() else SUPER_SCALE_FACTOR
    return _base_output_dir() / f"{source.stem}_vt{factor}x{suffix}"


def upscale_video_with_videotoolbox(source_path: str) -> str:
    """
    Upscale the given video to 4K (3840x2160) using Apple VideoToolbox via ffmpeg.
    """
    if platform.system() != "Darwin":
        raise RuntimeError("VideoToolbox Super Resolution is only supported on macOS.")

    source = Path(source_path).resolve()
    if not source.exists():
        raise RuntimeError(f"Source video for upscaling not found: {source_path}")

    output_path = _build_output_path(source)
    if output_path.exists() and output_path.stat().st_mtime >= source.stat().st_mtime:
        return str(output_path)

    ffmpeg = _ffmpeg_binary()
    scale_expr_w = f"trunc(iw*{SUPER_SCALE_FACTOR}/2)*2"
    scale_expr_h = f"trunc(ih*{SUPER_SCALE_FACTOR}/2)*2"
    scale_filter = f"scale='{scale_expr_w}':'{scale_expr_h}':flags=lanczos"
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0",
        "-c:v",
        "h264_videotoolbox",
        "-vf",
        scale_filter,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-movflags",
        "use_metadata_tags+faststart",
        str(output_path),
    ]

    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"VideoToolbox upscaling failed: {completed.stderr.strip() or 'Unknown ffmpeg error'}"
        )

    return str(output_path)
