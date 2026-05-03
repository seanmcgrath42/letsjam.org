#!/usr/bin/env python3
"""
generate_karaoke.py
===================
Step 2 of the karaoke build process.

Reads the edited ChordPro file (assets/song.cho) and the XSC chord
timings, then generates a self-contained karaoke.html page.

The page shows the full lyrics. Each chord section is a block; as the
song plays the active block scrolls into view and highlights — giving
musicians a clear view of the current chord change and lyrics.

Usage
-----
    python generate_karaoke.py

Workflow
--------
    1. Run transcribe.py  →  assets/song.cho  (auto-generated)
    2. Edit assets/song.cho  (fix lyrics, adjust chord placements)
    3. Run generate_karaoke.py  →  karaoke.html
    4. Open karaoke.html in a browser.
"""

import re
import json
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────
CHO_FILE    = "assets/song.cho"
XSC_FILE    = "assets/song.xsc"
AUDIO_FILE  = "assets/song.mp3"
OUTPUT_FILE = "karaoke.html"
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


# ── XSC parser ────────────────────────────────────────────────────────────

def parse_xsc(xsc_path: Path) -> list:
    if not xsc_path.exists():
        raise FileNotFoundError(f"XSC file not found: {xsc_path}")

    entries, in_markers = [], False

    with open(xsc_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line == "SectionStart,Markers":
                in_markers = True; continue
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
            seconds = round(int(h)*3600 + int(mn)*60 + int(s) + int(frac)/(10**len(frac)), 3)
            entries.append({"time": seconds, "label": label})

    return entries


# ── ChordPro parser ───────────────────────────────────────────────────────

def parse_chordpro(cho_path: Path) -> tuple[str, str, list]:
    """
    Parse a flat ChordPro file.

    Returns:
        title   : str
        artist  : str
        segments: list of {'chord': str, 'text': str}
                  Each segment is the lyrics from one [Chord] marker
                  up to (but not including) the next.
    """
    content = cho_path.read_text(encoding="utf-8")

    # Extract header directives
    title  = ""
    artist = ""
    for m in re.finditer(r'\{(\w+):\s*([^}]*)\}', content):
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "title":  title  = val
        if key == "artist": artist = val

    # Remove all directives for lyric processing
    body = re.sub(r'\{[^}]*\}', '', content).strip()

    # Split on [Chord] tokens while keeping them
    tokens = re.split(r'(\[[^\]]+\])', body)

    segments = []
    current_chord = None
    current_text  = []

    for token in tokens:
        if re.match(r'^\[[^\]]+\]$', token):
            # Flush previous segment
            if current_chord is not None:
                text = " ".join(current_text).strip()
                if text or current_chord:
                    segments.append({"chord": current_chord, "text": text})
            current_chord = token[1:-1]
            current_text  = []
        else:
            # Normalise whitespace but preserve line breaks as spaces
            cleaned = re.sub(r'\s+', ' ', token)
            if cleaned.strip():
                current_text.append(cleaned.strip())

    # Flush final segment
    if current_chord is not None:
        text = " ".join(current_text).strip()
        segments.append({"chord": current_chord, "text": text})

    return title, artist, segments


# ── Match ChordPro segments to XSC timings ───────────────────────────────

def match_timings(segments: list, xsc_entries: list) -> list:
    """
    Positionally match ChordPro chord segments to XSC timing entries.

    Both lists should have the same length (one entry per chord change).
    If they differ, we do the best we can and warn.

    Returns segments with a 'time' key added.
    """
    if len(segments) != len(xsc_entries):
        print(f"  [warn] ChordPro has {len(segments)} chord segments but "
              f"XSC has {len(xsc_entries)} markers. "
              f"Matching by position; extras will be ignored.")

    timed = []
    for i, seg in enumerate(segments):
        time = xsc_entries[i]["time"] if i < len(xsc_entries) else None
        timed.append({**seg, "time": time})
    return timed


# ── JS data builder ───────────────────────────────────────────────────────

def segments_to_js(segments: list) -> str:
    lines = []
    for seg in segments:
        lines.append(
            f'      {{ time: {seg["time"]:.3f}, '
            f'chord: {json.dumps(seg["chord"])}, '
            f'text: {json.dumps(seg["text"])} }}'
        )
    return "[\n" + ",\n".join(lines) + "\n    ]"


# ── HTML template ─────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>%%PAGE_TITLE%%</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:         #0d0d16;
      --surface:    #1a1a2e;
      --surface2:   #16213e;
      --border:     #243358;
      --accent:     #e94560;
      --accent-dim: rgba(233, 69, 96, 0.18);
      --text:       #f0f0f5;
      --muted:      #5a6480;
      --radius:     14px;
      --font:       'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem 4rem;
      gap: 1.5rem;
    }

    /* ── Header ── */
    header { text-align: center; }
    .lj-logo {
      width: 180px; height: auto;
      display: block; margin: 0 auto 0.8rem;
      filter: drop-shadow(0 2px 12px rgba(233,69,96,0.15));
    }
    header h1 {
      font-size: 1.05rem; letter-spacing: 0.25em;
      text-transform: uppercase; color: var(--accent); font-weight: 700;
    }
    header p {
      font-size: 0.78rem; color: var(--muted);
      margin-top: 0.25rem; letter-spacing: 0.08em;
    }

    /* ── Player card ── */
    .player-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1.25rem 1.75rem;
      width: 100%; max-width: 700px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
      display: flex; flex-direction: column; gap: 1rem;
    }
    audio { width: 100%; accent-color: var(--accent); }

    /* Speed buttons */
    .speed-row {
      display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    }
    .speed-label {
      font-size: 0.7rem; letter-spacing: 0.1em;
      text-transform: uppercase; color: var(--muted); margin-right: 0.2rem;
    }
    .speed-btn {
      background: var(--surface2); color: var(--muted);
      border: 1px solid var(--border); border-radius: 8px;
      padding: 0.35rem 0.9rem; font-size: 0.82rem; font-weight: 600;
      cursor: pointer; transition: background .15s, color .15s, border-color .15s;
    }
    .speed-btn:hover { background: var(--accent-dim); color: var(--text); }
    .speed-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

    /* ── Lyrics scroll area ── */
    .lyrics-outer {
      width: 100%; max-width: 700px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1.5rem 1.75rem;
      box-shadow: 0 8px 40px rgba(0,0,0,0.4);
    }

    #lyrics-scroll {
      /* Fixed-height scrollable window; JS scrolls it */
      max-height: 60vh;
      overflow-y: auto;
      scroll-behavior: smooth;
      /* Hide scrollbar on most browsers for cleanliness */
      scrollbar-width: thin;
      scrollbar-color: var(--border) transparent;
    }
    #lyrics-scroll::-webkit-scrollbar { width: 4px; }
    #lyrics-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

    /* ── Individual chord segment ── */
    .seg {
      display: flex;
      align-items: baseline;
      gap: 0.9rem;
      padding: 0.65rem 0.5rem;
      border-radius: 8px;
      transition: background 0.2s, box-shadow 0.2s;
      margin-bottom: 0.15rem;
    }
    .seg-chord {
      min-width: 3.2rem;
      font-size: 1.35rem;
      font-weight: 900;
      color: var(--muted);
      letter-spacing: -0.01em;
      flex-shrink: 0;
      transition: color 0.2s;
      text-align: right;
    }
    .seg-text {
      font-size: 1.05rem;
      line-height: 1.55;
      color: var(--muted);
      transition: color 0.2s;
    }

    /* Active segment */
    .seg.active {
      background: var(--accent-dim);
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .seg.active .seg-chord {
      color: var(--accent);
      text-shadow: 0 0 20px rgba(233,69,96,0.6);
    }
    .seg.active .seg-text {
      color: var(--text);
      font-weight: 500;
    }

    /* Upcoming segment — slightly lighter than idle */
    .seg.upcoming {
      opacity: 0.65;
    }
    .seg.upcoming .seg-chord { color: #3a4868; }
    .seg.upcoming .seg-text  { color: #3a4868; }

    /* Past segments */
    .seg.past .seg-chord { color: #2a3248; }
    .seg.past .seg-text  { color: #2a3248; }
  </style>
</head>
<body>

  <header>
    <a href="https://letsjam.org" target="_blank" rel="noopener">
      <img src="https://letsjam.org/assets/images/lets_jam_logo_347x141.png"
           alt="Let's Jam" class="lj-logo" />
    </a>
    <h1>%%SONG_TITLE%%</h1>
    <p>%%SUBTITLE%%</p>
  </header>

  <div class="player-card">
    <audio id="player" controls src="%%AUDIO_FILE%%"></audio>
    <div class="speed-row">
      <span class="speed-label">Speed</span>
      <button class="speed-btn" data-speed="0.5">0.5×</button>
      <button class="speed-btn" data-speed="0.75">0.75×</button>
      <button class="speed-btn active" data-speed="1.0">1.0×</button>
    </div>
  </div>

  <div class="lyrics-outer">
    <div id="lyrics-scroll">
      <!-- Segments injected by JS -->
    </div>
  </div>

  <script>
    // ── Song data (generated by generate_karaoke.py) ──────────────────
    const songData = %%SONG_DATA%%;

    // ── DOM ──────────────────────────────────────────────────────────
    const audio      = document.getElementById('player');
    const lyricsEl   = document.getElementById('lyrics-scroll');

    // ── Build DOM from song data ──────────────────────────────────────
    const segEls = songData.map((seg, i) => {
      const div   = document.createElement('div');
      div.className = 'seg upcoming';
      div.dataset.idx = i;

      const chord = document.createElement('span');
      chord.className = 'seg-chord';
      chord.textContent = seg.chord;

      const text = document.createElement('span');
      text.className = 'seg-text';
      text.textContent = seg.text;

      div.appendChild(chord);
      div.appendChild(text);
      lyricsEl.appendChild(div);
      return div;
    });

    // ── Speed buttons ─────────────────────────────────────────────────
    document.querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        audio.playbackRate = parseFloat(btn.dataset.speed);
        audio.preservesPitch = true;
        document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    // ── Playback sync ─────────────────────────────────────────────────
    let activeIndex = -1;

    audio.addEventListener('timeupdate', () => {
      const t = audio.currentTime;
      let idx = -1;
      for (let i = songData.length - 1; i >= 0; i--) {
        if (t >= songData[i].time) { idx = i; break; }
      }
      if (idx !== activeIndex) {
        activeIndex = idx;
        updateHighlight(idx);
      }
    });

    audio.addEventListener('seeked', () => { activeIndex = -2; });

    audio.addEventListener('ended', () => {
      activeIndex = -1;
      segEls.forEach(el => { el.classList.remove('active', 'upcoming'); el.classList.add('past'); });
    });

    function updateHighlight(idx) {
      segEls.forEach((el, i) => {
        el.classList.remove('active', 'past', 'upcoming');
        if (i < idx)       el.classList.add('past');
        else if (i === idx) el.classList.add('active');
        else                el.classList.add('upcoming');
      });

      // Auto-scroll: keep active segment roughly in the top third of the viewport
      if (idx >= 0 && segEls[idx]) {
        const container    = lyricsEl;
        const el           = segEls[idx];
        const containerRect = container.getBoundingClientRect();
        const elRect        = el.getBoundingClientRect();
        // Position relative to the scrollable container
        const relativeTop   = elRect.top - containerRect.top + container.scrollTop;
        // Keep active line in the upper third of the visible area
        const target        = relativeTop - container.clientHeight * 0.25;
        container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
      } else if (idx < 0) {
        lyricsEl.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }

    // Initial state
    updateHighlight(-1);
  </script>

</body>
</html>
"""


# ── Build ─────────────────────────────────────────────────────────────────

def build_html(title: str, artist: str, audio_file: str, segments: list) -> str:
    subtitle = "Karaoke — Bass Playalong" if not artist else f"{artist} — Karaoke"
    page_title = f"{title} — Karaoke"
    html = HTML_TEMPLATE
    html = html.replace("%%PAGE_TITLE%%",  page_title)
    html = html.replace("%%SONG_TITLE%%",  title)
    html = html.replace("%%SUBTITLE%%",    subtitle)
    html = html.replace("%%AUDIO_FILE%%",  audio_file)
    html = html.replace("%%SONG_DATA%%",   segments_to_js(segments))
    return html


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent

    cho_path = base / CHO_FILE
    if not cho_path.exists():
        raise SystemExit(
            f"\n[error] ChordPro file not found: {cho_path}\n"
            "  Run transcribe.py first to generate it.\n"
        )

    print(f"Parsing ChordPro file: {cho_path.name} ...")
    title, artist, segments = parse_chordpro(cho_path)
    print(f"  Title:    {title or '(none)'}")
    print(f"  Artist:   {artist or '(none)'}")
    print(f"  Segments: {len(segments)}")

    print(f"Parsing XSC timings: {XSC_FILE} ...")
    xsc_entries = parse_xsc(base / XSC_FILE)
    print(f"  Markers: {len(xsc_entries)}")

    print("Matching chord segments to timings ...")
    timed = match_timings(segments, xsc_entries)

    # Drop any segments without a timing (shouldn't happen in normal use)
    timed = [s for s in timed if s["time"] is not None]

    song_title = title or "Song"
    html = build_html(song_title, artist, AUDIO_FILE, timed)

    out_path = base / OUTPUT_FILE
    out_path.write_text(html, encoding="utf-8")
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
