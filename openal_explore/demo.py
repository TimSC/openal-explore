"""Small generated mono WAVs make the demo usable without external assets."""
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
    return Scene(emitters=[
        Emitter(name="Beacon", points=[[-10, 7]], file=str((folder / "beacon.wav").resolve())),
        Emitter(name="High chime", points=[[12, 10]], altitude=8, file=str((folder / "chime.wav").resolve())),
        Emitter(name="Passing engine", kind="line", points=[[-22, -8], [-8, -5], [8, 2], [23, -6]],
                speed=9, gain=0.8, file=str((folder / "engine.wav").resolve())),
    ])
