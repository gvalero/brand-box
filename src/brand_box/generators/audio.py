"""
Audio generator using Azure Speech Service.

Generates narration audio from script segments with caching.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


RECOMMENDED_VOICES = {
    "narrator_female": "en-US-JennyNeural",
    "narrator_male": "en-US-GuyNeural",
    "excited_female": "en-US-AriaNeural",
    "child_female": "en-US-AnaNeural",
    "british_female": "en-GB-SoniaNeural",
    "british_male": "en-GB-RyanNeural",
}


class AudioGenerator:
    """Generate narration audio via Azure Speech Service."""

    def __init__(self, voice_name: str = "en-US-JennyNeural", cache_dir: str | Path | None = None) -> None:
        self.voice_name = voice_name
        self.cache_dir = Path(cache_dir) if cache_dir else Path.cwd() / ".audio_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._speech_config = None
        self._init_speech()

    def _init_speech(self) -> None:
        from brand_box.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
        if not AZURE_SPEECH_KEY:
            logger.warning("AZURE_SPEECH_KEY not set — audio generation will fail")
            return

        try:
            import azure.cognitiveservices.speech as speechsdk
            self._speech_config = speechsdk.SpeechConfig(
                subscription=AZURE_SPEECH_KEY,
                region=AZURE_SPEECH_REGION,
            )
            self._speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
            )
            logger.info("Audio generator using Azure Speech (%s)", AZURE_SPEECH_REGION)
        except Exception as e:
            logger.warning("Azure Speech init failed: %s", e)

    def generate_narration(
        self,
        text: str,
        output_path: str,
        voice_name: str | None = None,
    ) -> str:
        """Generate a single narration MP3 from text. Returns output_path."""
        voice = voice_name or self.voice_name

        # Check cache
        cached = self._cache_lookup(voice, text)
        if cached:
            import shutil
            shutil.copy2(str(cached), output_path)
            logger.info("Audio cache hit → %s", output_path)
            return output_path

        if not self._speech_config:
            raise RuntimeError("Azure Speech not configured. Set AZURE_SPEECH_KEY in .env.")

        import azure.cognitiveservices.speech as speechsdk

        self._speech_config.speech_synthesis_voice_name = voice
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self._speech_config,
            audio_config=audio_config,
        )

        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.info("Audio generated → %s", output_path)
            self._cache_store(voice, text, output_path)
            return output_path

        raise RuntimeError(f"Speech synthesis failed: {result.reason}")

    def generate_from_script(
        self,
        script: dict,
        output_dir: str,
        voice_name: str | None = None,
    ) -> dict:
        """Generate audio for all segments + full narration.

        Returns: {"segments": {0: "path", 1: "path", ...}, "full": "full_path"}
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        segments = {}
        for seg in script.get("segments", []):
            idx = seg["index"]
            text = seg.get("text", "")
            if not text.strip():
                continue
            voice = seg.get("voice_name") or voice_name or self.voice_name
            seg_path = str(out / f"seg_{idx}.mp3")
            self.generate_narration(text, seg_path, voice)
            segments[idx] = seg_path

        # Full narration
        full_text = script.get("narration_text", "")
        if not full_text:
            full_text = " ".join(seg.get("text", "") for seg in script.get("segments", []))

        full_path = str(out / "full_narration.mp3")
        if full_text.strip():
            self.generate_narration(full_text, full_path, voice_name)

        return {"segments": segments, "full": full_path}

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """Get duration of an MP3 file in seconds."""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(audio_path)
            return audio.info.length
        except Exception:
            pass
        # Fallback: estimate from file size (32 kbps = 4000 bytes/sec)
        try:
            size = os.path.getsize(audio_path)
            return size / 4000.0
        except Exception:
            return 5.0

    # --- Caching ---

    def _cache_key(self, voice: str, text: str) -> str:
        md5 = hashlib.md5(f"{voice}|{text}".encode()).hexdigest()
        return f"{voice}_{md5}.mp3"

    def _cache_lookup(self, voice: str, text: str) -> Optional[Path]:
        path = self.cache_dir / self._cache_key(voice, text)
        return path if path.is_file() else None

    def _cache_store(self, voice: str, text: str, src_path: str) -> None:
        import shutil
        dest = self.cache_dir / self._cache_key(voice, text)
        if not dest.exists():
            shutil.copy2(src_path, dest)
