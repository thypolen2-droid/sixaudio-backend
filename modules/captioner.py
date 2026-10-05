"""
Local speech-to-caption engine (faster-whisper).

Transcribes already-synthesized MP3 chapters into `<stem>.json` cue files that
live next to the audio, using the exact same schema modules/tts.py writes for
Edge-TTS boundaries. That means modules/server.py picks them up unchanged and
the web player switches from ESTIMATED to EXACT TIMING with no JS edits.

Requires `faster-whisper` (pip install faster-whisper). Models are downloaded
once on first use and cached under Library/.caption_models.
"""

import json
import logging
from pathlib import Path

from .events import EventHandler
from .utils import natural_sort_key

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

WHISPER_AVAILABLE = False
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None

# Where downloaded model weights are cached, relative to project root.
MODEL_CACHE_DIR = Path("Library/.caption_models")

# Whisper sizes worth offering: (key, size_hint). 'base' is the default because
# the audio here is clean single-voice TTS, not noisy real-world speech.
MODEL_CHOICES = ["tiny", "base", "small", "medium"]


class CaptionerConfig:
    def __init__(self, model_size="base", compute_type="int8", device="cpu"):
        self.model_size = model_size
        self.compute_type = compute_type
        self.device = device


class Captioner:
    """Transcribes chapter audio into exact-timestamp JSON cue files."""

    def __init__(self, config: CaptionerConfig = None, event_handler: EventHandler = None):
        self.config = config if config else CaptionerConfig()
        self.events = event_handler
        self._model = None

    def set_event_handler(self, handler: EventHandler):
        self.events = handler

    def _log(self, msg, level="info"):
        if self.events:
            self.events.log(msg, level)
        else:
            logger.info(msg)

    @staticmethod
    def is_available() -> bool:
        return WHISPER_AVAILABLE

    def install_hint(self) -> str:
        return (
            "Local captions need the 'faster-whisper' package, which isn't installed "
            "in this interpreter.\n"
            "Run:  pip install faster-whisper\n"
            "(It also needs ctranslate2; pip pulls that in automatically.)"
        )

    def _load_model(self):
        """Lazily instantiate the Whisper model, downloading weights on first use."""
        if self._model is not None:
            return self._model

        if not WHISPER_AVAILABLE:
            raise RuntimeError(self.install_hint())

        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # download_root keeps weights inside the project so they aren't re-fetched
        # and don't clutter the user's global HF cache.
        self._model = WhisperModel(
            self.config.model_size,
            device=self.config.device,
            compute_type=self.config.compute_type,
            download_root=str(MODEL_CACHE_DIR.resolve()),
        )
        self._log(f"[dim]Whisper model '{self.config.model_size}' loaded ({self.config.device}/{self.config.compute_type}).[/dim]")
        return self._model

    def transcribe_file(self, audio_path: Path) -> Path:
        """Transcribe one audio file and write its .json cue file. Returns cue path or None."""
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            return None

        cue_path = audio_path.with_suffix(".json")

        model = self._load_model()
        segments, _info = model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        cues = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            cues.append({
                "text": text,
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
            })

        if not cues:
            self._log(f"[yellow]No speech detected in {audio_path.name}[/yellow]", "warning")
            return None

        cue_path.write_text(json.dumps(cues, indent=2, ensure_ascii=False), encoding="utf-8")
        return cue_path

    def find_uncaptioned(self, folder_path: Path):
        """Returns sorted MP3s in a story folder that have no cue file yet."""
        folder_path = Path(folder_path)
        audio_dir = folder_path / "Audios"
        if not audio_dir.is_dir():
            return []
        audios = sorted(audio_dir.glob("*.mp3"), key=lambda p: natural_sort_key(p.name))
        return [a for a in audios if not a.with_suffix(".json").is_file()]

    def process_folder(self, folder_path: Path, overwrite=False):
        """Caption every MP3 in a story folder. Returns (success, skipped, failed) counts."""
        folder_path = Path(folder_path)
        if overwrite:
            targets = sorted((folder_path / "Audios").glob("*.mp3"), key=lambda p: natural_sort_key(p.name)) \
                if (folder_path / "Audios").is_dir() else []
        else:
            targets = self.find_uncaptioned(folder_path)

        if not targets:
            self._log(f"[green]All chapters in '{folder_path.name}' already captioned.[/green]")
            return (0, 0, 0)

        # Load the model before starting so the first progress bar entry isn't
        # stalled behind a multi-hundred-MB weight download.
        try:
            self._load_model()
        except RuntimeError as e:
            self._log(str(e), "error")
            return (0, 0, 0)

        skipped = len(sorted((folder_path / "Audios").glob("*.mp3"), key=lambda p: natural_sort_key(p.name))) - len(targets) \
            if (folder_path / "Audios").is_dir() else 0

        if self.events:
            self.events.progress_start("caption", len(targets), "Transcribing...")

        success, failed = 0, []
        for idx, audio_path in enumerate(targets, 1):
            if self.events:
                self.events.progress_update(
                    "caption", advance=0, description=f"[cyan]{audio_path.name}"
                )
            try:
                cue_path = self.transcribe_file(audio_path)
                if cue_path:
                    success += 1
                    if self.events:
                        self.events.progress_update("caption", advance=1)
                else:
                    failed.append(audio_path.name)
            except Exception as e:
                logger.error(f"Failed to caption {audio_path.name}: {e}")
                failed.append(audio_path.name)
                if self.events:
                    self.events.progress_update("caption", advance=1)

        if self.events:
            self.events.progress_finish("caption")

        self._log(f"[green]✔ {success} captioned[/green]" + (f", [red]{len(failed)} failed[/red]" if failed else ""))
        if failed:
            self._log(f"[dim]Failures: {', '.join(failed[:5])}{'…' if len(failed) > 5 else ''}[/dim]")
        return (success, skipped, len(failed))