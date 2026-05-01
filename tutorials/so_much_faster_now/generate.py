#!/usr/bin/env python3
"""
generate.py
===========
Generates song.html for the Let's Jam Bass Playalong tool.

Workflow
--------
1. Mark chord changes in Transcribe! (seventhstring.com/xscribe) using the
   chord's short name as the section label (e.g. "G", "Am", "Bb").
2. Save the .xsc file — the path is set in XSC_FILE below.
3. Run:  python generate.py
4. Open song.html in a browser.

To make any other change to the page, edit this file and re-run it.
The HTML file is fully regenerated each time — never edit it directly.
"""

import re
import json
from pathlib import Path


# ============================================================
#  CONFIGURATION
#  Everything about this specific song/page lives here.
# ============================================================

SONG_TITLE = "So Much Faster Now, E Major"
SUBTITLE   = "Bass Playalong"
AUDIO_FILE = "assets/song.mp3"

# Path to the Transcribe! project file (relative to this script).
# Set to None to skip XSC import and use FALLBACK_SONG_DATA instead.
XSC_FILE = "assets/song.xsc"

OUTPUT_FILE = "song.html"


# ============================================================
#  CHORD LIBRARY
#
#  Maps the short label you type in Transcribe! to a full
#  display name and a list of suggested bass notes.
#
#  Add or edit entries here to support any chord you need.
#  The key must exactly match the section label in the .xsc file.
# ============================================================

CHORD_LIBRARY = {
    # ── Natural major chords ──────────────────────────────────
    "C":   {"name": "C Major",  "notes": ["C — Root", "E — Major 3rd", "G — 5th"]},
    "D":   {"name": "D Major",  "notes": ["D — Root", "F# — Major 3rd", "A — 5th"]},
    "E":   {"name": "E Major",  "notes": ["E — Root", "G# — Major 3rd", "B — 5th"]},
    "F":   {"name": "F Major",  "notes": ["F — Root", "A — Major 3rd", "C — 5th"]},
    "G":   {"name": "G Major",  "notes": ["G — Root", "B — Major 3rd", "D — 5th"]},
    "A":   {"name": "A Major",  "notes": ["A — Root", "C# — Major 3rd", "E — 5th"]},
    "B":   {"name": "B Major",  "notes": ["B — Root", "D# — Major 3rd", "F# — 5th"]},

    # ── Natural minor chords ──────────────────────────────────
    "Cm":  {"name": "C Minor",  "notes": ["C — Root", "Eb — Minor 3rd", "G — 5th"]},
    "Dm":  {"name": "D Minor",  "notes": ["D — Root", "F — Minor 3rd",  "A — 5th"]},
    "Em":  {"name": "E Minor",  "notes": ["E — Root", "G — Minor 3rd",  "B — 5th"]},
    "Fm":  {"name": "F Minor",  "notes": ["F — Root", "Ab — Minor 3rd", "C — 5th"]},
    "Gm":  {"name": "G Minor",  "notes": ["G — Root", "Bb — Minor 3rd", "D — 5th"]},
    "Am":  {"name": "A Minor",  "notes": ["A — Root", "C — Minor 3rd",  "E — 5th"]},
    "Bm":  {"name": "B Minor",  "notes": ["B — Root", "D — Minor 3rd",  "F# — 5th"]},

    # ── Sharps / Flats ────────────────────────────────────────
    "C#":  {"name": "C# Major", "notes": ["C# — Root", "F — Major 3rd",  "G# — 5th"]},
    "Db":  {"name": "Db Major", "notes": ["Db — Root", "F — Major 3rd",  "Ab — 5th"]},
    "D#":  {"name": "D# Major", "notes": ["D# — Root", "G — Major 3rd",  "A# — 5th"]},
    "Eb":  {"name": "Eb Major", "notes": ["Eb — Root", "G — Major 3rd",  "Bb — 5th"]},
    "F#":  {"name": "F# Major", "notes": ["F# — Root", "A# — Major 3rd", "C# — 5th"]},
    "Gb":  {"name": "Gb Major", "notes": ["Gb — Root", "Bb — Major 3rd", "Db — 5th"]},
    "G#":  {"name": "G# Major", "notes": ["G# — Root", "C — Major 3rd",  "D# — 5th"]},
    "Ab":  {"name": "Ab Major", "notes": ["Ab — Root", "C — Major 3rd",  "Eb — 5th"]},
    "A#":  {"name": "A# Major", "notes": ["A# — Root", "D — Major 3rd",  "F — 5th"]},
    "Bb":  {"name": "Bb Major", "notes": ["Bb — Root", "D — Major 3rd",  "F — 5th"]},

    # ── Sharp/flat minor chords ───────────────────────────────
    "C#m": {"name": "C# Minor", "notes": ["C# — Root", "E — Minor 3rd",  "G# — 5th"]},
    "Ebm": {"name": "Eb Minor", "notes": ["Eb — Root", "Gb — Minor 3rd", "Bb — 5th"]},
    "F#m": {"name": "F# Minor", "notes": ["F# — Root", "A — Minor 3rd",  "C# — 5th"]},
    "Abm": {"name": "Ab Minor", "notes": ["Ab — Root", "B — Minor 3rd",  "Eb — 5th"]},
    "Bbm": {"name": "Bb Minor", "notes": ["Bb — Root", "Db — Minor 3rd", "F — 5th"]},
}


