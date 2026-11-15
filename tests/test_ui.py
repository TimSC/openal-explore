from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
import pytest

from openal_explore.app import MainWindow
from openal_explore.audio import Audio


def test_forward_and_backward_follow_heading(qapp, demo, tmp_path):
    import time

    window = MainWindow(demo, Audio(enabled=False), tmp_path)
    window.show()
    window.activateWindow()
    window.canvas.setFocus()
    qapp.processEvents()
    window.timer.stop()
    player = demo.player
    for heading, unit in [(0, (0, 1)), (90, (1, 0)), (180, (0, -1)),
                          (-90, (-1, 0)), (45, (2 ** -0.5, 2 ** -0.5))]:
        for key, sign in [(Qt.Key.Key_Up, 1), (Qt.Key.Key_Down, -1)]:
            player.x = player.y = 0
            player.heading = heading
            QTest.keyPress(window.canvas, key)
            window.last_time = time.perf_counter() - 0.1
            window.tick()
            QTest.keyRelease(window.canvas, key)
            assert (player.x, player.y) == pytest.approx(
                tuple(v * sign * player.speed * 0.1 for v in unit), abs=0.001)
            assert (player.heading - heading) % 360 == 0
    window.dirty = False
    window.close()


def test_arrow_turning_keeps_player_position_and_map_north_up(qapp, demo, tmp_path):
    import time

    window = MainWindow(demo, Audio(enabled=False), tmp_path)
    window.show()
    window.activateWindow()
    window.canvas.setFocus()
    qapp.processEvents()
    window.timer.stop()
    position = (demo.player.x, demo.player.y)
    north = window.canvas.to_screen((position[0], position[1] + 10))
    for key, expected_heading in [(Qt.Key.Key_Right, 9), (Qt.Key.Key_Left, 0)]:
        QTest.keyPress(window.canvas, key)
        window.last_time = time.perf_counter() - 0.1
        window.tick()
        QTest.keyRelease(window.canvas, key)
        assert abs(demo.player.heading - expected_heading) < 0.01
        assert (demo.player.x, demo.player.y) == position
        assert window.canvas.to_screen((position[0], position[1] + 10)) == north
    for key in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D):
        QTest.keyPress(window.canvas, key)
        assert window.canvas.movement() == (0, 0, 0)
        assert key not in window.canvas.keys
        QTest.keyRelease(window.canvas, key)
    window.dirty = False
    window.close()


def click_world(canvas, xy):
    p = canvas.to_screen(xy)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=p.toPoint())


def test_scene_tools_and_inspectors(qapp, demo, tmp_path):
    window = MainWindow(demo, Audio(enabled=False), tmp_path / "samples")
    window.show()
    qapp.processEvents()
    window.canvas.fit()
    window.set_tool("point")
    click_world(window.canvas, (5, -3))
    assert len(demo.emitters) == 4
    assert window.inspector.identifier == demo.emitters[-1].id
    window.set_tool("line")
    for xy in ((-8, -10), (0, -10), (5, -8)):
        click_world(window.canvas, xy)
    QTest.keyClick(window.canvas, Qt.Key.Key_Return)
    e = demo.emitters[-1]
    assert e.kind == "line" and len(e.points) == 3
    assert window.inspector.table.rowCount() == 3
    window.set_tool("vertices")
    first = window.canvas.to_screen(e.points[0]).toPoint()
    target = first + QPoint(30, -20)
    original = e.points[0][:]
    QTest.mousePress(window.canvas, Qt.MouseButton.LeftButton, pos=first)
    QTest.mouseMove(window.canvas, target)
    QTest.mouseRelease(window.canvas, Qt.MouseButton.LeftButton, pos=target)
    assert e.points[0] != original
    QTest.keyClick(window.canvas, Qt.Key.Key_Delete)
    assert len(e.points) == 2
    window.select("player")
    assert window.inspector.tabs.count() == 2
    assert window.canvas.to_screen((demo.player.x, demo.player.y)).toPoint() == window.canvas.rect().center() + QPoint(1, 1)
    window.dirty = False
    window.close()


def test_movement_keys_clear_when_editing_properties(qapp, demo, tmp_path):
    window = MainWindow(demo, Audio(enabled=False), tmp_path)
    window.show()
    window.activateWindow()
    window.canvas.setFocus()
    qapp.processEvents()
    QTest.keyPress(window.canvas, Qt.Key.Key_Up)
    assert window.canvas.movement()[1] == 1
    window.inspector.tabs.setFocus()
    qapp.processEvents()
    assert not window.canvas.keys
    window.pause_action.trigger()
    assert window.paused
    before = demo.emitters[-1].phase
    window.tick()
    assert demo.emitters[-1].phase == before
    window.dirty = False
    window.close()
