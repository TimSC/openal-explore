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
    cone_inner: float = 360.0
    cone_outer: float = 360.0
    cone_gain: float = 0.0
    air_absorption: float = 0.0
    lowpass: bool = False
    lowpass_hf: float = 0.3
    reverb_send: bool = True
    phase: float = field(default=0.0, repr=False, metadata={"runtime": True})

    def sample(self):
        if self.kind == "point":
            return tuple(self.points[0]), (0.0, 0.0)
        pos, tangent = path_sample(self.points, self.phase, self.motion)
        return pos, tuple(v * self.speed if self.enabled else 0.0 for v in tangent)

    def reset(self):
        self.phase = 0.0


@dataclass
class Scene:
    player: Player = field(default_factory=Player)
    settings: Settings = field(default_factory=Settings)
    emitters: list[Emitter] = field(default_factory=list)

    def advance(self, dt: float):
        for e in self.emitters:
            if e.enabled and e.kind == "line":
                e.phase += e.speed * dt

    def find(self, identifier):
        return next((e for e in self.emitters if e.id == identifier), None)


def _construct(cls, data):
    if not isinstance(data, dict):
        raise ValueError(f"Expected a {cls.__name__} object")
    allowed = {f.name for f in fields(cls) if not f.metadata.get("runtime")}
    return cls(**{k: v for k, v in data.items() if k in allowed})


def _number(value, lo, hi, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{label} must be between {lo} and {hi}")


def validate(scene: Scene):
    for obj in [scene.player, scene.settings, *scene.emitters]:
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
    if s.distance_model not in {"NONE", "INVERSE", "INVERSE_CLAMPED", "LINEAR", "LINEAR_CLAMPED", "EXPONENT", "EXPONENT_CLAMPED"}:
        raise ValueError("Unknown distance model")
    ids = set()
    for e in scene.emitters:
        if not e.id or e.id in ids or e.id == "player":
            raise ValueError("Sound IDs must be unique")
        ids.add(e.id)
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
    data = {"version": 1, "player": asdict(scene.player), "settings": asdict(scene.settings), "emitters": emitters}
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
    validate(scene)
    for e in scene.emitters:
        if e.file:
            e.file = str((path.parent / e.file).resolve())
    return scene
