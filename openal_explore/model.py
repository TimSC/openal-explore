"""Scene data and path motion, independent of Qt and OpenAL.

World coordinates: X east, Y north, altitude up. One unit is one metre.
Headings are degrees clockwise from north. OpenAL uses (X, altitude, -Y).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import math
import os
from pathlib import Path
import uuid

from .effect_specs import EFFECTS, ZONE_PRESETS


def direction(heading: float) -> tuple[float, float]:
    a = math.radians(heading)
    return math.sin(a), math.cos(a)


def path_sample(points, distance: float, mode: str = "pingpong"):
    """Return position and unit tangent at travelled distance, including reversals."""
    if not points:
        return (0.0, 0.0), (0.0, 0.0)
    segments = list(zip(points, points[1:]))
    if mode == "loop" and len(points) > 1:
        segments.append((points[-1], points[0]))
    segments = [(a, b, math.dist(a, b)) for a, b in segments if math.dist(a, b) > 1e-9]
    length = sum(s[2] for s in segments)
    if not segments:
        return tuple(points[0]), (0.0, 0.0)
    sign = 1
    if mode == "pingpong":
        distance %= 2 * length
        if distance >= length:
            distance = 2 * length - distance
            sign = -1
    else:
        distance %= length
    for a, b, size in segments:
        if distance <= size:
            t = distance / size
            return ((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t),
                    (sign * (b[0] - a[0]) / size, sign * (b[1] - a[1]) / size))
        distance -= size
    return tuple(segments[-1][1]), (0.0, 0.0)


@dataclass
class Player:
    x: float = 0.0
    y: float = 0.0
    altitude: float = 1.7
    heading: float = 0.0
    speed: float = 6.0


@dataclass
class Settings:
    volume: float = 0.5
    distance_model: str = "INVERSE_CLAMPED"
    doppler: float = 1.0
    speed_of_sound: float = 343.3
    hrtf: bool = False
    reverb: bool = False
    reverb_gain: float = 0.25
    reverb_decay: float = 1.5
    doppler_enabled: bool = True
    zones_enabled: bool = True
    transition_time: float = 1.0


@dataclass
class ReverbZone:
    name: str = "Reverb zone"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    x: float = 0.0
    y: float = 0.0
    width: float = 20.0
    height: float = 20.0
    enabled: bool = True
    preset: str = "hall"
    wet: float = 0.35
    decay: float = 2.4
    gain_hf: float = 0.8
    diffusion: float = 0.9
    fade: float = 5.0

    def apply_preset(self, preset):
        self.preset = preset
        for key, value in ZONE_PRESETS[preset].items():
            setattr(self, key, value)

    def weight(self, x, y):
        if not self.enabled:
            return 0.0
        distance = math.hypot(max(self.x - x, 0, x - self.x - self.width),
                              max(self.y - y, 0, y - self.y - self.height))
        if distance == 0:
            return 1.0
        t = max(0.0, 1 - distance / self.fade) if self.fade > 0 else 0.0
        return t * t * (3 - 2 * t)


@dataclass
class Emitter:
    name: str = "Sound"
    kind: str = "point"
    points: list[list[float]] = field(default_factory=lambda: [[0.0, 0.0]])
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    file: str = ""
    enabled: bool = True
    looping: bool = True
    gain: float = 0.7
    pitch: float = 1.0
    altitude: float = 0.0
    radius: float = 45.0
    reference_distance: float = 2.0
    max_distance: float = 40.0
    rolloff: float = 1.0
    speed: float = 5.0
    motion: str = "pingpong"
    heading: float = 0.0
    follow_path: bool = True
    cone_inner: float = 60.0
    cone_outer: float = 120.0
    cone_gain: float = 0.0
    air_absorption: float = 0.0
    lowpass: bool = False
    lowpass_hf: float = 0.3
    reverb_send: bool = True
    directional: bool = False
    source_distance_model: str = "DEFAULT"
    source_resampler: int = -1
    source_spatialize: str = "DEFAULT"
    source_radius: float = 0.0
    show_latency: bool = False
    playback_mode: str = "auto"
    effect_type: str = "NONE"
    effect_gain: float = 0.35
    effect_params: dict[str, float] = field(default_factory=dict)
    phase: float = field(default=0.0, repr=False, metadata={"runtime": True})

    def sample(self):
        if self.kind == "point":
            return tuple(self.points[0]), (0.0, 0.0)
        pos, tangent = path_sample(self.points, self.phase, self.motion)
        return pos, tuple(v * self.speed if self.enabled else 0.0 for v in tangent)

    def reset(self):
        self.phase = 0.0

    def facing(self):
        if self.kind == "line" and self.follow_path:
            _, tangent = path_sample(self.points, self.phase, self.motion)
            if any(tangent):
                return math.degrees(math.atan2(tangent[0], tangent[1]))
        return self.heading


@dataclass
class Scene:
    player: Player = field(default_factory=Player)
    settings: Settings = field(default_factory=Settings)
    emitters: list[Emitter] = field(default_factory=list)
    zones: list[ReverbZone] = field(default_factory=list)

    def advance(self, dt: float):
        for e in self.emitters:
            if e.enabled and e.kind == "line":
                e.phase += e.speed * dt

    def find(self, identifier):
        return next((e for e in self.emitters if e.id == identifier), None)

    def find_zone(self, identifier):
        return next((z for z in self.zones if z.id == identifier), None)

    def reverb_target(self):
        s = self.settings
        result = {"wet": s.reverb_gain if s.reverb else 0.0, "decay": s.reverb_decay,
                  "gain_hf": 0.83, "diffusion": 1.0}
        name = "Global reverb" if s.reverb else "Outside zones"
        if s.zones_enabled:
            for zone in self.zones:  # Last drawn zone has priority where zones overlap.
                weight = zone.weight(self.player.x, self.player.y)
                if weight:
                    result = {k: value + (getattr(zone, k) - value) * weight for k, value in result.items()}
                    name = zone.name
        return result, name


def _construct(cls, data):
    if not isinstance(data, dict):
        raise ValueError(f"Expected a {cls.__name__} object")
    allowed = {f.name for f in fields(cls) if not f.metadata.get("runtime")}
    return cls(**{k: v for k, v in data.items() if k in allowed})


def _number(value, lo, hi, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{label} must be between {lo} and {hi}")


def validate(scene: Scene):
    for obj in [scene.player, scene.settings, *scene.emitters, *scene.zones]:
        defaults = type(obj)()
        for f in fields(obj):
            if f.metadata.get("runtime"):
                continue
            value, default = getattr(obj, f.name), getattr(defaults, f.name)
            if isinstance(default, bool) and type(value) is not bool:
                raise ValueError(f"{f.name} must be a checkbox value")
            if isinstance(default, float):
                _number(value, -1e6, 1e6, f.name)
            if isinstance(default, str) and not isinstance(value, str):
                raise ValueError(f"{f.name} must be text")
    _number(scene.player.speed, 0, 100, "Player speed")
    s = scene.settings
    _number(s.volume, 0, 1, "Master volume")
    _number(s.doppler, 0, 10, "Doppler factor")
    _number(s.speed_of_sound, 10, 10000, "Speed of sound")
    _number(s.reverb_gain, 0, 1, "Reverb gain")
    _number(s.reverb_decay, 0.1, 20, "Reverb decay")
    _number(s.transition_time, 0.05, 10, "Zone transition time")
    if s.distance_model not in {"NONE", "INVERSE", "INVERSE_CLAMPED", "LINEAR", "LINEAR_CLAMPED", "EXPONENT", "EXPONENT_CLAMPED"}:
        raise ValueError("Unknown distance model")
    ids = set()
    for e in scene.emitters:
        if not e.id or e.id in ids or e.id == "player":
            raise ValueError("Sound IDs must be unique")
        ids.add(e.id)
        if e.playback_mode not in ("auto", "static", "stream") or e.effect_type not in {"NONE", *EFFECTS}:
            raise ValueError("Unknown playback mode or effect")
        if e.source_distance_model not in {"DEFAULT", "NONE", "INVERSE", "INVERSE_CLAMPED", "LINEAR", "LINEAR_CLAMPED", "EXPONENT", "EXPONENT_CLAMPED"}:
            raise ValueError("Unknown source distance model")
        if e.source_spatialize not in {"DEFAULT", "OFF", "ON"}:
            raise ValueError("Unknown source spatialization mode")
        if type(e.source_resampler) is not int or e.source_resampler < -1:
            raise ValueError("Invalid source resampler")
        if type(e.show_latency) is not bool:
            raise ValueError("Invalid latency toggle")
        _number(e.source_radius, 0, 10000, "Source radius")
        _number(e.effect_gain, 0, 1, "Effect return volume")
        if not isinstance(e.effect_params, dict):
            raise ValueError("Effect parameters must be an object")
        for key, value in e.effect_params.items():
            schema = EFFECTS.get(e.effect_type, {})
            if key not in schema:
                raise ValueError(f"Unknown effect parameter: {key}")
            _, lo, hi, _, _ = schema[key]
            _number(value, lo, hi, key)
        if e.kind not in ("point", "line") or e.motion not in ("pingpong", "loop"):
            raise ValueError("Unknown sound or path type")
        if not isinstance(e.points, list) or not (1 <= len(e.points) <= 10000):
            raise ValueError("Invalid path points")
        if (e.kind == "line" and len(e.points) < 2) or (e.kind == "point" and len(e.points) != 1):
            raise ValueError("Points need one position; lines need at least two")
        for p in e.points:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise ValueError("Expected X/Y pairs")
            for v in p:
                _number(v, -1e6, 1e6, "Coordinate")
        for key, lo, hi in [("gain", 0, 4), ("pitch", 0.1, 4), ("radius", 0.1, 10000),
                            ("reference_distance", 0.01, 10000), ("max_distance", 0.02, 10000),
                            ("rolloff", 0, 10), ("speed", 0, 100), ("cone_inner", 0, 360),
                            ("cone_outer", 0, 360), ("cone_gain", 0, 1),
                            ("air_absorption", 0, 10), ("lowpass_hf", 0, 1)]:
            _number(getattr(e, key), lo, hi, key)
        if e.max_distance <= e.reference_distance or e.cone_inner > e.cone_outer:
            raise ValueError("Max distance must exceed reference distance; outer cone must contain inner cone")
    for z in scene.zones:
        if not z.id or z.id in ids or z.id == "player":
            raise ValueError("Zone and sound IDs must be unique")
        ids.add(z.id)
        if z.preset not in ZONE_PRESETS:
            raise ValueError("Unknown zone preset")
        for key, lo, hi in [("width", 0.1, 10000), ("height", 0.1, 10000), ("wet", 0, 1),
                            ("decay", 0.1, 20), ("gain_hf", 0, 1), ("diffusion", 0, 1), ("fade", 0, 100)]:
            _number(getattr(z, key), lo, hi, key)


def save_scene(scene: Scene, path: Path):
    validate(scene)
    path = Path(path).resolve()
    emitters = []
    for e in scene.emitters:
        data = {f.name: getattr(e, f.name) for f in fields(e) if not f.metadata.get("runtime")}
        if e.file:
            try:
                data["file"] = os.path.relpath(Path(e.file).resolve(), path.parent)
            except ValueError:  # A sound on a different Windows drive stays absolute.
                pass
        emitters.append(data)
    data = {"version": 1, "player": asdict(scene.player), "settings": asdict(scene.settings),
            "emitters": emitters, "zones": [asdict(z) for z in scene.zones]}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def load_scene(path: Path) -> Scene:
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported scene version")
    raw = data.get("emitters", [])
    if not isinstance(raw, list) or len(raw) > 512:
        raise ValueError("Scenes support at most 512 sounds")
    scene = Scene(_construct(Player, data.get("player", {})), _construct(Settings, data.get("settings", {})),
                  [_construct(Emitter, e) for e in raw])
    zones = data.get("zones", [])
    if not isinstance(zones, list) or len(zones) > 256:
        raise ValueError("Scenes support at most 256 reverb zones")
    scene.zones = [_construct(ReverbZone, z) for z in zones]
    for emitter, original in zip(scene.emitters, raw):
        if "directional" not in original:
            emitter.directional = original.get("cone_inner", 360) < 360 or original.get("cone_outer", 360) < 360
    validate(scene)
    for e in scene.emitters:
        if e.file:
            e.file = str((path.parent / e.file).resolve())
    return scene
