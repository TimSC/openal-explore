from dataclasses import asdict

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from openal_explore.app import MainWindow
from openal_explore.audio import Audio


def test_diagnostics_read_native_state_without_changing_scene_or_playback(audio, demo):
    audio.update(demo)
    before = asdict(demo)
    sources = {key: p.source for key, p in audio.playbacks.items()}
    buffers = dict(audio.buffers)
    with audio.context.activate() as ctx:
        native_before = (ctx.listener.position, ctx.listener.gain,
                         ctx.doppler_factor, sources[demo.emitters[0].id].offset_seconds)
    report = audio.diagnostics(demo)
    assert "OpenAL Soft" in report["Overview"]
    assert "OpenAL version:" in report["Overview"]
    assert "ALC_FREQUENCY:" in report["Overview"]
    assert "Position (m):" in report["Listener"]
    assert "Beacon" in report["Sources"]
    assert "Native state: PLAYING" in report["Sources"]
    assert "AL_" in report["AL extensions"]
    assert "ALC_" in report["ALC extensions"]
    assert asdict(demo) == before
    assert audio.buffers == buffers
    assert {key: p.source for key, p in audio.playbacks.items()} == sources
    with audio.context.activate() as ctx:
        assert (ctx.listener.position, ctx.listener.gain,
                ctx.doppler_factor, sources[demo.emitters[0].id].offset_seconds) == native_before


def test_disabled_audio_information_is_available():
    audio = Audio(enabled=False)
    report = audio.diagnostics()
    assert "Audio disabled" in report["Overview"]
    assert "Unavailable" in report["Listener"]


def test_information_window_is_readonly_and_reuses_popup(qapp, demo, tmp_path):
    window = MainWindow(demo, Audio(enabled=False), tmp_path)
    window.show()
    qapp.processEvents()
    window.timer.stop()
    window.show_audio_info()
    qapp.processEvents()
    dialog = window.audio_info_dialog
    assert dialog.isVisible() and not dialog.isModal()
    assert dialog.timer.isActive()
    assert all(view.isReadOnly() for view in dialog.findChildren(QPlainTextEdit))
    overview = dialog.views["Overview"]
    previous = overview.toPlainText()
    QTest.keyClicks(overview, "cannot edit this")
    assert overview.toPlainText() == previous
    dialog.copy_all()
    assert "Audio disabled" in QApplication.clipboard().text()
    assert "ALC extensions" in QApplication.clipboard().text()
    assert not window.dirty
    dialog.close()
    assert not dialog.timer.isActive()
    window.show_audio_info()
    assert window.audio_info_dialog is dialog
    assert dialog.timer.isActive()
    window.close()
    assert not dialog.isVisible()
    assert not dialog.timer.isActive()
