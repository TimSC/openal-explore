"""Generated sounds near the player, with an outer ring of available Ogg samples."""
from pathlib import Path
import math
import random
import struct
import wave

from .model import Emitter, ReverbZone, Scene
from .effect_specs import ZONE_PRESETS


def create_demo(folder: Path) -> Scene:
    folder.mkdir(parents=True, exist_ok=True)
    rate = 22050
    randomizer = random.Random(42)
    for name in ("beacon", "engine", "chime"):
        path = folder / f"{name}.wav"
        if path.exists():
            continue
        samples = []
        for i in range(rate * 4):
            t = i / rate
            if name == "beacon":
                pulse = max(0, math.sin(2 * math.pi * 2 * t)) ** 8
                v = 0.5 * pulse * math.sin(2 * math.pi * 660 * t)
            elif name == "engine":
                v = (0.20 * math.sin(2 * math.pi * 90 * t) +
                     0.12 * math.sin(2 * math.pi * 180 * t) + 0.04 * randomizer.uniform(-1, 1))
            else:
                phase = t % 1
                envelope = math.exp(-phase * 7) * min(1, phase * 100)
                v = 0.4 * envelope * (math.sin(2 * math.pi * 440 * t) +
                                      0.3 * math.sin(2 * math.pi * 880 * t))
            samples.append(int(v * 32767))
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    scene = Scene(emitters=[
        Emitter(name="Beacon", points=[[-10, 7]], altitude=3.0, directional=True, heading=125,
                cone_gain=0.1, file=str((folder / "beacon.wav").resolve())),
        Emitter(name="High chime", points=[[12, 10]], altitude=10.0, file=str((folder / "chime.wav").resolve())),
        Emitter(name="Doppler fly-by", kind="line", points=[[-35, -6], [35, -6]],
                speed=45, gain=0.8, altitude=0.8, radius=75, reference_distance=5,
                max_distance=70, file=str((folder / "engine.wav").resolve())),
    ])
    ogg_files = sorted(
        (p for p in (folder / "ogg").glob("*") if p.is_file() and p.suffix.lower() == ".ogg"),
        key=lambda p: p.name.casefold(),
    )
    # Ten samples sit about 40 m apart, beyond the small central demo.
    # Grow the ring if more samples are added to keep that separation useful.
    ring_radius = max(65.0, len(ogg_files) * 6.5)
    gains = (0.56, 0.72, 0.63, 0.68, 0.59, 0.75, 0.65, 0.70, 0.60, 0.67)
    altitudes = (0.0, 2.0, 5.0, 8.0, 12.0, 1.0, 4.0, 7.0, 11.0, 15.0)
    for index, path in enumerate(ogg_files):
        angle = 2 * math.pi * index / len(ogg_files)
        x, y = ring_radius * math.sin(angle), ring_radius * math.cos(angle)
        moving = index % 3 == 1
        # Short tangential paths keep moving sounds in their own part of the ring.
        offsets = (-12.0, 12.0) if moving else (0.0,)
        points = [[round(x + offset * math.cos(angle), 2),
                   round(y - offset * math.sin(angle), 2)] for offset in offsets]
        scene.emitters.append(Emitter(
            name=path.stem.rsplit("__", 1)[-1],
            kind="line" if moving else "point", points=points,
            speed=3.0 + index // 3, motion="pingpong",
            file=str(path.resolve()), gain=gains[index % len(gains)],
            altitude=altitudes[index % len(altitudes)],
            directional=index % 5 == 0, heading=(math.degrees(angle) + 180) % 360,
            cone_gain=0.1,
            radius=26.0, reference_distance=4.0, max_distance=26.0,
        ))
    scene.zones = [
        ReverbZone(name="Stone cave", x=-70, y=-40, width=35, height=35, preset="cave", **ZONE_PRESETS["cave"]),
        ReverbZone(name="Concert hall", x=-35, y=18, width=35, height=30, preset="hall", **ZONE_PRESETS["hall"]),
        ReverbZone(name="Open air", x=15, y=25, width=40, height=30, preset="outdoor", **ZONE_PRESETS["outdoor"]),
    ]
    return scene
