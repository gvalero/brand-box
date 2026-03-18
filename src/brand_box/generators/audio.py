"""
Audio generator with ElevenLabs (primary) and Azure Speech (fallback).

ElevenLabs produces natural, expressive speech. Azure is the fallback
when ElevenLabs is unavailable.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


ELEVENLABS_VOICES = {
    "narrator_female": "cgSgspJ2msm6clMCkdW9",   # Jessica - Playful, Bright, Warm
    "narrator_male": "cjVigY5qzO86Huf0OWal",     # Eric - Smooth, Trustworthy
    "storyteller": "JBFqnCBsd6RMkjVDRZzb",       # George - Warm, Captivating Storyteller
    "energetic": "TX3LPaxmHKxFdv7VOQHJ",         # Liam - Energetic, Social Media Creator
}

AZURE_VOICES = {
    "narrator_female": "en-US-JennyNeural",
    "narrator_male": "en-US-GuyNeural",
    "excited_female": "en-US-AriaNeural",
}


class AudioGenerator:
    """Generate narration audio — ElevenLabs primary, Azure fallback."""

    def __init__(
        self,
        voice_name: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else Path.cwd() / ".audio_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._backend = "none"
        self._el_client = None
        self._el_voice = voice_name or ELEVENLABS_VOICES["narrator_female"]
        self._speech_config = None
        self._azure_voice = voice_name or "en-US-JennyNeural"
        self._init_elevenlabs()
        if self._backend == "none":
            self._init_azure()

    def _init_elevenlabs(self) -> None:
        from brand_box.config import ELEVENLABS_API_KEY
        if not ELEVENLABS_API_KEY:
            return
        try:
            from elevenlabs.client import ElevenLabs
            self._el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            self._backend = "elevenlabs"
            logger.info("Audio generator using ElevenLabs")
        except Exception as e:
            logger.warning("ElevenLabs init failed: %s", e)

    def _init_azure(self) -> None:
        from brand_box.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
        if not AZURE_SPEECH_KEY:
            return
        try:
            import azure.cognitiveservices.speech as speechsdk
            self._speech_config = speechsdk.SpeechConfig(
                subscription=AZURE_SPEECH_KEY,
                region=AZURE_SPEECH_REGION,
            )
            self._speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio24Khz160KBitRateMonoMp3
            )
            self._backend = "azure"
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
        voice = voice_name or (self._el_voice if self._backend == "elevenlabs" else self._azure_voice)

        # Check cache
        cached = self._cache_lookup(voice, text)
        if cached:
            import shutil
            shutil.copy2(str(cached), output_path)
            logger.info("Audio cache hit → %s", output_path)
            return output_path

        if self._backend == "elevenlabs":
            self._generate_elevenlabs(text, output_path, voice)
        elif self._backend == "azure":
            self._generate_azure(text, output_path, voice)
        else:
            raise RuntimeError("No TTS backend configured. Set ELEVENLABS_API_KEY or AZURE_SPEECH_KEY in .env.")

        self._cache_store(voice, text, output_path)
        return output_path

    def _generate_elevenlabs(self, text: str, output_path: str, voice: str) -> None:
        """Generate audio using ElevenLabs API."""
        audio_iter = self._el_client.text_to_speech.convert(
            text=text,
            voice_id=voice,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in audio_iter:
                f.write(chunk)
        logger.info("ElevenLabs audio → %s", output_path)

    def _generate_azure(self, text: str, output_path: str, voice: str) -> None:
        """Generate audio using Azure Speech Service."""
        import azure.cognitiveservices.speech as speechsdk
        self._speech_config.speech_synthesis_voice_name = voice
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self._speech_config,
            audio_config=audio_config,
        )
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.info("Azure audio → %s", output_path)
            return
        raise RuntimeError(f"Azure Speech synthesis failed: {result.reason}")

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
            voice = seg.get("voice_name") or voice_name
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
        # Fallback: estimate from file size (128 kbps = 16000 bytes/sec)
        try:
            size = os.path.getsize(audio_path)
            return size / 16000.0
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
