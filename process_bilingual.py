#!/usr/bin/env python3
"""
Bilingual-episode driver for the standard `process_unified.py` routine.

Why this exists
---------------
`process_unified.py` passes a single `language` code to Whisper for the whole
episode. Whisper treats that code as a HARD override, not a hint (see README
v3.1.2). That is fine for a monolingual show, but a show that alternates
Japanese and English for minutes at a time — e.g. バイリンガルニュース — gets
half of its audio force-fitted into the wrong language and silently translated
or transliterated into nonsense.

This driver keeps the routine completely intact (Gemini summary / chapters /
verification / Notion upload all come from `UnifiedProcessor`) and only swaps
out the transcription step:

  1. Sweep the audio in 30s windows and ask Whisper which language it hears.
  2. Smooth the result into contiguous spans, so cut points land on speaker /
     language switches instead of mid-sentence.
  3. Transcribe each span with its own language, then splice the segments back
     together with absolute timestamps.

Usage
-----
    python process_bilingual.py "https://open.spotify.com/episode/xxx" \
        --audio-file "data/downloads/episode.mp3" \
        [--segments-out data/outputs/segments.json] [--no-notion]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "local_transcriber"))

SAMPLE_RATE = 16000
WINDOW_SEC = 30
# A language run shorter than this is treated as detector noise (a loanword, a
# quoted English phrase inside a Japanese sentence) rather than a real switch.
MIN_RUN_SEC = 90


def build_language_timeline(model, audio, whisper):
    """Return one detected language ('ja' or 'en') per 30-second window."""
    win = WINDOW_SEC * SAMPLE_RATE
    n_mels = model.dims.n_mels
    langs = []
    total = (len(audio) + win - 1) // win

    for idx, start in enumerate(range(0, len(audio), win)):
        chunk = whisper.pad_or_trim(audio[start:start + win])
        mel = whisper.log_mel_spectrogram(chunk, n_mels=n_mels).to(model.device)
        _, probs = model.detect_language(mel)
        if isinstance(probs, list):
            probs = probs[0]
        langs.append("ja" if probs.get("ja", 0.0) >= probs.get("en", 0.0) else "en")
        if (idx + 1) % 20 == 0 or idx + 1 == total:
            print(f"   language sweep: {idx + 1}/{total} windows", flush=True)

    return langs


def spans_from_timeline(langs, audio_len):
    """Collapse the per-window timeline into contiguous (start, end, lang) spans."""
    win = WINDOW_SEC * SAMPLE_RATE
    min_windows = max(1, MIN_RUN_SEC // WINDOW_SEC)

    # Group into runs, then absorb runs too short to be a real speaker turn.
    runs = []
    for lang in langs:
        if runs and runs[-1][0] == lang:
            runs[-1][1] += 1
        else:
            runs.append([lang, 1])

    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, (lang, count) in enumerate(runs):
            if count >= min_windows:
                continue
            # Merge the short run into whichever neighbour is longer.
            prev_len = runs[i - 1][1] if i > 0 else -1
            next_len = runs[i + 1][1] if i + 1 < len(runs) else -1
            target = i - 1 if prev_len >= next_len else i + 1
            runs[target][1] += count
            runs.pop(i)
            changed = True
            break

    spans = []
    cursor = 0
    for lang, count in runs:
        start = cursor
        end = min(audio_len, cursor + count * win)
        spans.append((start, end, lang))
        cursor = end
    if spans:
        spans[-1] = (spans[-1][0], audio_len, spans[-1][2])

    return spans


def transcribe_bilingual(audio_path, model_size="medium", segments_out=None):
    """Transcribe a JA/EN mixed episode, returning Whisper-style segments."""
    import whisper

    print(f"\n🎙️ Bilingual transcription (model: {model_size})")
    model = whisper.load_model(model_size)
    audio = whisper.load_audio(str(audio_path))
    print(f"   Audio: {len(audio) / SAMPLE_RATE / 60:.1f} min")

    print("\n🌐 Detecting language per 30s window...")
    langs = build_language_timeline(model, audio, whisper)
    spans = spans_from_timeline(langs, len(audio))

    print(f"\n📚 {len(spans)} language spans:")
    for start, end, lang in spans:
        print(f"   {start / SAMPLE_RATE / 60:6.1f}–{end / SAMPLE_RATE / 60:6.1f} min  {lang}")

    all_segments = []
    for i, (start, end, lang) in enumerate(spans, 1):
        offset = start / SAMPLE_RATE
        print(f"\n   [{i}/{len(spans)}] transcribing {offset / 60:.1f} min "
              f"({(end - start) / SAMPLE_RATE / 60:.1f} min, {lang})", flush=True)
        result = model.transcribe(
            audio[start:end],
            language=lang,
            verbose=False,
            task="transcribe",
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.6,
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        )
        for seg in result["segments"]:
            text = seg["text"].strip()
            if not text:
                continue
            all_segments.append({
                "start": seg["start"] + offset,
                "end": seg["end"] + offset,
                "text": text,
                "language": lang,
            })

    all_segments.sort(key=lambda s: s["start"])
    print(f"\n✅ {len(all_segments)} segments across {len(spans)} spans")

    if segments_out:
        Path(segments_out).parent.mkdir(parents=True, exist_ok=True)
        Path(segments_out).write_text(
            json.dumps({"spans": [(s, e, l) for s, e, l in spans], "segments": all_segments},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"   Segments saved: {segments_out}")

    return all_segments


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spotify_url")
    parser.add_argument("--audio-file", required=True)
    parser.add_argument("--whisper-model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--segments-out", default=None,
                        help="Write raw timestamped segments to this JSON path")
    parser.add_argument("--no-notion", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--llm-backend", default=None, choices=["gemini", "lmstudio"])
    args = parser.parse_args()

    from process_unified import UnifiedProcessor

    segments_holder = {}

    def _transcribe_bilingual(self, audio_path, language, model_size):
        segments = transcribe_bilingual(audio_path, model_size, args.segments_out)
        segments_holder["segments"] = segments
        self.source = "whisper"

        timestamps_raw = []
        for seg in segments:
            start_sec = int(seg["start"])
            timestamps_raw.append((f"{start_sec // 60}:{start_sec % 60:02d}", seg["text"]))

        return {
            "transcript": " ".join(s["text"] for s in segments),
            "timestamps_raw": timestamps_raw,
            "language": "mixed",
        }

    # Swap only the transcription step; everything downstream is the normal routine.
    UnifiedProcessor._transcribe_with_whisper = _transcribe_bilingual

    kwargs = {}
    if args.llm_backend:
        kwargs["llm_backend"] = args.llm_backend
    processor = UnifiedProcessor(**kwargs)

    result = processor.process(
        args.spotify_url,
        audio_file=args.audio_file,
        no_notion=args.no_notion,
        whisper_model=args.whisper_model,
        no_verify=args.no_verify,
    )

    if not result.get("success"):
        print(f"\n❌ Failed: {result.get('error')}")
        return 1

    print(f"\n📂 Output: {result['output_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
