# Workflow: Implement AI Voice Announcements and Multi-Speaker Feedback

## Objective
Update the `dopamine-hardware` Python logic to automatically trigger Cloudflare AI voice generation asynchronously on physical hardware events and network triggers.

## Execution Steps
1. **Update `worker_ai.py`**:
   - Introduce `_MALE_VOICES` and `_FEMALE_VOICES` arrays to cycle through Deepgram models.
   - Add `generate_multi_speaker_task_audio()` which sequences two HTTP calls for dual-channel audio pipelines.
   - Add `generate_announcement_audio()` to generate alert payloads for print events.
2. **Update `hardware.py`**:
   - Establish `audio_lock` across all ALSA outputs (`play_sound` and `play_audio_file`) to stop `mpg123` and `aplay` collisions.
   - Refactor `play_sound` to use the thread-safe handler to free up the blocking scanner thread.
   - Inside `scanner_worker()`: Capture the Cloudflare Worker API's `title` response payload and trigger `generate_multi_speaker_task_audio` asynchronously so it speaks over the printer hardware safely.
   - Inside `print_and_ack()`: Upon a successful print confirmation, parse the job's title and trigger `generate_announcement_audio()` asynchronously.
3. **Validation & Restart**:
   - Run `sudo systemctl restart dopamine.service`.
   - Send a physical print job to the machine and listen for the announcement.
   - Scan an action barcode (e.g. `{BCMD:DONE`) and verify the male/female sequential feedback logic.
