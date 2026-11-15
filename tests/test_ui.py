from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from openal_explore.app import MainWindow
from openal_explore.audio import Audio


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
    QTest.keyPress(window.canvas, Qt.Key.Key_W)
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
