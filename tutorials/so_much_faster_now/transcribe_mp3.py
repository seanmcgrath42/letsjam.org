#!/usr/bin/env python3
"""
transcribe.py
=============
Step 1 of the karaoke build process.

Transcribes the song MP3 using OpenAI Whisper (word-level timestamps)
and merges with chord timings from the XSC file to produce a flat
ChordPro file (.cho) ready for editing.

Prerequisites
-------------
    pip install openai-whisper
    # Windows: also install ffmpeg and add to PATH
    #   https://ffmpeg.org/download.html

Usage
-----
    python transcribe.py

Output
------
    assets/song.cho   ← edit this, then run generate_karaoke.py
"""

import re
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
MP3_FILE      = "assets/song.mp3"
XSC_FILE      = "assets/song.xsc"
OUTPUT_FILE   = "assets/song.cho"

# Whisper model size. Larger = more accurate but slower.
# Recommended: "base" for a quick first pass, "small" or "medium" for accuracy.
#   tiny | base | small | medium | large
WHISPER_MODEL = "base"

SONG_TITLE  = "So Much Faster Now"
SONG_ARTIST = ""          # fill in if known
# ──────────────────────────────────────────────────────────────────────────


CHORD_LIBRARY = {
    "C":   "C",    "D":   "D",    "E":   "E",    "F":   "F",
    "G":   "G",    "A":   "A",    "B":   "B",
    "Cm":  "Cm",   "Dm":  "Dm",   "Em":  "Em",   "Fm":  "Fm",
    "Gm":  "Gm",   "Am":  "Am",   "Bm":  "Bm",
    "C#":  "C#",   "Db":  "Db",   "D#":  "D#",   "Eb":  "Eb",
    "F#":  "F#",   "Gb":  "Gb",   "G#":  "G#",   "Ab":  "Ab",
    "A#":  "A#",   "Bb":  "Bb",
    "C#m": "C#m",  "Ebm": "Ebm",  "F#m": "F#m",
    "Abm": "Abm",  "Bbm": "Bbm",
}

# Maps "E Major" -> "E",  "A Minor" -> "Am",  etc.
_LONG_RE = re.compile(r'^(.+?)\s+(Major|Minor)$', re.IGNORECASE)

def simplify_chord(full_name: str) -> str:
    m = _LONG_RE.match(full_name.strip())
    if not m:
        return full_name.strip()
    root, quality = m.group(1), m.group(2)
    return root if quality.lower() == "major" else root + "m"


# ── XSC parser (same logic as generate.py) ───────────────────────────────

def parse_xsc(xsc_path: Path) -> list:
    if not xsc_path.exists():
        raise FileNotFoundError(f"XSC file not found: {xsc_path}")

    entries = []
    in_markers = False

    with open(xsc_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line == "SectionStart,Markers":
                in_markers = True
                continue
            if line == "SectionEnd,Markers":
                break
            if not in_markers or not line.startswith("S,"):
                continue

            parts = line.split(",")
            if len(parts) < 6:
                continue

            label     = parts[3].strip()
            timestamp = parts[5].strip()

            m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", timestamp)
            if not m:
                continue
            h, mn, s, frac = m.group(1), m.group(2), m.group(3), m.group(4)
            seconds = int(h)*3600 + int(mn)*60 + int(s) + int(frac)/(10**len(frac))
            seconds = round(seconds, 3)

            if label in CHORD_LIBRARY:
                entries.append({"time": seconds, "chord": CHORD_LIBRARY[label]})
            else:
                print(f"  [warn] Unknown chord label '{label}' at {timestamp}")
                entries.append({"time": seconds, "chord": label})

    return entries


# ── Transcription ─────────────────────────────────────────────────────────

def transcribe(mp3_path: Path, model_name: str) -> dict:
    try:
        import whisper
    except ImportError:
        raise SystemExit(
            "\n[error] openai-whisper is not installed.\n"
            "  Run:  pip install openai-whisper\n"
            "  Also ensure ffmpeg is installed and on your PATH.\n"
        )
    print(f"  Loading Whisper model '{model_name}' ...")
    model = whisper.load_model(model_name)
    print(f"  Transcribing {mp3_path.name} ...")
    result = model.transcribe(str(mp3_path), word_timestamps=True)
    return result


# ── Merge into ChordPro ───────────────────────────────────────────────────

def merge_to_chordpro(whisper_result: dict, chords: list) -> str:
    """
    Inserts [Chord] markers into the transcribed lyrics at the word
    whose start time is closest to each chord change.

    Each Whisper segment becomes one line in the output.
    """
    # Build a flat list of words with timestamps across all segments,
    # keeping track of which segment each word belongs to (for line breaks).
    seg_words = []   # list of (seg_idx, word_dict)
    for seg_idx, seg in enumerate(whisper_result.get("segments", [])):
        for w in seg.get("words", []):
            seg_words.append((seg_idx, w))

    if not seg_words:
        raise ValueError("Whisper returned no word-level data. "
                         "Make sure word_timestamps=True is supported by your model.")

    # For each chord, find the word index whose start time is nearest.
    def nearest_word_idx(target_time):
        best_idx, best_delta = 0, float("inf")
        for i, (_, w) in enumerate(seg_words):
            delta = abs(w.get("start", 0) - target_time)
            if delta < best_delta:
                best_idx, best_delta = i, delta
        return best_idx

    # Map word_index -> list of chord labels to insert before that word
    chord_inserts: dict[int, list[str]] = {}
    for ch in chords:
        idx = nearest_word_idx(ch["time"])
        chord_inserts.setdefault(idx, []).append(ch["chord"])

    # Build output line by line
    lines = []
    current_line = ""
    current_seg  = seg_words[0][0]

    for i, (seg_idx, w) in enumerate(seg_words):
        if seg_idx != current_seg:
            lines.append(current_line.strip())
            current_line = ""
            current_seg  = seg_idx

        for chord in chord_inserts.get(i, []):
            current_line += f"[{chord}]"

        word_text = w.get("word", "")
        # Whisper often includes a leading space; preserve it between words
        current_line += word_text

    if current_line.strip():
        lines.append(current_line.strip())

    return "\n".join(lines)


# ── ChordPro file writer ──────────────────────────────────────────────────

def write_chordpro(cho_path: Path, title: str, artist: str, body: str):
    header_lines = [f"{{title: {title}}}"]
    if artist:
        header_lines.append(f"{{artist: {artist}}}")
    header_lines.append("")   # blank line before lyrics

    content = "\n".join(header_lines) + "\n" + body + "\n"
    cho_path.write_text(content, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent

    print("Parsing XSC chord markers ...")
    chords = parse_xsc(base / XSC_FILE)
    print(f"  Found {len(chords)} chord marker(s).")

    print("Transcribing audio ...")
    result = transcribe(base / MP3_FILE, WHISPER_MODEL)
    n_segs = len(result.get("segments", []))
    print(f"  Got {n_segs} segment(s) from Whisper.")

    print("Merging chords into lyrics ...")
    body = merge_to_chordpro(result, chords)

    out_path = base / OUTPUT_FILE
    write_chordpro(out_path, SONG_TITLE, SONG_ARTIST, body)
    print(f"\nWritten: {out_path}")
    print("\nNext steps:")
    print("  1. Open assets/song.cho and review / correct the lyrics and chord placements.")
    print("  2. Run generate_karaoke.py to build karaoke.html.")


if __name__ == "__main__":
    main()
