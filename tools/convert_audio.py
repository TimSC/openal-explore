"""Convert a WAV folder to Ogg Vorbis without modifying the source files."""
import argparse
from pathlib import Path

import soundfile as sf


def convert_folder(source: Path, destination: Path):
    source = source.resolve()
    destination = destination.resolve()
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".wav")
    if not files:
        raise ValueError(f"No WAV files found in {source}")
    converted = []
    for file in files:
        target = (destination / file.relative_to(source)).with_suffix(".ogg")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite {target}")
        temporary = target.with_suffix(".tmp.ogg")
        try:
            with sf.SoundFile(file) as original:
                rate, channels, frames = original.samplerate, original.channels, original.frames
                with sf.SoundFile(temporary, "w", samplerate=rate, channels=channels,
                                  format="OGG", subtype="VORBIS") as output:
                    for block in original.blocks(blocksize=65536, dtype="float32", always_2d=True):
                        output.write(block)
            result = sf.info(temporary)
            if (result.samplerate, result.channels, result.frames) != (rate, channels, frames):
                raise RuntimeError(f"Output metadata does not match: {target}")
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        converted.append(target)
        print(f"{target.name}: {frames / rate:.1f}s, {rate} Hz, {channels} ch, "
              f"{file.stat().st_size:,} -> {target.stat().st_size:,} bytes", flush=True)
    print(f"Converted {len(converted)} files to {destination}", flush=True)
    return converted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    convert_folder(args.source, args.destination)
