# OpenAL Explore

A PySide6 scene editor and spatial audio demo for `openal-py`. The player stays
at the centre while the world scrolls. Audio comes from stationary points or
sources travelling along editable polylines.

## Run

The project environment is already set up with Python 3.11, your Windows wheel,
PySide6, SoundFile, NumPy and pytest:

```powershell
cd C:\Dev\openal-explore
.\.venv\Scripts\python.exe run.py
```

Alternatively, `./run.ps1` forwards arguments to the same command. On first run,
the demo generates three short mono WAV files in `samples/`: a pulsing beacon,
a chime, and an engine sound. It also places the available `samples/ogg/` files
around an outer ring: the ten included samples are 65 metres from the starting
player position and approximately 40 metres apart. Each has a 26-metre audible
radius, so walk towards a source to hear it without the whole collection playing
at once. **File → Load demo scene** restores this scene.

```powershell
# Open a saved scene
.\.venv\Scripts\python.exe run.py scene.json

# Edit with no audio device, or start with an empty scene
.\.venv\Scripts\python.exe run.py --no-audio
.\.venv\Scripts\python.exe run.py --empty
```

To recreate the environment, use Python 3.11 and the matching wheel:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install C:\Dev\openal-py\wheelhouse\windows.cd529808ce214dd8b912c1fbb494ce46\openal_py-0.1.0-cp311-cp311-win_amd64.whl
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

For a different Python version, install its matching `win_amd64` wheel from
`C:\Dev\openal-py\wheelhouse\` first. The demo does not modify the wrapper repository.

## Controls

Click the map to give it keyboard focus. Keyboard movement deliberately stops
when editing a property or switching applications.

| Control | Action |
| --- | --- |
| Up / Down | Move forward/backward along the player's heading |
| Left / Right or Q / E | Turn listener left/right; map stays north-up |
| Mouse wheel | Zoom, keeping player centred |
| 1 | Inspect; select a source and drag it or its entire path |
| 2 | Add a sound point with one click |
| 3 | Draw a path: click vertices, Enter/double-click to finish |
| 4 | Edit vertices: select a path, then drag square handles |
| Double-click a segment in Edit Vertices | Insert a control point |
| Delete / Backspace on map | Remove selected vertex, or selected source |
| Backspace while drawing | Undo the last draft vertex |
| Escape | Cancel drawing and return to Inspect |
| Right-click | Cancel the current draft |
| Space | Pause/resume audio, movement and path animation |
| Ctrl+0 | Fit the scene around the current player position |
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S | New / open / save / save as |

The toolbar buttons also work without keyboard shortcuts. Shortcuts 1–4 and
Space apply only to the map, so they do not interfere with entering properties.
**Restart** resets all path positions and replays sounds. **Replay / retry sound**
restarts just the selected sound without resetting its path.

Select objects on the map or in **Scene objects**. The properties and object
panels can be moved, detached, closed, and reopened through **View**.
The **Vertices** inspector tab provides numeric editing and add/remove buttons.
Paths retain at least two control points. Closed-loop paths include a segment
from the last point back to the first; back-and-forth paths reverse at their ends.

## Sound properties

- File, enabled, looping (on by default), volume and pitch.
- Point coordinates, altitude, and live position/velocity/playback status.
- Line speed in metres per second, back-and-forth/closed-loop travel, and path-facing direction.
- Audible radius, reference distance, maximum distance and rolloff.
- Direction, inner/outer cone angles and outside-cone volume.
- EFX low-pass filtering, high-frequency gain, air absorption, and a reverb send.

**Player / listener** properties include coordinates, altitude, movement speed,
facing direction, master volume, HRTF, all seven OpenAL
distance models, Doppler factor, speed of sound, and shared reverb gain/decay.
Unsupported HRTF/EFX controls are disabled. HRTF reports the device's actual
status, since an output device may deny a request. Use headphones to hear HRTF.

Coordinates are metres: X east, Y north, altitude up. OpenAL receives
`(x, altitude, -y)`, with listener up `(0, 1, 0)`. Heading 0° is north and 90°
is east. Line velocities follow the current segment; listener velocity follows
keyboard motion. Property edits and dragging teleport objects without an
artificial Doppler impulse. Corners and path-end reversals are instantaneous.

**Audible radius** is a demo-level hard stop, using the full 3D source/listener
distance. **Max distance** is an OpenAL attenuation parameter; it does not
automatically mute an inverse-distance source. For clamped models, attenuation
stops changing beyond max distance. The map shows selected-source radius,
reference/max distance and directional cone from a top-down view; altitude
still participates in the actual distance and mixing.

An unchecked **Loop sound** plays once on entry into range or when replayed. It
does not restart every frame after finishing. Leaving and re-entering range,
or disabling/re-enabling it, arms it again. Path motion and audio looping are
independent. Disabling a source stops its audio and freezes its path motion.

## Files and scenes

[SoundFile](https://pypi.org/project/soundfile/) handles decoding through
libsndfile. WAV, FLAC, OGG and other installed decoder formats can be selected.
Decoded channels are averaged to mono and converted to PCM16 for OpenAL
positional playback; the original files are unchanged. Decoding and resource
creation currently happen on the UI thread, and sounds are loaded in full and
cached until scene replacement, so short demo assets work best. This demo does
not yet stream long recordings.

To convert a folder of WAV assets to Ogg Vorbis using SoundFile:

```powershell
.\.venv\Scripts\python.exe tools\convert_audio.py samples\wav samples\ogg
```

This preserves sample rates, channel counts and frame counts, keeps the WAVs,
and refuses to overwrite existing outputs. Ogg Vorbis compression is lossy.

Scenes save as versioned JSON. Audio paths are relative to the scene file when
possible, and absolute when on a different Windows drive. Scene JSON refers to
sound files; it does not embed them. Save/loading retains editable properties
and control points, but resets playback and path animation to their beginnings.
The player position is saved. Changes prompt for save before closing/replacing
a scene. Missing/corrupt audio reports a per-source error; other sounds continue.
Fix the path or press Replay / retry sound after fixing the file.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover arc-length movement, reversal and closed paths, JSON round trips and
invalid scenes, Qt drawing/vertex tools and keyboard focus, plus **real OpenAL
loopback rendering** for stereo panning, source/listener position and velocity,
effects, pause/resume, one-shots and range transitions. Loopback tests do not
play through the speakers. Perceptual headphone/HRTF listening remains a manual
check.

Code is split into `model.py` (data/motion/JSON), `audio.py` (OpenAL lifecycle and
mixing), `canvas.py` (map/tools), `inspector.py` (properties) and `app.py` (window,
timer and document actions). OpenAL stays on the creating Qt thread, with
explicit context activation and deterministic shutdown.
