"""Exercise the showcases through the real OpenAL loopback mixer and Qt tools."""
import json

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox

from openal_explore.app import MainWindow
from openal_explore.audio import Audio
from openal_explore.effect_specs import EFFECTS
from openal_explore.model import Emitter, ReverbZone, Scene, load_scene, save_scene


def render(audio, frames):
    with audio.context.activate():
        return np.frombuffer(audio.device.render(frames), dtype=np.int16).reshape(-1, 2).astype(float)


def tone(tmp_path, seconds=2):
    rate = 48000
    t = np.arange(int(rate * seconds)) / rate
    path = tmp_path / f"tone-{seconds:g}.ogg"
    samples = np.sin(2 * np.pi * 440 * t) * 0.4
    with sf.SoundFile(path, "w", samplerate=rate, channels=1, format="OGG", subtype="VORBIS") as output:
        for start in range(0, len(samples), 8192):
            output.write(samples[start:start + 8192])
    return path


def test_zone_blending_priority_and_serialization(tmp_path):
    scene = Scene(zones=[ReverbZone(x=-5, y=-5, width=10, height=10, fade=4)])
    z = scene.zones[0]
    assert z.weight(0, 0) == 1
    assert z.weight(7, 0) == pytest.approx(0.5)
    assert z.weight(9, 0) == 0
    target, name = scene.reverb_target()
    assert target["wet"] == z.wet
    outdoor = ReverbZone(name="Outdoors", x=-5, y=-5)
    outdoor.apply_preset("outdoor")
    scene.zones.append(outdoor)
    assert scene.reverb_target()[0]["decay"] == pytest.approx(0.3)
    outdoor.enabled = False
    assert scene.reverb_target()[0]["decay"] == pytest.approx(z.decay)
    scene.emitters.append(Emitter(directional=True, effect_type="ECHO", effect_params={"delay": 0.15}, playback_mode="stream"))
    file = tmp_path / "scene.json"
    save_scene(scene, file)
    loaded = load_scene(file)
    assert loaded.zones == scene.zones
    assert loaded.emitters[0].directional
    assert loaded.emitters[0].effect_params == {"delay": 0.15}
    assert loaded.emitters[0].playback_mode == "stream"
    raw = json.loads(file.read_text())
    raw["zones"][0]["width"] = -2
    file.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_scene(file)


def test_old_directional_scenes_still_load(tmp_path):
    file = tmp_path / "old.json"
    file.write_text(json.dumps({"version": 1, "emitters": [{"cone_inner": 45, "cone_outer": 90}]}))
    assert load_scene(file).emitters[0].directional
    file.write_text(json.dumps({"version": 1, "emitters": [{}]}))
    assert not load_scene(file).emitters[0].directional


def test_zone_reverb_changes_smoothly(audio):
    if not audio.efx:
        pytest.skip("EFX unavailable")
    scene = Scene(zones=[ReverbZone(x=10, y=-5, width=20, height=10, fade=2, wet=0.6, decay=4)])
    audio.update(scene, dt=0.1)
    with audio.context.activate():
        assert audio.slot.gain == 0
    scene.player.x = 15
    audio.update(scene, dt=0.1)
    first = audio.reverb_state["wet"]
    assert 0 < first < 0.6
    for _ in range(50):
        audio.update(scene, dt=0.1)
    assert audio.reverb_state["wet"] > 0.59
    scene.player.x = 0
    audio.update(scene, dt=0.1)
    assert first < audio.reverb_state["wet"] < 0.6
    assert not audio.error


@pytest.mark.parametrize("effect", EFFECTS)
def test_each_effect_routes_and_updates(audio, tmp_path, effect):
    if not audio.efx:
        pytest.skip("EFX unavailable")
    e = Emitter(file=str(tone(tmp_path)), points=[[0, 2]], effect_type=effect)
    scene = Scene(emitters=[e])
    audio.update(scene)
    p = audio.playbacks[e.id]
    assert p.state == "Playing", p.error
    assert not p.effect_message
    with audio.context.activate():
        assert p.fx.type.name == effect
        send_index = 1 if audio.effect_sends >= 2 else 0
        assert p.source.get_send(send_index)[0] is p.fx_slot
        if audio.effect_sends >= 2:
            assert p.source.get_send(0)[0] is audio.slot
    samples = render(audio, 12000)
    assert np.abs(samples).max() > 0
    parameter, spec = next(iter(EFFECTS[effect].items()))
    e.effect_params[parameter] = (spec[1] + spec[2]) / 2
    audio.update(scene)
    with audio.context.activate():
        assert p.fx.parameters[parameter] == pytest.approx(e.effect_params[parameter], rel=1e-5)
    e.effect_type, e.effect_params = "NONE", {}
    audio.update(scene)
    assert p.fx is None and p.fx_slot is None
    assert p.state == "Playing"


def test_directional_switch_attenuates_back_of_speaker(audio, tmp_path):
    e = Emitter(file=str(tone(tmp_path)), points=[[0, 4]], altitude=1.7, heading=0,
                directional=True, cone_inner=45, cone_outer=90, cone_gain=0.05)
    scene = Scene(emitters=[e])
    audio.update(scene)
    behind = render(audio, 24000)
    e.heading = 180  # Face the listener south of the source.
    audio.update(scene)
    render(audio, 4800)
    front = render(audio, 24000)
    assert np.sqrt((front ** 2).mean()) > np.sqrt((behind ** 2).mean()) * 5
    e.directional = False
    e.heading = 0
    audio.update(scene)
    with audio.context.activate():
        assert audio.playbacks[e.id].source.cone_inner_angle == 360


