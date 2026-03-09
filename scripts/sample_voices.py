#!/usr/bin/env python3
"""
Voice sampling script - Round-robin demo of Deepgram Aura 2 EN voices.

Cycles through a list of voices, reading sentences from a longer text block.
Each sentence is spoken by a different voice in sequence.
"""
import os
import sys
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.speech import generate_voice
from audio import play_audio_file

# Long reading block for voice sampling
READING_TEXT = """
Welcome to the Dopamine Hardware Bridge voice sampling demonstration.
This system is designed to interface with thermal receipt printers and barcode scanners.
The hardware controller runs on a Raspberry Pi four, using Debian Raspberry Pi OS Lite sixty-four bit.
It communicates with a Cloudflare Worker through three resilient fallback methods.
First, a direct Flask server exposed via Cloudflare Tunnel.
Second, a persistent WebSocket connection for pub-sub broadcasts.
Third, a REST polling mechanism that recovers from network outages.
All audio is synthesized using text-to-speech technology from either Deepgram or Cloudflare Workers AI.
The system features dual-logging with local SQLite storage and asynchronous streaming to a telemetry endpoint.
Thread safety is ensured through careful use of locks to prevent USB bus collisions during printer access.
This voice sampling script demonstrates the round-robin selection of different voice personalities.
Each sentence you hear is spoken by a different voice model in sequence.
The voices include Luna, Thalia, Athena, Hera, Orpheus, Zeus, Hermes, and Apollo.
These are all part of the Deepgram Aura two English voice collection.
Thank you for listening to this demonstration of the text-to-speech capabilities.
"""

# List of voices to sample
VOICES = ["luna", "thalia", "athena", "hera", "orpheus", "zeus", "hermes", "apollo"]


def main():
    """Run the voice sampling demonstration."""
    # Split text into sentences
    sentences = re.split(r'(?<=[.!?]) +', READING_TEXT.strip())

    # Filter out empty sentences
    sentences = [s for s in sentences if s.strip()]

    print("\n" + "="*70)
    print("DOPAMINE HARDWARE - VOICE SAMPLING DEMONSTRATION")
    print("="*70)
    print(f"\nTotal sentences: {len(sentences)}")
    print(f"Voices in rotation: {', '.join(VOICES)}")
    print("="*70 + "\n")

    voice_index = 0

    for i, sentence in enumerate(sentences, 1):
        # Pick the next voice in round-robin fashion
        voice = VOICES[voice_index % len(VOICES)]
        voice_index += 1

        # Print to console
        print(f"[{voice.upper()}]: \"{sentence}\"")

        # Generate audio file in /tmp
        temp_audio_path = f"/tmp/voice_sample_{i}.mp3"

        try:
            # Generate the voice
            audio_path = generate_voice(
                text=sentence,
                output_path=temp_audio_path,
                speaker=voice,
                speed=1.0
            )

            if audio_path:
                # Play the audio
                play_audio_file(audio_path)

                # Clean up temp file
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                    print(f"✓ Cleaned up: {audio_path}\n")
            else:
                print(f"✗ Failed to generate audio for sentence {i}\n")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Cleaning up...")
            # Clean up any remaining temp files
            for j in range(1, i+1):
                temp_file = f"/tmp/voice_sample_{j}.mp3"
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            sys.exit(0)
        except Exception as e:
            print(f"✗ Error processing sentence {i}: {e}\n")
            continue

    print("="*70)
    print("Voice sampling demonstration complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
