"""Local media providers that implement the Genblaze provider contract."""

from __future__ import annotations

import hashlib
import math
import platform
import shutil
import subprocess
import textwrap
from pathlib import Path
from urllib.parse import quote

from genblaze_core import Modality
from genblaze_core.models.asset import Asset, AudioMetadata
from genblaze_core.models.step import Step
from genblaze_core.providers import ProviderCapabilities, RetryPolicy, SyncProvider
from genblaze_core.runnable.config import RunnableConfig
from PIL import Image, ImageDraw, ImageFont


def _file_uri(path: Path) -> str:
    return f"file://{quote(str(path.resolve()))}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalSpeechProvider(SyncProvider):
    """Generate WAV narration with a free local OS speech model.

    macOS uses the built-in Apple Speech synthesizer. Linux deployments use
    eSpeak NG. No provider account, API key, network request, or paid inference
    is involved.
    """

    name = "proofcast-local-speech"

    def __init__(
        self,
        output_dir: Path,
        *,
        engine: str = "auto",
        voice: str = "Samantha",
        rate: int = 175,
        max_chars: int = 1200,
    ) -> None:
        super().__init__(retry_policy=RetryPolicy.disabled())
        self.output_dir = output_dir
        self.engine = self._resolve_engine(engine)
        self.voice = voice
        self.rate = max(100, min(int(rate), 260))
        self.max_chars = max_chars

    @staticmethod
    def _resolve_engine(engine: str) -> str:
        normalized = engine.strip().lower()
        if normalized not in {"auto", "say", "espeak-ng"}:
            raise ValueError("engine must be auto, say, or espeak-ng")
        if normalized != "auto":
            return normalized
        if platform.system() == "Darwin" and shutil.which("say"):
            return "say"
        if shutil.which("espeak-ng"):
            return "espeak-ng"
        raise RuntimeError(
            "No local speech engine found. Install espeak-ng, or run on macOS with /usr/bin/say."
        )

    @property
    def model_name(self) -> str:
        if self.engine == "say":
            return f"apple-speech-{self.voice.lower().replace(' ', '-')}"
        return "espeak-ng-en-us"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supported_modalities=[Modality.AUDIO],
            supported_inputs=["text"],
            models=[self.model_name],
            output_formats=["audio/wav"],
        )

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        script = " ".join((step.prompt or "").split())
        if not script:
            raise ValueError("Narration script cannot be empty")
        if len(script) > self.max_chars:
            raise ValueError(f"Narration script exceeds the {self.max_chars}-character limit")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{step.step_id}-narration.wav"

        if self.engine == "say":
            self._generate_with_say(script, output_path)
        else:
            self._generate_with_espeak(script, output_path)

        step.assets.append(
            Asset(
                url=_file_uri(output_path),
                media_type="audio/wav",
                sha256=_sha256(output_path),
                size_bytes=output_path.stat().st_size,
                audio=AudioMetadata(sample_rate=22050, channels=1, codec="pcm_s16le"),
                metadata={
                    "local_engine": self.engine,
                    "voice": self.voice if self.engine == "say" else "en-us",
                    "network_calls": 0,
                },
            )
        )
        step.cost_usd = 0.0
        return step

    def _generate_with_say(self, script: str, output_path: Path) -> None:
        say = shutil.which("say") or "/usr/bin/say"
        afconvert = shutil.which("afconvert") or "/usr/bin/afconvert"
        if not Path(say).exists() or not Path(afconvert).exists():
            raise RuntimeError("macOS say and afconvert are required for the say engine")
        aiff_path = output_path.with_suffix(".aiff")
        try:
            subprocess.run(
                [say, "-v", self.voice, "-r", str(self.rate), "-o", str(aiff_path), script],
                check=True,
                timeout=60,
                capture_output=True,
            )
            subprocess.run(
                [afconvert, "-f", "WAVE", "-d", "LEI16", str(aiff_path), str(output_path)],
                check=True,
                timeout=60,
                capture_output=True,
            )
        finally:
            aiff_path.unlink(missing_ok=True)

    def _generate_with_espeak(self, script: str, output_path: Path) -> None:
        executable = shutil.which("espeak-ng")
        if not executable:
            raise RuntimeError("espeak-ng is not installed")
        subprocess.run(
            [
                executable,
                "-v",
                "en-us",
                "-s",
                str(self.rate),
                "-w",
                str(output_path),
                script,
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )


class AccessibleCoverProvider(SyncProvider):
    """Generate a high-contrast editorial cover from the same prompt."""

    name = "proofcast-accessible-cover"
    model_name = "proofcast-accessible-cover-v1"

    def __init__(self, output_dir: Path) -> None:
        super().__init__(retry_policy=RetryPolicy.disabled())
        self.output_dir = output_dir

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supported_modalities=[Modality.IMAGE],
            supported_inputs=["text"],
            models=[self.model_name],
            output_formats=["image/png"],
        )

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        title = str(step.params.get("title") or "ProofCast Brief")[:90]
        prompt = step.prompt or title
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{step.step_id}-cover.png"
        image = self._render(title, prompt)
        image.save(output_path, format="PNG", optimize=True)
        step.assets.append(
            Asset(
                url=_file_uri(output_path),
                media_type="image/png",
                sha256=_sha256(output_path),
                size_bytes=output_path.stat().st_size,
                width=image.width,
                height=image.height,
                metadata={"generator": self.model_name, "network_calls": 0},
            )
        )
        step.cost_usd = 0.0
        return step

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    def _render(self, title: str, prompt: str) -> Image.Image:
        width, height = 1280, 720
        seed = hashlib.sha256(prompt.encode("utf-8")).digest()
        hue = seed[0] / 255.0
        accent = self._hsl_to_rgb(hue, 0.72, 0.57)
        accent_dark = self._hsl_to_rgb((hue + 0.08) % 1, 0.68, 0.30)

        image = Image.new("RGB", (width, height), "#08111f")
        draw = ImageDraw.Draw(image)
        for y in range(height):
            t = y / max(height - 1, 1)
            color = tuple(
                round((1 - t) * 8 + t * channel * 0.45) for channel in accent_dark
            )
            draw.line((0, y, width, y), fill=color)

        for index in range(28):
            magnitude = 46 + seed[index % len(seed)] * 0.7
            x = 60 + index * 42
            center = 485
            top = center - magnitude / 2
            bottom = center + magnitude / 2
            draw.rounded_rectangle((x, top, x + 18, bottom), radius=9, fill=accent)

        draw.rounded_rectangle((64, 54, 292, 104), radius=25, fill="#f7f9fc")
        draw.text((88, 66), "PROOFCAST", fill="#08111f", font=self._font(22, bold=True))

        wrapped = textwrap.wrap(title, width=28)[:3]
        y = 145
        title_font = self._font(66, bold=True)
        for line in wrapped:
            draw.text((64, y), line, fill="#ffffff", font=title_font)
            y += 79

        draw.text(
            (64, 626),
            "LOCAL NARRATION  /  HASH-VERIFIED PROVENANCE",
            fill="#dce7f7",
            font=self._font(22, bold=True),
        )
        draw.ellipse((1110, 74, 1206, 170), fill=accent)
        draw.polygon(((1140, 102), (1140, 142), (1176, 122)), fill="#08111f")
        return image

    @staticmethod
    def _hsl_to_rgb(h: float, s: float, lightness: float) -> tuple[int, int, int]:
        c = (1 - abs(2 * lightness - 1)) * s
        x = c * (1 - abs((h * 6) % 2 - 1))
        m = lightness - c / 2
        sector = int(math.floor(h * 6)) % 6
        pairs = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))
        r, g, b = pairs[sector]
        return tuple(round((channel + m) * 255) for channel in (r, g, b))

