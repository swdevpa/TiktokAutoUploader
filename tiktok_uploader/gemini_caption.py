import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import google.generativeai as genai
except ModuleNotFoundError as exc:  # pragma: no cover - library is optional at import time
    genai = None
    _import_error = exc
else:
    _import_error = None

try:
    from pypdf import PdfReader
except ModuleNotFoundError as exc:  # pragma: no cover - library is optional at import time
    PdfReader = None
    _pdf_import_error = exc
else:
    _pdf_import_error = None


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-pro")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "300"))
DEFAULT_MAX_PDF_CHARS = int(os.getenv("GEMINI_MAX_PDF_CHARS", "8000"))


class GeminiCaptionError(RuntimeError):
    """Raised when generating captions via Gemini fails."""


@dataclass
class CaptionSuggestion:
    """Structured response returned by the Gemini caption service."""

    title: str
    description: str
    hashtags: List[str]
    raw_text: str

    @property
    def formatted(self) -> str:
        """Return a TikTok-ready caption combining title, description, and hashtags."""
        parts: List[str] = []
        if self.title:
            parts.append(self.title.strip())
        if self.description:
            parts.append(self.description.strip())
        if self.hashtags:
            hashtag_line = (
                " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags if tag.strip())
            ).strip()
            if hashtag_line:
                parts.append(hashtag_line)
        return "\n\n".join(part for part in parts if part)


