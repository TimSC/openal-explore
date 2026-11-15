"""OpenAL resources stay on the Qt thread; QTimer drives update(), never wait()."""
from __future__ import annotations

from dataclasses import astuple, dataclass
import math
from pathlib import Path

from .model import Scene, direction


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
        if not enabled:
            self.error = "Audio disabled (--no-audio)"
            return
        try:
            import openal_py as al
            self.al = al
            self.device = device if device is not None else al.Device.open()
            self.context = self.device.create_context()
            with self.context.activate() as ctx:
                self.efx = self.device.supports("ALC_EXT_EFX")
                self.hrtf = self.device.supports("ALC_SOFT_HRTF")
                self.info = f"{ctx.renderer} · {self.device.spec}"
                if self.efx:
                    try:
                        self.effect = ctx.create_effect(al.EffectType.REVERB)
                        self.slot = ctx.create_effect_slot(effect=self.effect, gain=0)
                    except Exception:
                        self.efx = False
                self.available = True
        except Exception as exc:
            self.error = f"Audio unavailable: {exc}"
            self.close()

    def _load(self, filename):
        import numpy as np
        import soundfile as sf
        path = Path(filename).resolve()
        stat = path.stat()
        key = str(path), stat.st_mtime_ns, stat.st_size
        if key not in self.buffers:
            data, rate = sf.read(path, dtype="float32", always_2d=True)
            if not len(data):
                raise ValueError("The audio file is empty")
            # OpenAL spatializes mono buffers. Explicit downmix also handles stereo assets.
            mono = np.nan_to_num(data.mean(axis=1), nan=0.0, posinf=1.0, neginf=-1.0)
            pcm = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
            self.buffers[key] = self.context.buffer_from_pcm(
                pcm.tobytes(), format=self.al.AudioFormat.MONO16, sample_rate=rate)
        return self.buffers[key]

    @staticmethod
    def _release(p):
        if p.source is not None:
            p.source.close()
            p.source = None
        if p.filter is not None:
            p.filter.close()
            p.filter = None
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
        ctx.doppler_factor = s.doppler
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
        if self.efx:
            self.effect.parameters["decay_time"] = s.reverb_decay
            self.slot.refresh()
            self.slot.gain = s.reverb_gain if s.reverb else 0.0
        self.settings_key = key

    def _configure(self, e, p):
        key = (e.gain, e.pitch, e.looping, e.reference_distance, e.max_distance, e.rolloff,
               e.cone_inner, e.cone_outer, e.cone_gain, e.air_absorption, e.lowpass,
               e.lowpass_hf, e.reverb_send)
        if p.config == key:
            return
        src = p.source
        src.gain, src.pitch, src.looping = e.gain, e.pitch, e.looping
        src.reference_distance, src.max_distance, src.rolloff_factor = e.reference_distance, e.max_distance, e.rolloff
        src.cone_inner_angle, src.cone_outer_angle, src.cone_outer_gain = e.cone_inner, e.cone_outer, e.cone_gain
        if self.efx:
            src.air_absorption_factor = e.air_absorption
            if e.lowpass:
                if p.filter is None:
                    p.filter = self.context.create_filter(self.al.FilterType.LOWPASS)
                p.filter.parameters["gain_hf"] = e.lowpass_hf
                src.direct_filter = p.filter
            else:
                src.direct_filter = None
            src.set_send(0, self.slot if e.reverb_send else None)
        p.config = key

    def update(self, scene: Scene, velocity=(0.0, 0.0), paused=False):
        if not self.available:
            return
        try:
            with self.context.activate() as ctx:
                self._settings(scene.settings)
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
        if p.file != e.file:
            self._release(p)
            p.file, p.finished, p.error = e.file, False, ""
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
                p.source = self.context.create_source(buffer=self._load(e.file))
                self._configure(e, p)
                self._position(e, p.source, position, velocity, paused)
                p.source.play()
            else:
                self._configure(e, p)
                self._position(e, p.source, position, velocity, paused)
            src = p.source
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
        dx, dy = velocity if e.kind == "line" and e.follow_path and any(velocity) else direction(e.heading)
        src.direction = (dx, 0, -dy)

    def state(self, identifier):
        p = self.playbacks.get(identifier)
        return p.state if p else "Ready" if self.available else "Audio unavailable"

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
