"""Generated sounds near the player, with an outer ring of available Ogg samples."""
from pathlib import Path
import math
import random
import struct
import wave

from .model import Emitter, Scene


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
        Emitter(name="Beacon", points=[[-10, 7]], file=str((folder / "beacon.wav").resolve())),
        Emitter(name="High chime", points=[[12, 10]], altitude=8, file=str((folder / "chime.wav").resolve())),
        Emitter(name="Passing engine", kind="line", points=[[-22, -8], [-8, -5], [8, 2], [23, -6]],
                speed=9, gain=0.8, file=str((folder / "engine.wav").resolve())),
    ])
    ogg_files = sorted(
        (p for p in (folder / "ogg").glob("*") if p.is_file() and p.suffix.lower() == ".ogg"),
        key=lambda p: p.name.casefold(),
    )
    # Ten samples sit about 40 m apart, beyond the small central demo.
    # Grow the ring if more samples are added to keep that separation useful.
    ring_radius = max(65.0, len(ogg_files) * 6.5)
    for index, path in enumerate(ogg_files):
        angle = 2 * math.pi * index / len(ogg_files)
        scene.emitters.append(Emitter(
            name=path.stem.rsplit("__", 1)[-1],
            points=[[round(ring_radius * math.sin(angle), 2), round(ring_radius * math.cos(angle), 2)]],
            file=str(path.resolve()), gain=0.65,
            radius=26.0, reference_distance=4.0, max_distance=26.0,
        ))
    return scene
