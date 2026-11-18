import json
import math

import pytest

from openal_explore.model import Emitter, Scene, load_scene, path_sample, save_scene


def test_path_uses_arc_length_and_reverses():
    points = [[0, 0], [3, 0], [3, 4]]
    assert path_sample(points, 5) == ((3, 2), (0, 1))
    assert path_sample(points, 9) == ((3, 2), (0, -1))
    assert path_sample(points, 14) == ((0, 0), (1, 0))
    assert path_sample(points, 7) == ((3, 4), (0, -1))
    assert path_sample([[1, 2], [1, 2]], 100) == ((1, 2), (0, 0))


def test_closed_path_moves_along_closing_segment():
    p, velocity = path_sample([[0, 0], [3, 0], [3, 4]], 9.5, "loop")
    assert p == pytest.approx((1.5, 2))
    assert velocity == pytest.approx((-0.6, -0.8))


def test_motion_obeys_speed_and_disabled_state():
    e = Emitter(kind="line", points=[[0, 0], [100, 0]], speed=8)
    scene = Scene(emitters=[e])
    scene.advance(0.25)
    assert e.sample() == ((2, 0), (8, 0))
    e.enabled = False
    scene.advance(10)
    assert e.sample() == ((2, 0), (0, 0))


def test_scene_roundtrip_relative_assets_without_animation_phase(demo, tmp_path):
    demo.emitters[-1].phase = 123
    demo.settings.hrtf = True
    demo.emitters[0].looping = False
    file = tmp_path / "scene.json"
    save_scene(demo, file)
    raw = json.loads(file.read_text())
    assert not raw["emitters"][0]["file"].startswith(str(tmp_path))
    assert "phase" not in raw["emitters"][-1]
    loaded = load_scene(file)
    assert loaded.emitters[0].file == demo.emitters[0].file
    assert not loaded.emitters[0].looping
    assert loaded.settings.hrtf
    assert loaded.emitters[-1].phase == 0


@pytest.mark.parametrize("modify", [
    lambda d: d.update(version=2),
    lambda d: d["emitters"][0].update(points=[]),
    lambda d: d["emitters"][0].update(pitch=-1),
    lambda d: d["emitters"][0].update(enabled="yes"),
    lambda d: d["emitters"][0].update(points=[[math.nan, 0]]),
    lambda d: d["settings"].update(distance_model="NOPE"),
    lambda d: d["emitters"][0].update(reference_distance=50, max_distance=10),
])
def test_invalid_scenes_rejected(demo, tmp_path, modify):
    file = tmp_path / "scene.json"
    save_scene(demo, file)
    data = json.loads(file.read_text())
    modify(data)
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_scene(file)


def test_source_extensions_round_trip_and_legacy_defaults(demo, tmp_path):
    path = tmp_path / "extensions.json"
    e = demo.emitters[0]
    values = dict(source_distance_model="LINEAR", source_resampler=0,
                  source_spatialize="OFF", source_radius=2.5, show_latency=True)
    for key, value in values.items():
        setattr(e, key, value)
    save_scene(demo, path)
    loaded = load_scene(path).emitters[0]
    assert {key: getattr(loaded, key) for key in values} == values
    data = json.loads(path.read_text())
    for emitter in data["emitters"]:
        for key in values:
            emitter.pop(key)
    path.write_text(json.dumps(data))
    legacy = load_scene(path).emitters[0]
    assert legacy.source_distance_model == legacy.source_spatialize == "DEFAULT"
    assert legacy.source_resampler == -1
    assert legacy.source_radius == 0
    assert not legacy.show_latency