class GeminiCaptionService:
    """Service object that wraps Google Gemini for generating TikTok captions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        pdf_paths: Optional[List[str]] = None,
        model_name: str = DEFAULT_MODEL,
        max_pdf_chars: int = DEFAULT_MAX_PDF_CHARS,
        request_timeout: int = DEFAULT_TIMEOUT_SECONDS,
        app_focus: bool = True,
    ) -> None:
        if genai is None:
            raise GeminiCaptionError(
                f"google-generativeai is required but not installed: {_import_error}"
            )
        if PdfReader is None:
            raise GeminiCaptionError(
                f"pypdf is required but not installed: {_pdf_import_error}"
            )

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise GeminiCaptionError("GEMINI_API_KEY environment variable is not set.")

        self.model_name = model_name
        self.pdf_paths = pdf_paths or []
        self.max_pdf_chars = max_pdf_chars
        self.request_timeout = request_timeout
        self.app_focus = app_focus

        genai.configure(api_key=self.api_key)
        try:
            self.model = genai.GenerativeModel(self.model_name)
        except Exception as exc:
            raise GeminiCaptionError(
                f"Failed to initialize Gemini model '{self.model_name}': {exc}"
            ) from exc

        self._pdf_context = self._load_pdf_context()

    def _load_pdf_context(self) -> List[str]:
        """Extract text snippets from the provided PDF files."""
        contexts: List[str] = []
        for path in self.pdf_paths:
            if not path:
                continue
            if not os.path.isfile(path):
                continue
            try:
                reader = PdfReader(path)
            except Exception as exc:  # pragma: no cover - depends on PDF content
                raise GeminiCaptionError(f"Failed to read PDF '{path}': {exc}") from exc

            collected: List[str] = []
            total = 0
            for page in reader.pages:
                try:
                    text = page.extract_text() or ""
                except Exception as exc:  # pragma: no cover
                    raise GeminiCaptionError(
                        f"Failed to extract text from '{path}': {exc}"
                    ) from exc
                cleaned = self._clean_text(text)
                if cleaned:
                    collected.append(cleaned)
                    total += len(cleaned)
                if total >= self.max_pdf_chars:
                    break

            if collected:
                contexts.append("\n".join(collected)[: self.max_pdf_chars])
        return contexts

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse excessive whitespace in extracted PDF text."""
        return re.sub(r"[ \t]+\n", "\n", text.strip())

    def generate_caption(
        self,
        video_path: str,
        *,
        additional_context: Optional[str] = None,
    ) -> CaptionSuggestion:
        """Generate a caption suggestion for the provided video file."""
        if not video_path:
            raise GeminiCaptionError("A video path must be provided.")
        if not os.path.isfile(video_path):
            raise GeminiCaptionError(f"Video file not found: {video_path}")

        mime_type, _ = mimetypes.guess_type(video_path)
        if not mime_type:
            mime_type = "video/mp4"

        video_file = self._upload_file(video_path, mime_type)
        try:
            prompt = self._build_prompt(video_path, additional_context)
            response = self.model.generate_content(
                [video_file, prompt],
                request_options={"timeout": self.request_timeout},
            )
        except Exception as exc:
            raise GeminiCaptionError(f"Gemini request failed: {exc}") from exc
        finally:
            # Free up storage on Gemini by deleting uploaded file.
            try:
                genai.delete_file(video_file.name)
            except Exception:
                # Non-fatal cleanup failure.
                pass

        if not hasattr(response, "text") or not response.text:
            raise GeminiCaptionError("Gemini returned an empty response.")

        return self._parse_caption_response(response.text)

    def _build_prompt(
        self, video_path: str, additional_context: Optional[str]
    ) -> str:
        """Construct the instruction prompt sent alongside the video."""
        framework_text = "\n\n---\n\n".join(self._pdf_context)
        video_name = os.path.basename(video_path)
        role_line = (
            "You are an expert marketer for mobile apps on TikTok."
            if self.app_focus
            else "You are an expert TikTok marketer for creators, brands, and services beyond mobile apps."
        )
        objective_line = (
            "Return an English TikTok hook/title and description that drive installs for the app."
            if self.app_focus
            else "Return an English TikTok hook/title and description that match the video's topic even when no app is promoted."
        )
        benefit_line = (
            "Highlight why the app is valuable and how it solves the viewer's problem."
            if self.app_focus
            else "Highlight the key benefit, curiosity gap, or transformation for the viewer without inventing any app references."
        )
        hashtag_line = (
            "Add up to five relevant, mixed-difficulty hashtags focused on the app niche."
            if self.app_focus
            else "Add up to five relevant, mixed-difficulty hashtags aligned with the video's niche or subject."
        )

        context_sections = [f"Video filename: {video_name}"]
        if additional_context:
            context_sections.append(additional_context.strip())
        if framework_text:
            context_sections.append(f"Strategy frameworks:\n{framework_text}")

        context_block = "\n\n".join(context_sections)

        return (
            f"{role_line} "
            "Analyze the attached video together with the provided strategy frameworks. "
            f"{objective_line} "
            "Use a concise, high-energy tone suitable for organic TikTok content, "
            "the first line must catch attention and highlight the benefit to the viewer. "
            f"{benefit_line} "
            "Optimise the caption for conversions while remaining natural and organic. "
            f"{hashtag_line} "
            "Do not repeat hashtags already present in the caption body.\n\n"
            f"{context_block}\n\n"
            "Respond ONLY with valid JSON in the following schema:\n"
            "{\n"
            '  "title": "short hook line",\n'
            '  "description": "2-4 sentences describing the video and CTA",\n'
            '  "hashtags": ["tag1", "tag2", "..."]\n'
            "}\n"
            "Keep the combined description and hashtags under 2,000 characters."
        )

    def _upload_file(self, video_path: str, mime_type: str):
        """Upload the local video file to Gemini and wait for processing."""
        try:
            file_obj = genai.upload_file(path=video_path, mime_type=mime_type)
        except Exception as exc:
            raise GeminiCaptionError(f"Failed to upload video to Gemini: {exc}") from exc

        if getattr(file_obj, "state", None) and file_obj.state.name == "PROCESSING":
            file_obj = self._wait_for_file_active(file_obj.name)
        return file_obj

    def _wait_for_file_active(self, file_name: str):
        """Poll Gemini until the uploaded file is ready for inference."""
        start_time = time.time()
        while True:
            file_obj = genai.get_file(file_name)
            state_name = getattr(file_obj.state, "name", "ACTIVE")
            if state_name == "ACTIVE":
                return file_obj
            if state_name == "FAILED":
                raise GeminiCaptionError("Gemini reported a failure while processing the video.")
            if time.time() - start_time > self.request_timeout:
                raise GeminiCaptionError("Timed out waiting for Gemini to process the video.")
            time.sleep(2)

    @staticmethod
    def _parse_caption_response(response_text: str) -> CaptionSuggestion:
        """Decode the JSON payload returned by Gemini."""
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = GeminiCaptionService._strip_fenced_block(cleaned)

        try:
            payload: Dict[str, object] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # Fallback: treat the raw response as description.
            raise GeminiCaptionError(
                f"Failed to parse Gemini response as JSON: {exc}\nResponse: {response_text}"
            ) from exc

        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        hashtags_raw = payload.get("hashtags", [])
        hashtags: List[str] = []
        if isinstance(hashtags_raw, list):
            hashtags = [str(tag).strip().lstrip("#") for tag in hashtags_raw if str(tag).strip()]
        elif isinstance(hashtags_raw, str):
            hashtags = [tag.strip().lstrip("#") for tag in hashtags_raw.split() if tag.strip()]

        return CaptionSuggestion(
            title=title,
            description=description,
            hashtags=hashtags,
            raw_text=response_text,
        )

    @staticmethod
    def _strip_fenced_block(text: str) -> str:
        """Extract JSON from a fenced code block."""
        # Supports ```json ... ``` or ``` ... ```
        pattern = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
        match = pattern.match(text)
        if match:
            return match.group(1).strip()
        return text.strip()
