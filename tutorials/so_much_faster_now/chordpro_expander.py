#!/usr/bin/env python3
"""
pro_to_cho.py
=============
Converts a ChordPro source file (.pro) + XSC chord timings into a flat
song.cho file for generate_karaoke.py.

Because the chord progression is identical throughout this song, the
XSC markers divide into repeating cycles.  This script:

  1. Parses the chorus lines from the .pro (they carry chord annotations).
  2. Applies the same chord pattern to verse lines (no chords in source).
  3. Expands the full song in the order defined in SONG_STRUCTURE.
  4. Maps XSC timings positionally across the expanded structure.
  5. Writes assets/song.cho ready for generate_karaoke.py.

Usage
-----
    python pro_to_cho.py
    # review/tweak assets/song.cho if needed
    python generate_karaoke.py
"""

import re
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────
PRO_FILE    = "assets/so_much_faster_now.pro"
XSC_FILE    = "assets/song.xsc"
OUTPUT_FILE = "assets/song.cho"

# Transposition map: chords as written in the .pro  →  chords in the recording.
# The .pro is in G; the recording is in E major.
TRANSPOSE = {
    "G":  "E",
    "C":  "A",
    "D7": "B",
    "D":  "B",
}

# Full song order — one entry per chord cycle.
# Label must match a key in SECTIONS below (populated from the .pro).
# Edit this list to match the actual recording structure.
SONG_STRUCTURE = [
    "chorus",
    "verse1",
    "chorus",
    "verse2",
    "chorus",
    "chorus",
    "chorus",
]
# ──────────────────────────────────────────────────────────────────────────


# ── XSC parser ────────────────────────────────────────────────────────────

def parse_xsc(xsc_path: Path) -> list[dict]:
    entries, in_markers = [], False
    with open(xsc_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line == "SectionStart,Markers":   in_markers = True;  continue
            if line == "SectionEnd,Markers":     break
            if not in_markers or not line.startswith("S,"): continue
            parts = line.split(",")
            if len(parts) < 6: continue
            label, ts = parts[3].strip(), parts[5].strip()
            m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", ts)
            if not m: continue
            h, mn, s, frac = m.groups()
            secs = round(int(h)*3600 + int(mn)*60 + int(s) + int(frac)/(10**len(frac)), 3)
            entries.append({"time": secs, "label": label})
    return entries


# ── ChordPro parser ───────────────────────────────────────────────────────

def parse_pro(pro_path: Path) -> tuple[str, list, dict]:
    """
    Parse the .pro file.

    Returns:
        title    : str
        chorus   : list of line-dicts  [{'segments': [{'chord': str, 'text': str}]}]
        verses   : dict  {'verse1': [line, ...], 'verse2': [line, ...], ...}
                   Each line is a plain string (no chord annotations).
    """
    content = pro_path.read_text(encoding="utf-8")

    # Title
    m = re.search(r'\{title:([^}]*)\}', content, re.IGNORECASE)
    title = m.group(1).strip() if m else "Song"

    # Split into lines, strip directives we don't need
    lines = content.splitlines()

    chorus_lines_raw = []
    verse_lines_raw  = []
    in_chorus = False

    for line in lines:
        stripped = line.strip()
        if re.match(r'\{soc\}', stripped, re.IGNORECASE):
            in_chorus = True;  continue
        if re.match(r'\{eoc\}', stripped, re.IGNORECASE):
            in_chorus = False; continue
        if re.match(r'\{[^}]+\}', stripped):
            continue   # skip other directives
        if not stripped:
            continue

        if in_chorus:
            chorus_lines_raw.append(stripped)
        else:
            verse_lines_raw.append(stripped)

    # Parse chorus lines into segments: [(chord, text), ...]
    def parse_line(raw: str) -> list[dict]:
        """Split a ChordPro line into chord+text segments."""
        tokens   = re.split(r'(\[[^\]]+\])', raw)
        segments = []
        cur_chord = None
        cur_text  = []
        for tok in tokens:
            if re.match(r'^\[[^\]]+\]$', tok):
                if cur_chord is not None:
                    segments.append({"chord": cur_chord, "text": " ".join(cur_text).strip()})
                chord_raw = tok[1:-1]
                cur_chord = TRANSPOSE.get(chord_raw, chord_raw)
                cur_text  = []
            else:
                t = tok.strip()
                if t:
                    cur_text.append(t)
        if cur_chord is not None:
            segments.append({"chord": cur_chord, "text": " ".join(cur_text).strip()})
        return segments

    chorus = [{"segments": parse_line(l)} for l in chorus_lines_raw]

    # Split verse lines into verse1 / verse2 etc. (separated by blank lines).
    # Must properly skip chorus content using soc/eoc tracking.
    raw_verse_blocks = []
    current_block: list[str] = []
    in_chorus_v = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'\{soc\}', stripped, re.IGNORECASE):
            in_chorus_v = True;  continue
        if re.match(r'\{eoc\}', stripped, re.IGNORECASE):
            in_chorus_v = False; continue
        if re.match(r'\{[^}]+\}', stripped):
            continue   # skip all other directives
        if in_chorus_v:
            continue   # skip chorus content
        if not stripped:
            if current_block:
                raw_verse_blocks.append(current_block)
                current_block = []
        else:
            current_block.append(stripped)
    if current_block:
        raw_verse_blocks.append(current_block)

    # Filter out empty or whitespace-only blocks (e.g. trailing blank lines in .pro)
    raw_verse_blocks = [b for b in raw_verse_blocks if any(l.strip() for l in b)]

    verses = {}
    for i, block in enumerate(raw_verse_blocks, 1):
        verses[f"verse{i}"] = block

    return title, chorus, verses