# ============================================================
#  FALLBACK SONG DATA
#  Used only when XSC_FILE is None or the file is missing.
#  chord must be either a key in CHORD_LIBRARY or a full name
#  string (in which case notes must be supplied manually).
# ============================================================

FALLBACK_SONG_DATA = [
    {"time": 0.000,  "chord": "G",  "notes": None},
    {"time": 15.182, "chord": "C",  "notes": None},
    {"time": 17.380, "chord": "G",  "notes": None},
    {"time": 21.669, "chord": "C",  "notes": None},
]


# ============================================================
#  XSC PARSER
# ============================================================

def parse_xsc(xsc_path: Path) -> list | None:
    """
    Parse section markers from a Transcribe! .xsc file.

    Each marker whose label matches a key in CHORD_LIBRARY is
    converted to a song-data entry. Unknown labels are included
    with a warning so you can add them to CHORD_LIBRARY.

    Returns a list of dicts, or None if the file has no markers.
    """
    if not xsc_path.exists():
        print(f"  [skip] XSC file not found: {xsc_path}")
        return None

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

            # Format: S,-1,0,LABEL,0,H:MM:SS.ffffff,
            parts = line.split(",")
            if len(parts) < 6:
                continue

            label     = parts[3].strip()
            timestamp = parts[5].strip()

            # Parse H:MM:SS.ffffff → total seconds
            m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", timestamp)
            if not m:
                continue
            h, mn, s, frac_str = m.group(1), m.group(2), m.group(3), m.group(4)
            seconds = int(h) * 3600 + int(mn) * 60 + int(s) + int(frac_str) / (10 ** len(frac_str))
            seconds = round(seconds, 3)

            if label in CHORD_LIBRARY:
                chord_def = CHORD_LIBRARY[label]
                entries.append({
                    "time":  seconds,
                    "chord": chord_def["name"],
                    "notes": chord_def["notes"],
                })
            else:
                print(f"  [warn] Unknown chord label '{label}' at {timestamp} "
                      f"— add it to CHORD_LIBRARY in generate.py")
                entries.append({
                    "time":  seconds,
                    "chord": label,
                    "notes": [f"{label} — Root"],
                })

    return entries if entries else None


# ============================================================
#  RESOLVE SONG DATA
#  Expand any shorthand entries in FALLBACK_SONG_DATA through
#  CHORD_LIBRARY before passing to the template.
# ============================================================

def resolve_song_data(raw: list) -> list:
    resolved = []
    for entry in raw:
        label  = entry["chord"]
        notes  = entry.get("notes")
        if notes is None and label in CHORD_LIBRARY:
            chord_def = CHORD_LIBRARY[label]
            resolved.append({
                "time":  entry["time"],
                "chord": chord_def["name"],
                "notes": chord_def["notes"],
            })
        else:
            resolved.append({
                "time":  entry["time"],
                "chord": label,
                "notes": notes or [],
            })
    return resolved


# ============================================================
#  SONG DATA → JAVASCRIPT ARRAY STRING
# ============================================================

