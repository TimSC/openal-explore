"""OpenAL resources stay on the Qt thread; QTimer drives update(), never wait()."""
from __future__ import annotations

from dataclasses import astuple, dataclass, field
import math
from pathlib import Path

from .model import Scene, direction
from .effect_specs import EFFECTS


@dataclass
class Playback:
    source: object = None
    filter: object = None
    file: str = ""
    config: tuple = ()
    finished: bool = False
    paused: bool = False
    error: str = ""
    state: str = "Ready"
    mode: str = "auto"
    streaming: bool = False
    reader: object = None
    chunks: list = field(default_factory=list)
    eof: bool = False
    buffered: float = 0.0
    underruns: int = 0
    fx: object = None
    fx_slot: object = None
    fx_type: str = "NONE"
    fx_key: tuple = ()
    effect_message: str = ""


class Audio:
    def __init__(self, device=None, enabled=True):
        self.device = self.context = None
        self.owns_device = device is None
        self.available = False
        self.efx = self.hrtf = False
        self.error = ""
        self.info = ""
        self.playbacks: dict[str, Playback] = {}
        self.buffers = {}
        self.settings_key = None
        self.effect = self.slot = None
        self.hrtf_actual = "Unavailable"
        self.effect_sends = 0
        self.reverb_state = None
        self.reverb_key = None
        self.zone_name = "Outside zones"
        self.unsupported_effects = {}
        if not enabled:
            self.error = "Audio disabled (--no-audio)"
            return
        try:
            import openal_py as al
            self.al = al
            self.device = device if device is not None else al.Device.open()
            attributes = {"ALC_MAX_AUXILIARY_SENDS": 2} if self.device.supports("ALC_EXT_EFX") else None
            try:
                self.context = self.device.create_context(attributes=attributes)
            except al.ALCError:
                if attributes is None:
                    raise
                self.context = self.device.create_context()
            with self.context.activate() as ctx:
                self.efx = self.device.supports("ALC_EXT_EFX")
                self.hrtf = self.device.supports("ALC_SOFT_HRTF")
                self.info = f"{ctx.renderer} · {self.device.spec}"
                if self.efx:
                    try:
                        self.effect = ctx.create_effect(al.EffectType.REVERB)
                        self.slot = ctx.create_effect_slot(effect=self.effect, gain=0)
                        self.effect_sends = self.device.get_parameter("ALC_MAX_AUXILIARY_SENDS")
                    except Exception:
                        self.efx = False
                self.available = True
        except Exception as exc:
            self.error = f"Audio unavailable: {exc}"
            self.close()

    def _load(self, filename):
        import soundfile as sf
        path = Path(filename).resolve()
        stat = path.stat()
        key = str(path), stat.st_mtime_ns, stat.st_size
        if key not in self.buffers:
            data, rate = sf.read(path, dtype="float32", always_2d=True)
            if not len(data):
                raise ValueError("The audio file is empty")
            # OpenAL spatializes mono buffers. Explicit downmix also handles stereo assets.
            self.buffers[key] = self.context.buffer_from_pcm(
                self._pcm(data), format=self.al.AudioFormat.MONO16, sample_rate=rate)
        return self.buffers[key]

    @staticmethod
    def _pcm(data):
        import numpy as np
        mono = np.nan_to_num(data.mean(axis=1), nan=0.0, posinf=1.0, neginf=-1.0)
        return (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()

    @staticmethod
    def _release(p):
        if p.source is not None:
            p.source.close()
            p.source = None
        if p.filter is not None:
            p.filter.close()
            p.filter = None
        for chunk in p.chunks:
            chunk.close()
        p.chunks.clear()
        if p.reader is not None:
            p.reader.close()
            p.reader = None
        if p.fx_slot is not None:
            p.fx_slot.close()
            p.fx_slot = None
        if p.fx is not None:
            p.fx.close()
            p.fx = None
        p.fx_type, p.fx_key = "NONE", ()
        p.buffered = 0.0
        p.config = ()
        p.paused = False

    def reset(self):
        if self.context is not None and not self.context.closed:
            with self.context.activate():
                for p in self.playbacks.values():
                    self._release(p)
                for b in self.buffers.values():
                    b.close()
        self.playbacks.clear()
        self.buffers.clear()
        self.settings_key = None
        self.reverb_state = self.reverb_key = None
        self.zone_name = "Outside zones"

    def restart(self, identifier=None):
        identifiers = list(self.playbacks) if identifier is None else [identifier]
        if self.available:
            with self.context.activate():
                for key in identifiers:
                    p = self.playbacks.pop(key, None)
                    if p:
                        self._release(p)

    def _settings(self, s):
        key = astuple(s)
        if key == self.settings_key:
            return
        ctx = self.context
        ctx.distance_model = getattr(self.al.DistanceModel, s.distance_model)
        ctx.doppler_factor = s.doppler if s.doppler_enabled else 0.0
        ctx.speed_of_sound = s.speed_of_sound
        ctx.listener.gain = s.volume
        if self.hrtf:
            try:
                if self.device.hrtf_enabled != s.hrtf:
                    self.device.reset(hrtf=s.hrtf)
                self.hrtf_actual = self.device.hrtf_status.name.replace("_", " ").title()
            except Exception as exc:
                # Some outputs advertise the extension but cannot reset (e.g. loopback).
                # An optional rendering feature must not stop all scene playback.
                self.hrtf = False
                self.hrtf_actual = f"Request unavailable: {exc}"
        self.settings_key = key

    def _reverb(self, scene, dt):
        target, self.zone_name = scene.reverb_target()
        if not self.efx:
            return
        if self.reverb_state is None:
            self.reverb_state = target.copy()
        alpha = 1 - math.exp(-max(0.0, dt) / scene.settings.transition_time)
        for key, value in target.items():
            self.reverb_state[key] += (value - self.reverb_state[key]) * alpha
        state = self.reverb_state
        key = tuple(round(state[k], 3) for k in ("decay", "gain_hf", "diffusion"))
        if key != self.reverb_key:
            for name, value in zip(("decay_time", "gain_hf", "diffusion"), key):
                self.effect.parameters[name] = value
            self.slot.refresh()
            self.reverb_key = key
        self.slot.gain = state["wet"]

    def _source_effect(self, e, p):
        requested = e.effect_type
        if requested != p.fx_type:
            p.source.set_send(1 if self.effect_sends >= 2 else 0, None)
            if p.fx_slot is not None:
                p.fx_slot.close()
                p.fx_slot = None
            if p.fx is not None:
                p.fx.close()
                p.fx = None
            p.fx_key, p.effect_message = (), ""
            p.fx_type = requested
            if requested != "NONE":
                try:
                    p.fx = self.context.create_effect(getattr(self.al.EffectType, requested))
                    p.fx_slot = self.context.create_effect_slot(effect=p.fx, gain=e.effect_gain)
                except Exception as exc:
                    p.effect_message = f"{requested.title()} unavailable: {exc}"
                    self.unsupported_effects[requested] = p.effect_message
                    if p.fx is not None:
                        p.fx.close()
                        p.fx = None
        if p.fx_slot is not None:
            values = {name: e.effect_params.get(name, spec[3]) for name, spec in EFFECTS[requested].items()}
            key = tuple(sorted(values.items()))
            if key != p.fx_key:
                for name, value in values.items():
                    p.fx.parameters[name] = value
                p.fx_slot.refresh()
                p.fx_key = key
            p.fx_slot.gain = e.effect_gain
            p.source.set_send(1 if self.effect_sends >= 2 else 0, p.fx_slot)
        if self.effect_sends >= 2 or p.fx_slot is None:
            p.source.set_send(0, self.slot if e.reverb_send else None)

    def _chunk(self, e, p):
        data = p.reader.read(8192, dtype="float32", always_2d=True)
        if not len(data) and e.looping:
            p.reader.seek(0)
            data = p.reader.read(8192, dtype="float32", always_2d=True)
        if not len(data):
            p.eof = True
            return None
        return self.context.buffer_from_pcm(self._pcm(data), format=self.al.AudioFormat.MONO16,
                                            sample_rate=p.reader.samplerate)

    def _fill(self, e, p):
        if p.eof and e.looping:
            p.eof = False
            p.reader.seek(0)
        while len(p.chunks) < 4 and not p.eof:
            chunk = self._chunk(e, p)
            if chunk is not None:
                p.chunks.append(chunk)
                p.source.queue_buffers([chunk])

    def _create_source(self, e, p):
        import soundfile as sf
        p.streaming = e.playback_mode == "stream" or (e.playback_mode == "auto" and sf.info(e.file).duration > 10)
        if p.streaming:
            p.reader = sf.SoundFile(e.file)
            if p.reader.frames == 0:
                raise ValueError("The audio file is empty")
            p.eof = False
            p.source = self.context.create_source()
            self._fill(e, p)
        else:
            p.source = self.context.create_source(buffer=self._load(e.file))

    def _pump(self, e, p, paused):
        stopped = p.source.state == self.al.SourceState.STOPPED
        for chunk in p.source.unqueue_buffers():
            p.chunks.remove(chunk)
            chunk.close()
        self._fill(e, p)
        if stopped and p.chunks and not paused and not p.paused:
            p.underruns += 1
            p.source.play()
        p.buffered = max(0, sum(c.duration for c in p.chunks) - p.source.offset_seconds)

    def _configure(self, e, p):
        key = (e.gain, e.pitch, e.looping, e.reference_distance, e.max_distance, e.rolloff,
               e.cone_inner, e.cone_outer, e.cone_gain, e.air_absorption, e.lowpass,
               e.lowpass_hf, e.reverb_send, e.directional, p.streaming,
               e.effect_type, e.effect_gain, tuple(sorted(e.effect_params.items())))
        if p.config == key:
            return
        src = p.source
        src.gain, src.pitch, src.looping = e.gain, e.pitch, e.looping and not p.streaming
        src.reference_distance, src.max_distance, src.rolloff_factor = e.reference_distance, e.max_distance, e.rolloff
        src.cone_inner_angle = e.cone_inner if e.directional else 360.0
        src.cone_outer_angle = e.cone_outer if e.directional else 360.0
        src.cone_outer_gain = e.cone_gain
        if self.efx:
            src.air_absorption_factor = e.air_absorption
            if e.lowpass:
                if p.filter is None:
                    p.filter = self.context.create_filter(self.al.FilterType.LOWPASS)
                p.filter.parameters["gain_hf"] = e.lowpass_hf
                src.direct_filter = p.filter
            else:
                src.direct_filter = None
            self._source_effect(e, p)
        p.config = key

    def update(self, scene: Scene, velocity=(0.0, 0.0), paused=False, dt=1 / 60):
        if not self.available:
            return
        try:
            with self.context.activate() as ctx:
                self._settings(scene.settings)
                self._reverb(scene, dt)
                player = scene.player
                listener = ctx.listener
                listener.position = (player.x, player.altitude, -player.y)
                listener.velocity = (velocity[0], 0, -velocity[1]) if not paused else (0, 0, 0)
                dx, dy = direction(player.heading)
                listener.direction, listener.up = (dx, 0, -dy), (0, 1, 0)
                ids = {e.id for e in scene.emitters}
                for key in list(self.playbacks):
                    if key not in ids:
                        self._release(self.playbacks.pop(key))
                for e in scene.emitters:
                    self._update_emitter(e, player, paused)
            self.error = ""
        except Exception as exc:
            self.error = f"Audio update: {exc}"

    def _update_emitter(self, e, player, paused):
        p = self.playbacks.setdefault(e.id, Playback())
        if p.file != e.file or p.mode != e.playback_mode:
            self._release(p)
            p.file, p.finished, p.error = e.file, False, ""
            p.mode, p.underruns = e.playback_mode, 0
        position, velocity = e.sample()
        distance = math.sqrt((position[0] - player.x)**2 + (position[1] - player.y)**2 +
                             (e.altitude - player.altitude)**2)
        state = "Disabled" if not e.enabled else "No file" if not e.file else "Out of range" if distance > e.radius else ""
        if state:
            self._release(p)
            p.finished, p.state = False, state
            return
        if p.error:
            p.state = "Error: " + p.error
            return
        if p.finished:
            if e.looping:
                p.finished = False
            else:
                p.state = "Finished · Replay to retrigger"
                return
        try:
            if p.source is None:
                if paused:
                    p.state = "Paused"
                    return
                self._create_source(e, p)
                self._configure(e, p)
                self._position(e, p.source, position, velocity, paused)
                p.source.play()
            else:
                self._configure(e, p)
                self._position(e, p.source, position, velocity, paused)
            src = p.source
            if p.streaming:
                self._pump(e, p, paused)
            if paused:
                if src.state == self.al.SourceState.PLAYING:
                    src.pause()
                    p.paused = True
                p.state = "Paused"
            elif p.paused:
                src.play()
                p.paused = False
                p.state = "Playing"
            elif src.state == self.al.SourceState.STOPPED:
                p.finished = True
                p.state = "Finished · Replay to retrigger"
                self._release(p)
            else:
                p.state = "Playing"
        except Exception as exc:
            self._release(p)
            p.error = str(exc)
            p.state = "Error: " + p.error

    @staticmethod
    def _position(e, src, position, velocity, paused):
        src.position = (position[0], e.altitude, -position[1])
        src.velocity = (velocity[0], 0, -velocity[1]) if not paused else (0, 0, 0)
        dx, dy = direction(e.facing())
        src.direction = (dx, 0, -dy)

    def state(self, identifier):
        p = self.playbacks.get(identifier)
        return p.state if p else "Ready" if self.available else "Audio unavailable"

    def stream_info(self, identifier):
        p = self.playbacks.get(identifier)
        if p is None or p.source is None:
            return "Waiting for playback"
        if p.streaming:
            return f"Streaming · {p.buffered:.2f} s buffered · {p.underruns} underruns"
        return "Static · file fully buffered"

    def diagnostics(self, scene=None):
        """Read native state without changing playback, settings, or resources."""
        sections = {"Overview": "", "Listener": "", "Sources": "", "AL extensions": "", "ALC extensions": ""}
        if not self.available or self.context is None or self.device is None:
            sections["Overview"] = self.error or "Audio is not running."
            for title in sections:
                if title != "Overview":
                    sections[title] = "Unavailable while audio is not running."
            return sections

        def read(label, getter):
            try:
                value = getter()
                if value is None or value == "":
                    value = "Not set"
                return f"{label}: {value}"
            except Exception as exc:
                return f"{label}: Unavailable ({exc})"

        try:
            with self.context.activate() as ctx:
                device = self.device
                lines = [
                    "Audio is running.",
                    read("openal-py version", lambda: self.al.__version__),
                    read("Native library", self.al.library_path),
                    read("Vendor", lambda: ctx.vendor),
                    read("Renderer", lambda: ctx.renderer),
                    read("OpenAL version", lambda: ctx.version),
                    read("ALC version", lambda: ".".join(map(str, device.version))),
                    read("Output device", lambda: device.spec),
                    f"EFX available: {bool(self.efx)}",
                    f"Auxiliary sends per source: {self.effect_sends}",
                    read("HRTF extension", lambda: bool(device.supports("ALC_SOFT_HRTF"))),
                    f"HRTF request status: {self.hrtf_actual}",
                ]
                if device.supports("ALC_SOFT_HRTF"):
                    lines += [read("HRTF enabled", lambda: device.hrtf_enabled),
                              read("HRTF device status", lambda: device.hrtf_status.name),
                              read("HRTF profile", lambda: device.hrtf_name),
                              read("Available HRTF profiles", lambda: ", ".join(device.hrtf_names))]
                lines += ["", "Device attributes", read("Values", lambda: "\n".join(
                    f"  {name}: {value}" for name, value in sorted(device.attributes.items())))]
                if device.supports("ALC_SOFT_device_clock"):
                    lines.append(read("Output latency (ms)", lambda: round(device.timing.latency_ns / 1e6, 3)))
                if self.error:
                    lines += ["", self.error]
                sections["Overview"] = "\n".join(lines)

                listener = ctx.listener
                sections["Listener"] = "\n".join([
                    "Native OpenAL coordinates: X east, Y altitude, Z south.", "",
                    read("Position (m)", lambda: listener.position),
                    read("Velocity (m/s)", lambda: listener.velocity),
                    read("Facing direction", lambda: listener.direction),
                    read("Up direction", lambda: listener.up),
                    read("Master gain", lambda: listener.gain),
                    read("Distance model", lambda: ctx.distance_model.name),
                    read("Doppler factor", lambda: ctx.doppler_factor),
                    read("Speed of sound (m/s)", lambda: ctx.speed_of_sound),
                    f"Current environment: {self.zone_name}",
                ])
                active = sum(p.source is not None for p in self.playbacks.values())
                lines = [f"Active native sources: {active}", f"Cached static buffers: {len(self.buffers)}", ""]
                for identifier, p in self.playbacks.items():
                    emitter = scene.find(identifier) if scene is not None else None
                    lines += [emitter.name if emitter else identifier, f"  Playback: {p.state}"]
                    if p.source is not None:
                        src = p.source
                        lines += ["  " + read("Native state", lambda: src.state.name),
                                  "  " + read("Source type", lambda: src.source_type.name),
                                  "  " + read("Position (m)", lambda: src.position),
                                  "  " + read("Velocity (m/s)", lambda: src.velocity),
                                  "  " + read("Direction", lambda: src.direction),
                                  "  " + read("Gain", lambda: src.gain),
                                  "  " + read("Pitch", lambda: src.pitch),
                                  "  " + read("Playback offset (s)", lambda: round(src.offset_seconds, 3)),
                                  "  " + self.stream_info(identifier)]
                        if p.streaming:
                            lines += ["  " + read("Queued buffers", lambda: src.buffers_queued),
                                      "  " + read("Processed buffers", lambda: src.buffers_processed)]
                    lines.append("")
                sections["Sources"] = "\n".join(lines)
                sections["AL extensions"] = read("Supported AL extensions", lambda: "\n" + "\n".join(sorted(ctx.extensions)))
                sections["ALC extensions"] = read("Supported ALC extensions", lambda: "\n" + "\n".join(sorted(device.extensions)))
        except Exception as exc:
            sections["Overview"] = f"OpenAL information unavailable: {exc}"
        return sections

    def close(self):
        try:
            self.reset()
        finally:
            if self.context is not None:
                self.context.close()
                self.context = None
            if self.device is not None and self.owns_device:
                self.device.close()
            self.device = None
            self.available = False