# ── Apply chord pattern to a plain-text verse ────────────────────────────

def verse_to_segments(verse_lines: list[str], chorus: list[dict]) -> list[dict]:
    """
    Apply the chorus chord pattern to a verse that has no chord annotations.

    Each chorus line is a template that defines how many chord changes
    occur on that line and roughly where.  We distribute the verse words
    across those same chord slots.
    """
    result = []  # list of line-dicts  (same shape as chorus)

    for line_idx, chorus_line in enumerate(chorus):
        chord_seq = [seg["chord"] for seg in chorus_line["segments"]]

        if line_idx < len(verse_lines):
            raw_text = verse_lines[line_idx]
        else:
            raw_text = ""

        words  = raw_text.split()
        n_seg  = len(chord_seq)
        segs   = []

        if n_seg == 0:
            segs.append({"chord": "", "text": raw_text})
        else:
            # Distribute words across chord slots as evenly as possible.
            base, extra = divmod(len(words), n_seg)
            pos = 0
            for s_idx, chord in enumerate(chord_seq):
                count  = base + (1 if s_idx < extra else 0)
                chunk  = " ".join(words[pos:pos+count])
                pos   += count
                segs.append({"chord": chord, "text": chunk})

        result.append({"segments": segs})

    return result


# ── Flatten structure into ordered segment list ───────────────────────────

def expand_structure(song_structure: list[str],
                     chorus: list[dict],
                     verses: dict) -> list[dict]:
    """
    Produce a flat list of (chord, text) segments in song order.
    """
    sections = {"chorus": chorus}
    sections.update({k: verse_to_segments(v, chorus) for k, v in verses.items()})

    flat = []
    for section_name in song_structure:
        if section_name not in sections:
            print(f"  [warn] Unknown section '{section_name}' in SONG_STRUCTURE — skipping.")
            continue
        for line in sections[section_name]:
            for seg in line["segments"]:
                flat.append(seg)

    return flat


# ── Match timings ─────────────────────────────────────────────────────────

def match_timings(flat_segments: list[dict], xsc_entries: list[dict]) -> list[dict]:
    if len(flat_segments) != len(xsc_entries):
        print(f"  [warn] {len(flat_segments)} chord segments vs "
              f"{len(xsc_entries)} XSC markers — matching by position.")

    timed = []
    for i, seg in enumerate(flat_segments):
        time = xsc_entries[i]["time"] if i < len(xsc_entries) else None
        timed.append({**seg, "time": time})
    return [s for s in timed if s["time"] is not None]


# ── Write ChordPro ────────────────────────────────────────────────────────

def write_cho(cho_path: Path, title: str, segments: list[dict]):
    lines = [f"{{title: {title}}}", ""]
    for seg in segments:
        lines.append(f'[{seg["chord"]}]{seg["text"]}')
    cho_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent

    print(f"Parsing {PRO_FILE} ...")
    title, chorus, verses = parse_pro(base / PRO_FILE)
    print(f"  Title:   {title}")
    print(f"  Chorus:  {len(chorus)} line(s), "
          f"{sum(len(l['segments']) for l in chorus)} chord segment(s)")
    for k, v in verses.items():
        print(f"  {k}: {len(v)} line(s)")

    print(f"Parsing {XSC_FILE} ...")
    xsc_entries = parse_xsc(base / XSC_FILE)
    chords_per_cycle = sum(len(l["segments"]) for l in chorus)
    total_cycles = len(xsc_entries) / chords_per_cycle
    print(f"  {len(xsc_entries)} markers  ÷  {chords_per_cycle} chords/cycle  "
          f"=  {total_cycles:.1f} cycles")

    print(f"Expanding song structure: {' -> '.join(SONG_STRUCTURE)} ...")
    flat = expand_structure(SONG_STRUCTURE, chorus, verses)
    print(f"  {len(flat)} chord segments total.")

    flat_timed = match_timings(flat, xsc_entries)

    out_path = base / OUTPUT_FILE
    write_cho(out_path, title, flat_timed)
    print(f"\nWritten: {out_path}")
    print("\nNext steps:")
    print("  1. Review assets/song.cho — tweak any lyrics that need adjusting.")
    print("  2. Run generate_karaoke.py to build karaoke.html.")


if __name__ == "__main__":
    main()
