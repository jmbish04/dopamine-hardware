"""
Cloudflare Workers AI Module for dopamine-hardware bridge.
Provides text generation, structured responses, and text-to-speech synthesis.
"""

# Import all public functions for convenient access
from .text import generate_text, generate_structured_response
from .speech import (
    generate_voice,
    generate_multi_speaker_task_audio,
    generate_announcement_audio,
    generate_task_completion_audio
)
from .diagnostics import diagnose_hardware
from .config import get_config, SOUND_MAP

__all__ = [
    'generate_text',
    'generate_structured_response',
    'generate_voice',
    'generate_multi_speaker_task_audio',
    'generate_announcement_audio',
    'generate_task_completion_audio',
    'diagnose_hardware',
    'get_config',
    'SOUND_MAP'
]