def test_doppler_toggle_changes_rendered_pitch(audio, tmp_path):
    e = Emitter(file=str(tone(tmp_path)), kind="line", points=[[-10, 0], [10, 0]],
                altitude=1.7, speed=45, phase=6)
    scene = Scene(emitters=[e])

    def peak_frequency():
        pcm = render(audio, 24000)[2400:].sum(axis=1)
        spectrum = np.abs(np.fft.rfft(pcm * np.hanning(len(pcm))))
        return np.argmax(spectrum) * 48000 / len(pcm)

    audio.update(scene)
    shifted = peak_frequency()
    scene.settings.doppler_enabled = False
    audio.update(scene)
    render(audio, 4800)
    original = peak_frequency()
    assert original == pytest.approx(440, abs=3)
    assert shifted > original * 1.1


def test_streaming_is_bounded_loops_pauses_and_counts_underruns(audio, tmp_path):
    e = Emitter(file=str(tone(tmp_path, seconds=0.25)), playback_mode="stream", points=[[0, 2]])
    scene = Scene(emitters=[e])
    audio.update(scene)
    p = audio.playbacks[e.id]
    assert p.streaming and p.reader is not None
    assert len(p.chunks) == 4
    assert len(audio.buffers) == 0
    for _ in range(30):
        assert np.abs(render(audio, 960)).max() > 0
        audio.update(scene)
        assert p.state == "Playing", p.error
        assert 0 < len(p.chunks) <= 4
    assert p.underruns == 0
    audio.update(scene, paused=True)
    buffered = p.buffered
    render(audio, 24000)
    audio.update(scene, paused=True)
    assert p.buffered == pytest.approx(buffered)
    audio.update(scene)
    render(audio, 48000)  # Deliberately starve the queue; a real underrun.
    audio.update(scene)
    assert p.underruns == 1
    assert p.state == "Playing"
    assert "1 underruns" in audio.stream_info(e.id)
    reader, chunks = p.reader, list(p.chunks)
    e.enabled = False
    audio.update(scene)
    assert reader.closed
    assert all(b.closed for b in chunks)


def test_streamed_one_shot_and_auto_mode(audio, tmp_path):
    e = Emitter(file=str(tone(tmp_path, seconds=0.1)), playback_mode="stream", looping=False, points=[[0, 2]])
    scene = Scene(emitters=[e])
    audio.update(scene)
    render(audio, 12000)
    audio.update(scene)
    assert audio.state(e.id).startswith("Finished")
    assert audio.playbacks[e.id].reader is None
    assert audio.playbacks[e.id].underruns == 0
    e.file = str(tone(tmp_path, seconds=11))
    e.playback_mode = "auto"
    audio.update(scene)
    p = audio.playbacks[e.id]
    assert p.streaming
    with audio.context.activate():
        assert sum(b.size for b in p.chunks) <= 4 * 8192 * 2
    assert not audio.buffers
    e.playback_mode = "static"
    audio.update(scene)
    assert not p.streaming
    assert len(audio.buffers) == 1


def test_zone_drawing_moving_resizing_and_doppler_ui(qapp, tmp_path):
    window = MainWindow(Scene(), Audio(enabled=False), tmp_path)
    window.show()
    qapp.processEvents()
    window.timer.stop()
    canvas = window.canvas
    window.set_tool("zone")
    start, end = canvas.to_screen((-12, -10)).toPoint(), canvas.to_screen((-3, -3)).toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert len(window.scene.zones) == 1
    z = window.scene.zones[0]
    assert window.inspector.identifier == z.id
    assert z.width == pytest.approx(9, abs=0.1)
    window.set_tool("inspect")
    original = (z.x, z.y)
    center = canvas.to_screen((z.x + z.width / 2, z.y + z.height / 2)).toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseMove(canvas, center + QPoint(20, 20))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(20, 20))
    assert (z.x, z.y) != original
    corner = canvas.to_screen((z.x + z.width, z.y + z.height)).toPoint()
    width = z.width
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=corner)
    QTest.mouseMove(canvas, corner + QPoint(20, -20))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=corner + QPoint(20, -20))
    assert z.width > width
    preset = window.inspector.tabs.currentWidget().findChild(QComboBox)
    preset.setCurrentIndex(preset.findData("cave"))
    assert z.decay == 4 and z.preset == "cave"
    window.doppler_action.trigger()
    assert not window.scene.settings.doppler_enabled
    window.delete_selected()
    assert not window.scene.zones
    window.dirty = False
    window.close()


def test_live_effect_inspector_controls(qapp, audio, tmp_path):
    if not audio.efx:
        pytest.skip("EFX unavailable")
    from PySide6.QtWidgets import QDoubleSpinBox

    e = Emitter(file=str(tone(tmp_path)), points=[[0, 2]])
    window = MainWindow(Scene(emitters=[e]), audio, tmp_path)
    window.show()
    qapp.processEvents()
    window.timer.stop()
    window.select(e.id)
    window.inspector.tabs.setCurrentIndex(2)
    page = window.inspector.tabs.currentWidget()
    choice = next(c for c in page.findChildren(QComboBox) if c.findData("FLANGER") >= 0)
    choice.setCurrentIndex(choice.findData("FLANGER"))
    assert e.effect_type == "FLANGER"
    delay = next(w for w, obj, key in window.inspector.bindings if obj is e.effect_params and key == "delay")
    delay.setValue(0.0035)
    assert e.effect_params["delay"] == 0.0035
    audio.update(window.scene)
    assert audio.state(e.id) == "Playing"
    with audio.context.activate():
        assert audio.playbacks[e.id].fx.parameters["delay"] == pytest.approx(0.0035)
    e.effect_params.clear()
    window.inspector.select(e.id)
    assert e.effect_params == {}  # Inspecting a scene does not silently change it.
    window.dirty = False
    window.close()
