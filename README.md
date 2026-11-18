# OpenAL Explore

A PySide6 scene editor and spatial audio demo for [openal-py](https://github.com/TimSC/openal-py). The player stays
at the centre while the world scrolls. Audio comes from stationary points or
sources travelling along editable polylines.

## Run

Use Python 3.11 or newer. From the project directory, create and activate a
virtual environment, then install the project and its test dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python run.py
```

On Debian/Ubuntu, install `python3-venv` with `sudo apt install python3-venv`
if virtual environment creation is unavailable.

[`openal-py`](https://pypi.org/project/openal-py/) is available on PyPI and is
installed automatically with the project dependencies, alongside PySide6,
SoundFile and NumPy. Its platform wheels bundle OpenAL Soft, so a separate
system OpenAL installation is normally unnecessary.

On first run,
the demo generates three short mono WAV files in `samples/`: a pulsing beacon,
a chime, and an engine sound. It also places the available `samples/ogg/` files
around an outer ring of radius 65 metres, with locations approximately 40 metres
apart. Three travel back and forth along short 24-metre paths at 3–5 m/s; the
others stay stationary. Initial source volumes vary from 0.56 to 0.75.
Default source altitudes range from 0 to 15 metres, including low sources below
the listener and elevated sources overhead. Altitude remains editable for each source.
Each Ogg source has a 26-metre audible radius, so walk towards a source to hear
it without the whole collection playing at once. The central **Doppler fly-by**
travels at 45 m/s along a 70-metre path near the player. Three directional
speakers have narrow cones and visible arrows. The **Stone cave**, **Concert
hall**, and **Open air** rectangles demonstrate reverb environments.
**File → Load demo scene** restores this scene.

```bash
# Open a saved scene
python run.py scene.json

# Edit with no audio device, or start with an empty scene
python run.py --no-audio
python run.py --empty
```

These commands assume the virtual environment is active. In a new terminal,
run `source .venv/bin/activate` from the project directory first.

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
| 5 | Draw a rectangular reverb zone by dragging |
| Double-click a segment in Edit Vertices | Insert a control point |
| Delete / Backspace on map | Remove selected vertex, source, or reverb zone |
| Backspace while drawing | Undo the last draft vertex |
| Escape | Cancel drawing and return to Inspect |
| Right-click | Cancel the current draft |
| Space | Pause/resume audio, movement and path animation |
| Ctrl+0 | Fit the scene around the current player position |
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S | New / open / save / save as |

The toolbar buttons also work without keyboard shortcuts. Shortcuts 1–5 and
Space apply only to the map, so they do not interfere with entering properties.
**Restart** resets all path positions and replays sounds. **Replay / retry sound**
restarts just the selected sound without resetting its path.
The **Doppler** toolbar checkbox switches Doppler on/off while preserving the
configured factor. Compare the fast fly-by with the checkbox enabled/disabled;
use Restart to replay the same pass.

Select objects on the map or in **Scene objects**. The properties and object
panels can be moved, detached, closed, and reopened through **View**.
The **Vertices** inspector tab provides numeric editing and add/remove buttons.
Paths retain at least two control points. Closed-loop paths include a segment
from the last point back to the first; back-and-forth paths reverse at their ends.

**View → OpenAL information** (also under Help) opens a separate, read-only
window. Tabs show the wrapper/native library, vendor, renderer and version,
output device and attributes, HRTF/EFX capabilities, live listener/source state,
buffering statistics, and AL/ALC extension lists. It updates once per second
while open; Refresh updates immediately and Copy all copies a diagnostic report.
The window does not change scene or playback settings and also explains when
audio is disabled or unavailable.

## Sound properties

- File, enabled, looping (on by default), volume and pitch.
- Point coordinates, altitude, and live position/velocity/playback status.
- Line speed in metres per second, back-and-forth/closed-loop travel, and path-facing direction.
- Audible radius, reference distance, maximum distance and rolloff.
- Directional speaker checkbox, facing direction, inner/outer cone angles and outside-cone volume.
- EFX low-pass filtering, high-frequency gain, air absorption, and a reverb send.
- Auto/static/stream buffering, live buffered time and underrun count.
- Echo, chorus, flanger, distortion or equalizer, with live effect parameters and return volume.

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
Directional speaker arrows appear even when the source is not selected. The
direction follows the editable heading, or the current path segment when
**Face along path** is enabled. Disabling Directional speaker bypasses the cone
without losing its configured angles.

## Reverb zones and effects

Use **Reverb zone [5]** to drag a rectangular area. In Inspect mode, drag the
area to move it or drag a selected corner to resize it. Select a zone to edit
its bounds, name, enabled state, preset, volume, decay, high-frequency gain,
diffusion and edge blend distance. Cave, hall and outdoor presets provide
starting values. Zones extend through all altitudes.

Inside a zone its settings apply fully. Outside its border, its influence fades
over the edge blend distance. Overlapping zones blend in scene order, with the
last zone taking precedence. The audio controller also smooths changes over
**Player → Acoustics → Transition time**, avoiding abrupt changes as you move
or edit a zone. Outside all zones, the player's global reverb settings apply.
Disable **Enable reverb zones** to compare against the global environment.
The listener inspector reports the current environment.

**Sound → Effects → Effects playground** selects one additional effect for
that source. Return volume mixes the processed signal with the dry sound;
zero bypasses the return. Parameters update during playback. Room/zone reverb
and the additional source effect use separate auxiliary sends when the device
supports two sends. With one send, the source effect replaces reverb for that
source. Unsupported effects report their unavailability while dry playback
continues. Effects and reverb require EFX support.

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

[SoundFile](https://pypi.org/project/soundfile/) provides optional decoding to
openal-py through libsndfile. Mono/stereo WAV, FLAC, OGG and other installed
decoder formats can be selected. Static sounds use `Context.load(mono=True,
format=AudioFormat.MONO16)`, including the wrapper's SoundFile fallback for
24-bit and floating-point WAVs. Stereo channels are averaged to mono and
converted to PCM16 for positional playback; original files are unchanged.
**Buffering → Auto**
streams recordings longer than 10 seconds, including the ten supplied Ogg
samples. **Stream** forces streaming for any length; **Static** loads the whole
file and caches its OpenAL buffer until scene replacement.

Streaming uses `openal_py.StreamingSource.from_file(mono=True)` with four
8192-frame buffers. The wrapper owns the decoder and native source, and reuses
the same buffer pool through `Buffer.upload_pcm()` as the Qt timer calls
`stream.update()`. The demo sets spatial/effect properties on the exposed source
and controls playback through the helper. The
sound inspector shows queued audio time and underruns. A drained queue with
more audio available is restarted and counted as an underrun; natural one-shot
completion is not. Looping is handled by seeking the decoder, so it also works
for short streamed files. Disabling, leaving range, replaying or changing scenes
closes decoder handles and releases queued buffers. Changing buffering mode
restarts that sound. Underruns count over the source's playback session and reset
on Replay or file/mode changes. Buffered time and underruns come from the
helper's `buffered_duration` and `underrun_count` properties. Decoding and OpenAL calls stay on the Qt thread,
so a long UI stall can still cause an underrun; no hidden audio thread is used.

To convert a folder of WAV assets to Ogg Vorbis using SoundFile:

```bash
python tools/convert_audio.py samples/wav samples/ogg
```

This preserves sample rates, channel counts and frame counts, keeps the WAVs,
and refuses to overwrite existing outputs. Ogg Vorbis compression is lossy.

Scenes save as versioned JSON. Audio paths are relative to the scene file when
possible, and absolute otherwise. Scene JSON refers to
sound files; it does not embed them. Save/loading retains editable properties
and control points, but resets playback and path animation to their beginnings.
The player position is saved. Changes prompt for save before closing/replacing
a scene. Missing/corrupt audio reports a per-source error; other sounds continue.
Fix the path or press Replay / retry sound after fixing the file.

## Verification

```bash
python -m pytest -q
```

Tests cover arc-length movement, reversal and closed paths, JSON round trips and
invalid scenes, Qt drawing/vertex tools and keyboard focus, plus **real OpenAL
loopback rendering** for stereo panning, source/listener position and velocity,
all five playground effects, rendered cone attenuation and Doppler pitch,
reverb transitions, bounded streaming/looping, deliberate underrun recovery,
pause/resume, one-shots and range transitions. Qt tests also exercise zone drawing,
moving, resizing and presets. Integration checks verify reusable streaming
buffers, mono decoding, high-resolution WAV fallback, boolean capabilities,
and HRTF reset without losing the loopback output format. Loopback tests do not
play through the speakers. Perceptual headphone/HRTF listening remains a manual
check.

Code is split into `model.py` (data/motion/JSON), `audio.py` (OpenAL lifecycle and
mixing), `canvas.py` (map/tools), `inspector.py` (properties) and `app.py` (window,
timer and document actions). OpenAL stays on the creating Qt thread, with
explicit context activation and deterministic shutdown.

## OpenAL source extensions

Sound → Spatial includes optional per-source OpenAL extension controls. All
start off: distance model and resampler inherit their defaults, spatialization
uses OpenAL's automatic mode, source radius is zero, and latency queries are off.
Unsupported controls are disabled and identify their extension in the tooltip.

- `AL_EXT_source_distance_model`: override the global distance model for this
  source. Sources without an override continue to follow the global setting.
- `AL_SOFT_source_resampler`: select a device-provided resampler by index.
  Indices are implementation-specific; unavailable saved indices use the default.
- `AL_SOFT_source_spatialize`: force spatialization on or off. Off here means
  disabling the override; select **Force off** to disable spatialization itself.
- `AL_EXT_SOURCE_RADIUS`: set the physical emitter radius in metres, independently
  of the application's audible cutoff radius.
- `AL_SOFT_source_latency`: opt into live output latency and playback-offset
  telemetry for the active source. This is separate from queued buffer duration.

These settings are saved with the scene; older scenes retain the default behavior.