def song_data_to_js(song_data: list) -> str:
    lines = []
    for entry in song_data:
        notes_js = json.dumps(entry["notes"])
        lines.append(
            f'      {{ time: {entry["time"]:.3f}, '
            f'chord: {json.dumps(entry["chord"])}, '
            f'notes: {notes_js} }}'
        )
    return "[\n" + ",\n".join(lines) + "\n    ]"


# ============================================================
#  HTML TEMPLATE
#  Edit the HTML/CSS/JS here, then re-run generate.py.
#
#  Placeholders (replaced at build time):
#    %%PAGE_TITLE%%   — browser tab title
#    %%SONG_TITLE%%   — large heading inside the page
#    %%SUBTITLE%%     — smaller subheading
#    %%AUDIO_FILE%%   — src attribute of the <audio> element
#    %%SONG_DATA%%    — the JS songData array literal
# ============================================================

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>%%PAGE_TITLE%%</title>
  <style>
    /* ─── Reset & CSS variables ─────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:          #0d0d16;
      --surface:     #1a1a2e;   /* letsjam.org --color-primary */
      --surface2:    #16213e;   /* letsjam.org --color-dark-bg */
      --border:      #243358;
      --accent:      #e94560;   /* letsjam.org --color-accent */
      --accent-dim:  rgba(233, 69, 96, 0.18);
      --text:        #f0f0f5;
      --muted:       #5a6480;
      --radius:      14px;
      --font:        'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2.5rem 1rem 4rem;
      gap: 1.75rem;
    }

    /* ─── Header ─────────────────────────────────────────────── */
    header {
      text-align: center;
    }
    .lj-logo {
      width: 200px;
      height: auto;
      display: block;
      margin: 0 auto 0.9rem;
      filter: drop-shadow(0 2px 12px rgba(233, 69, 96, 0.15));
    }
    header h1 {
      font-size: 1.1rem;
      letter-spacing: 0.25em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }
    header p {
      font-size: 0.78rem;
      color: var(--muted);
      margin-top: 0.3rem;
      letter-spacing: 0.08em;
    }
    header .tagline {
      font-size: 0.8rem;
      color: var(--muted);
      margin-top: 0.2rem;
      font-style: italic;
    }

    /* ─── Player Card ────────────────────────────────────────── */
    .player-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.5rem 2rem;
      width: 100%;
      max-width: 680px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
      display: flex;
      flex-direction: column;
      gap: 1.1rem;
    }

    audio {
      width: 100%;
      accent-color: var(--accent);
    }

    /* ─── Speed Buttons ──────────────────────────────────────── */
    .speed-row {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }
    .speed-label {
      font-size: 0.72rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      margin-right: 0.2rem;
    }
    .speed-btn {
      background: var(--surface2);
      color: var(--muted);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.4rem 1rem;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, color 0.15s, border-color 0.15s;
    }
    .speed-btn:hover { background: var(--accent-dim); color: var(--text); }
    .speed-btn.active {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }

    /* ─── Chord Display ──────────────────────────────────────── */
    .chord-display {
      width: 100%;
      max-width: 680px;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    .now-playing {
      background: var(--surface);
      border: 2px solid var(--accent);
      border-radius: var(--radius);
      padding: 2.25rem 2rem 1.75rem;
      text-align: center;
      box-shadow: 0 0 60px rgba(233, 69, 96, 0.12), inset 0 0 60px rgba(233,69,96,0.03);
      transition: border-color 0.25s;
    }
    .section-label {
      font-size: 0.7rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 0.6rem;
    }

    #currentChord {
      font-size: clamp(3.5rem, 12vw, 6rem);
      font-weight: 900;
      line-height: 1;
      color: var(--accent);
      text-shadow: 0 0 40px rgba(233,69,96,0.5);
      letter-spacing: -0.02em;
      margin-bottom: 0.4rem;
      transition: color 0.2s;
      min-height: 1.1em;
    }

    /* ─── Fretboard diagram ──────────────────────────────────── */
    .fretboard-wrap {
      margin: 0.9rem 0 0.75rem;
    }
    #fretboard svg {
      display: block;
      width: 100%;
      max-width: 300px;
      height: auto;
      margin: 0 auto;
      overflow: visible;
    }
    .fretboard-legend {
      display: flex;
      gap: 1.4rem;
      justify-content: center;
      margin-top: 0.55rem;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.7rem;
      color: var(--muted);
      letter-spacing: 0.03em;
    }
    .legend-pip {
      width: 11px;
      height: 11px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .legend-pip.root  { background: #e94560; }
    .legend-pip.fifth { background: #2563eb; }
    .legend-pip.open  { background: transparent; border: 1.5px solid var(--muted); }

    /* Notes pills */
    .notes-list {
      display: flex;
      gap: 0.6rem;
      justify-content: center;
      flex-wrap: wrap;
      min-height: 2rem;
    }
    .note-pill {
      background: var(--accent-dim);
      border: 1px solid var(--accent);
      border-radius: 999px;
      padding: 0.38rem 1.1rem;
      font-size: 0.92rem;
      font-weight: 600;
      color: var(--text);
      white-space: nowrap;
      transition: background 0.2s;
    }
    .note-pill.waiting {
      border-color: var(--border);
      background: transparent;
      color: var(--muted);
      font-style: italic;
      font-weight: 400;
    }

    /* Countdown bar */
    .countdown-track {
      height: 5px;
      background: var(--surface2);
      border-radius: 3px;
      overflow: hidden;
      margin-top: 1.4rem;
    }
    .countdown-fill {
      height: 100%;
      background: var(--accent);
      width: 100%;
      border-radius: 3px;
      transition: width 0.25s linear;
    }

    /* ─── Up Next ────────────────────────────────────────────── */
    .up-next {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.1rem 1.5rem;
      display: flex;
      align-items: center;
      gap: 1.2rem;
      flex-wrap: wrap;
    }
    .up-next .section-label {
      margin-bottom: 0;
      flex-shrink: 0;
      min-width: 4rem;
    }
    #nextChord {
      font-size: 1.9rem;
      font-weight: 800;
      color: var(--muted);
      flex-shrink: 0;
    }
    .next-notes {
      display: flex;
      gap: 0.45rem;
      flex-wrap: wrap;
    }
    .next-note-pill {
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--muted);
      border-radius: 999px;
      padding: 0.2rem 0.75rem;
      font-size: 0.8rem;
    }
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

  <div class="chord-display">

    <div class="now-playing">
      <div class="section-label">Now Playing</div>
      <div id="currentChord">–</div>

      <div class="fretboard-wrap">
        <div id="fretboard"></div>
        <div class="fretboard-legend">
          <span class="legend-item"><span class="legend-pip root"></span>Root (1)</span>
          <span class="legend-item"><span class="legend-pip fifth"></span>Fifth (5)</span>
          <span class="legend-item"><span class="legend-pip open"></span>Open string</span>
        </div>
      </div>

      <div class="notes-list" id="currentNotes"></div>
      <div class="countdown-track">
        <div class="countdown-fill" id="countdownFill"></div>
      </div>
    </div>

    <div class="up-next">
      <span class="section-label">Up Next</span>
      <span id="nextChord">–</span>
      <div class="next-notes" id="nextNotes"></div>
    </div>

  </div>

  <script>
    // ================================================================
    //  SONG DATA — generated by generate.py, do not edit directly
    // ================================================================
    const songData = %%SONG_DATA%%;

    // ================================================================
    //  DOM references
    // ================================================================
    const audio          = document.getElementById('player');
    const currentChordEl = document.getElementById('currentChord');
    const currentNotesEl = document.getElementById('currentNotes');
    const nextChordEl    = document.getElementById('nextChord');
    const nextNotesEl    = document.getElementById('nextNotes');
    const countdownFill  = document.getElementById('countdownFill');
    const fretboardEl    = document.getElementById('fretboard');

    let activeIndex = -1;

    // ================================================================
    //  Speed controls
    // ================================================================
    document.querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        audio.playbackRate = parseFloat(btn.dataset.speed);
        audio.preservesPitch = true;
        document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    // ================================================================
    //  Core sync
    // ================================================================
    audio.addEventListener('timeupdate', () => {
      const t = audio.currentTime;
      let idx = -1;
      for (let i = songData.length - 1; i >= 0; i--) {
        if (t >= songData[i].time) { idx = i; break; }
      }
      if (idx !== activeIndex) {
        activeIndex = idx;
        renderChordDisplay(idx);
      }
      updateCountdown(idx, t);
    });

    // ================================================================
    //  Render current chord + fretboard + up-next
    // ================================================================
    function renderChordDisplay(idx) {
      if (idx < 0) {
        currentChordEl.textContent = '\\u2013';
        currentNotesEl.innerHTML = '';
        nextChordEl.textContent = songData[0]?.chord ?? '\\u2013';
        renderNextNotes(0);
        fretboardEl.innerHTML = buildFretboardSVG(null, null);
        return;
      }

      const entry = songData[idx];
      const next  = songData[idx + 1];

      currentChordEl.textContent = entry.chord;
      currentNotesEl.innerHTML = entry.notes
        .map(n => `<span class="note-pill">${n}</span>`)
        .join('');

      const parsed = parseChord(entry.chord);
      fretboardEl.innerHTML = parsed
        ? buildFretboardSVG(parsed.rootSemitone, parsed.fifthSemitone)
        : '';

      if (next) {
        nextChordEl.textContent = next.chord;
        renderNextNotes(idx + 1);
      } else {
        nextChordEl.textContent = '(End)';
        nextNotesEl.innerHTML = '';
      }
    }

    function renderNextNotes(idx) {
      const entry = songData[idx];
      if (!entry) { nextNotesEl.innerHTML = ''; return; }
      nextNotesEl.innerHTML = entry.notes
        .map(n => `<span class="next-note-pill">${n}</span>`)
        .join('');
    }

    // ================================================================
    //  Countdown bar
    // ================================================================
    function updateCountdown(idx, currentTime) {
      if (idx < 0 || idx >= songData.length - 1) {
        countdownFill.style.width = idx < 0 ? '100%' : '0%';
        return;
      }
      const start    = songData[idx].time;
      const end      = songData[idx + 1].time;
      const progress = (currentTime - start) / (end - start);
      countdownFill.style.width = (100 - progress * 100).toFixed(1) + '%';
    }

    // ================================================================
    //  Reset on end / seek
    // ================================================================
    audio.addEventListener('ended', () => {
      activeIndex = -1;
      currentChordEl.textContent = '\\u2013';
      currentNotesEl.innerHTML = '<span class="note-pill waiting">Song ended \\u2014 rewind to replay</span>';
      nextChordEl.textContent = '\\u2013';
      nextNotesEl.innerHTML = '';
      countdownFill.style.width = '0%';
    });

    audio.addEventListener('seeked', () => { activeIndex = -2; });

    // ================================================================
    //  FRETBOARD SVG GENERATOR
    // ================================================================

    const NOTE_SEMITONE = {
      'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4,
      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8,
      'A':9, 'A#':10, 'Bb':10, 'B':11
    };

    const OPEN_STRINGS = [7, 2, 9, 4]; // G D A E
    const STR_LABELS   = ['G', 'D', 'A', 'E'];
    const STR_WIDTH    = [1, 1.5, 2, 2.5];

    function parseChord(chordName) {
      const match = chordName.match(/^([A-G][#b]?)/);
      if (!match) return null;
      const root = NOTE_SEMITONE[match[1]];
      if (root === undefined) return null;
      return { rootSemitone: root, fifthSemitone: (root + 7) % 12 };
    }

    function getPositions(semitone) {
      return OPEN_STRINGS.reduce((acc, open, sIdx) => {
        const fret = (semitone - open + 12) % 12;
        if (fret <= 5) acc.push({ s: sIdx, fret });
        return acc;
      }, []);
    }

    function buildFretboardSVG(rootSemitone, fifthSemitone) {
      const W = 256, H = 84, labelW = 24, nutX = labelW, nutW = 4;
      const fretW = 40, nFrets = 5, topPad = 18, strGap = 16, dotR = 8;
      const openX  = nutX - 13;
      const fbRight = nutX + nutW + nFrets * fretW;
      const strY = OPEN_STRINGS.map((_, i) => topPad + i * strGap);
      const cx   = fret => fret === 0 ? openX : nutX + nutW + (fret - 0.5) * fretW;

      const p = [];
      p.push(`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`);
      p.push(`<rect width="${W}" height="${H}" fill="#0d1117" rx="8"/>`);

      for (let f = 1; f <= nFrets; f++) {
        const x = nutX + nutW + (f - 0.5) * fretW;
        p.push(`<text x="${x}" y="11" text-anchor="middle" font-size="9" fill="#2d3f55">${f}</text>`);
      }

      STR_LABELS.forEach((lbl, i) => {
        p.push(`<text x="${fbRight + 6}" y="${strY[i] + 4}" text-anchor="start" font-size="9" font-weight="700" fill="#2d3f55">${lbl}</text>`);
      });

      strY.forEach((y, i) => {
        p.push(`<line x1="${nutX + nutW}" y1="${y}" x2="${fbRight}" y2="${y}" stroke="#1a2d46" stroke-width="${STR_WIDTH[i]}"/>`);
      });

      for (let f = 1; f <= nFrets; f++) {
        const x = nutX + nutW + f * fretW;
        p.push(`<line x1="${x}" y1="${strY[0]}" x2="${x}" y2="${strY[3]}" stroke="#1a2d46" stroke-width="1"/>`);
      }

      const nutTop = strY[0] - 6, nutBot = strY[3] + 6;
      p.push(`<rect x="${nutX}" y="${nutTop}" width="${nutW}" height="${nutBot - nutTop}" fill="#c0c8d8" rx="1"/>`);
      p.push(`<line x1="${nutX - 1}" y1="${strY[0]}" x2="${nutX - 1}" y2="${strY[3]}" stroke="#1a2d46" stroke-width="1" stroke-dasharray="3 3"/>`);

      function drawDot(fret, sIdx, label, fill, stroke) {
        const x = cx(fret), y = strY[sIdx];
        if (fret === 0) {
          p.push(`<circle cx="${x}" cy="${y}" r="${dotR}" fill="${fill}" fill-opacity="0.15" stroke="${stroke}" stroke-width="1.5"/>`);
          p.push(`<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="8" font-weight="700" fill="${stroke}">${label}</text>`);
        } else {
          p.push(`<circle cx="${x}" cy="${y}" r="${dotR}" fill="${fill}"/>`);
          p.push(`<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="8" font-weight="700" fill="#fff">${label}</text>`);
        }
      }

      if (fifthSemitone !== null) {
        getPositions(fifthSemitone).forEach(({ s, fret }) =>
          drawDot(fret, s, '5', '#2563eb', '#60a5fa'));
      }
      if (rootSemitone !== null) {
        getPositions(rootSemitone).forEach(({ s, fret }) =>
          drawDot(fret, s, '1', '#e94560', '#f87171'));
      }

      p.push(`</svg>`);
      return p.join('');
    }

    renderChordDisplay(-1);
  </script>

</body>
</html>
"""


# ============================================================
#  BUILD
# ============================================================

def build_html(title: str, subtitle: str, audio_file: str, song_data: list) -> str:
    html = HTML_TEMPLATE
    html = html.replace("%%PAGE_TITLE%%",  f"{title} — Bass Playalong")
    html = html.replace("%%SONG_TITLE%%",  title)
    html = html.replace("%%SUBTITLE%%",    subtitle)
    html = html.replace("%%AUDIO_FILE%%",  audio_file)
    html = html.replace("%%SONG_DATA%%",   song_data_to_js(song_data))
    return html


# ============================================================
#  MAIN
# ============================================================

def main():
    base = Path(__file__).parent

    song_data = None

    if XSC_FILE:
        xsc_path = base / XSC_FILE
        print(f"Parsing {xsc_path} ...")
        song_data = parse_xsc(xsc_path)
        if song_data:
            print(f"  Imported {len(song_data)} chord marker(s) from XSC file.")

    if not song_data:
        print("  Using FALLBACK_SONG_DATA.")
        song_data = resolve_song_data(FALLBACK_SONG_DATA)

    html     = build_html(SONG_TITLE, SUBTITLE, AUDIO_FILE, song_data)
    out_path = base / OUTPUT_FILE
    out_path.write_text(html, encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
