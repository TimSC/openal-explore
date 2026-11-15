import numpy as np
import pytest

from openal_explore.model import Scene


def render(audio, frames=4800):
    with audio.context.activate():
        return np.frombuffer(audio.device.render(frames), dtype=np.int16).reshape(-1, 2).astype(float)


def energy(pcm):
    return np.sqrt((pcm * pcm).mean(axis=0))


def test_real_openal_panning_and_vertical_position(audio, demo):
    e = demo.emitters[0]
    e.points = [[-4, 0]]
    demo.emitters = [e]
    audio.update(demo)
    assert not audio.error
    assert audio.state(e.id) == "Playing"
    left = energy(render(audio, 24000))
    assert left[0] > left[1] * 1.5
    e.points = [[4, 0]]
    e.altitude = 5
    audio.update(demo)
    render(audio)  # Allow OpenAL's gain interpolation to settle.
    right = energy(render(audio, 24000))
    assert right[1] > right[0] * 1.5
    with audio.context.activate():
        assert audio.playbacks[e.id].source.position == pytest.approx((4, 5, 0))
        assert audio.context.listener.position == pytest.approx((0, 1.7, 0))


def test_moving_source_velocity_and_effects(audio, demo):
    e = demo.emitters[-1]
    demo.emitters = [e]
    e.points = [[0, 0], [20, 0]]
    e.speed = 10
    e.lowpass = True
    e.air_absorption = 2
    demo.settings.reverb = True
    demo.advance(0.5)
    audio.update(demo, (1, 2))
    assert not audio.error
    assert audio.state(e.id) == "Playing"
    with audio.context.activate():
        src = audio.playbacks[e.id].source
        assert src.position == pytest.approx((5, 0, 0))
        assert src.velocity == pytest.approx((10, 0, 0))
        assert audio.context.listener.velocity == pytest.approx((1, 0, -2))
        if audio.efx:
            assert src.direct_filter is not None
            assert src.get_send(0)[0] is audio.slot
            assert audio.slot.gain == pytest.approx(0.25)
    assert energy(render(audio)).max() > 0


def test_pause_one_shot_range_and_replay(audio, demo):
    e = demo.emitters[0]
    demo.emitters = [e]
    e.looping = False
    audio.update(demo)
    audio.update(demo, paused=True)
    assert audio.state(e.id) == "Paused"
    audio.update(demo, paused=False)
    assert audio.state(e.id) == "Playing"
    render(audio, 48000 * 5)
    audio.update(demo)
    assert audio.state(e.id).startswith("Finished")
    audio.update(demo)
    assert audio.playbacks[e.id].source is None  # No frame-by-frame one-shot retrigger.
    audio.restart(e.id)
    audio.update(demo)
    assert audio.state(e.id) == "Playing"
    demo.player.x = 200
    audio.update(demo)
    assert audio.state(e.id) == "Out of range"
    demo.player.x = 0
    audio.update(demo)
    assert audio.state(e.id) == "Playing"
    e.enabled = False
    audio.update(demo)
    assert audio.state(e.id) == "Disabled"


def test_missing_file_does_not_break_other_sources(audio, demo):
    e = demo.emitters[0]
    e.file = "C:/no-such-sound.wav"
    audio.update(demo)
    assert audio.state(e.id).startswith("Error:")
    assert audio.state(demo.emitters[1].id) == "Playing"
    assert not audio.error


def test_soundfile_decodes_stereo_flac_to_spatial_mono(audio, demo, tmp_path):
    import soundfile as sf
    rate = 22050
    signal = np.sin(2 * np.pi * 300 * np.arange(rate) / rate) * 0.5
    file = tmp_path / "stereo.flac"
    sf.write(file, np.column_stack((signal, signal * 0.5)), rate)
    e = demo.emitters[0]
    e.file = str(file)
    demo.emitters = [e]
    audio.update(demo)
    assert audio.state(e.id) == "Playing"
    with audio.context.activate():
        buffer = audio.playbacks[e.id].source.buffer
        assert buffer.channels == 1
        assert buffer.sample_rate == rate
        assert buffer.duration == pytest.approx(1)
    assert sf.info(file).channels == 2  # Original asset remains stereo.
    assert energy(render(audio)).max() > 0


def test_hrtf_and_global_acoustic_settings(audio, demo):
    demo.settings.hrtf = True
    demo.settings.distance_model = "LINEAR_CLAMPED"
    demo.settings.doppler = 2
    demo.settings.speed_of_sound = 300
    audio.update(demo)
    assert not audio.error
    assert audio.state(demo.emitters[0].id) == "Playing"
    with audio.context.activate():
        assert audio.context.distance_model.name == "LINEAR_CLAMPED"
        assert audio.context.doppler_factor == pytest.approx(2)
        assert audio.context.speed_of_sound == pytest.approx(300)
    if audio.hrtf:
        assert audio.hrtf_actual != "Unavailable"
    demo.settings.hrtf = False
    audio.update(demo)
    assert not audio.error
