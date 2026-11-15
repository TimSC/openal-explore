from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QToolBar, QTreeWidget, QTreeWidgetItem,
)

from .audio import Audio
from .canvas import MapCanvas
from .demo import create_demo
from .inspector import Inspector
from .model import Scene, load_scene, save_scene


STYLE = """
QMainWindow, QWidget { background: #17232f; color: #d2dfeb; }
QMainWindow { font-family: 'Segoe UI'; font-size: 12px; }
QMenuBar, QMenu, QToolBar { background: #1b2937; }
QMenuBar::item:selected, QMenu::item:selected { background: #31465a; }
QToolBar { spacing: 5px; padding: 7px; border-bottom: 1px solid #304052; }
QToolButton { padding: 8px 10px; border: 1px solid transparent; border-radius: 4px; }
QToolButton:hover, QPushButton:hover { background: #30465a; }
QToolButton:checked { background: #2b4860; border-color: #5a95bf; color: #bce5ff; }
QDockWidget { font-weight: 600; }
QDockWidget::title { background: #203041; padding: 8px; }
QLabel#inspectorTitle { font-size: 19px; font-weight: 600; padding-top: 4px; }
QLabel#muted { color: #91a8bc; font-weight: normal; }
QGroupBox { border: 1px solid #344557; border-radius: 5px; margin-top: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #a3bfd5; }
QLineEdit, QDoubleSpinBox, QComboBox { background: #101c28; border: 1px solid #3a4d60; border-radius: 3px; padding: 5px; min-height: 19px; }
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #79afd6; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 16px; }
QPushButton { background: #263c4e; border: 1px solid #3e5970; border-radius: 4px; padding: 7px; }
QCheckBox { spacing: 8px; padding: 2px; font-weight: normal; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 9px 8px; color: #96aebf; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #deedf8; border-bottom-color: #80b4ff; }
QTreeWidget, QTableWidget { background: #111e2a; border: none; alternate-background-color: #192936; }
QTreeWidget::item { padding: 7px 3px; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #294760; }
QHeaderView::section { background: #23374a; color: #aac2d5; padding: 6px; border: none; }
QStatusBar { background: #1b2937; color: #9eb4c7; }
QScrollBar:vertical { width: 10px; background: #15212c; }
QScrollBar::handle:vertical { background: #3b5164; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QWidget:disabled { color: #617385; }
QToolTip { color: #e5eff7; background: #2b4053; border: 1px solid #62809a; padding: 6px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, scene=None, audio=None, demo_folder=None):
        super().__init__()
        self.scene = scene if scene is not None else Scene()
        self.audio = audio if audio is not None else Audio()
        self.demo_folder = demo_folder or Path.home() / "OpenAL Explore" / "samples"
        self.path = None
        self.dirty = False
        self.paused = False
        self.last_time = time.perf_counter()
        self.telemetry_time = 0.0
        self.tree_busy = False
        self.setObjectName("openalExplore")
        self.resize(1460, 920)
        self.setMinimumSize(1020, 640)
        self.setStyleSheet(STYLE)
        self.canvas = MapCanvas(self.scene)
        self.setCentralWidget(self.canvas)
        self.inspector = Inspector(self.scene, self.audio)
        self.inspector_dock = QDockWidget("Properties", self)
        self.inspector_dock.setObjectName("properties")
        self.inspector_dock.setWidget(self.inspector)
        self.inspector_dock.setMinimumWidth(370)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Scene", "Playback"])
        self.tree.setColumnWidth(0, 140)
        self.tree.header().setStretchLastSection(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree_dock = QDockWidget("Scene objects", self)
        self.tree_dock.setObjectName("objects")
        self.tree_dock.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)
        self.resizeDocks([self.tree_dock, self.inspector_dock], [250, 400], Qt.Orientation.Horizontal)
        self.hint = QLabel()
        self.hint.setMinimumWidth(0)
        self.statusBar().addWidget(self.hint, 1)
        self.audio_status = QLabel()
        self.statusBar().addPermanentWidget(self.audio_status)
        self._actions()
        self.canvas.selected.connect(self.select)
        self.canvas.edited.connect(self.canvas_edited)
        self.canvas.added.connect(self.add_emitter)
        self.canvas.deleteRequested.connect(self.delete_selected)
        self.canvas.pauseRequested.connect(self.pause_action.trigger)
        self.canvas.toolRequested.connect(self.set_tool)
        self.canvas.toolChanged.connect(lambda tool: self.tool_actions[tool].setChecked(True))
        self.canvas.hintChanged.connect(self.hint.setText)
        self.inspector.changed.connect(self.properties_edited)
        self.inspector.replay.connect(self.replay)
        self.inspector.editVertices.connect(lambda: self.set_tool("vertices"))
        self.tree.currentItemChanged.connect(self.tree_selected)
        self.tree.itemChanged.connect(self.tree_changed)
        self.rebuild_tree()
        self.select("player")
        self.set_tool("inspect")
        self.update_title()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def _actions(self):
        menu = self.menuBar().addMenu("&File")
        self.action(menu, "&New empty scene", lambda: self.replace_scene(Scene()), QKeySequence.StandardKey.New)
        self.action(menu, "Load &demo scene", self.load_demo)
        self.action(menu, "&Open scene…", self.open_scene, QKeySequence.StandardKey.Open)
        menu.addSeparator()
        self.action(menu, "&Save scene", self.save, QKeySequence.StandardKey.Save)
        self.action(menu, "Save scene &as…", lambda: self.save(True), QKeySequence.StandardKey.SaveAs)
        menu.addSeparator()
        self.action(menu, "Exit", self.close)
        menu = self.menuBar().addMenu("&View")
        menu.addAction(self.inspector_dock.toggleViewAction())
        menu.addAction(self.tree_dock.toggleViewAction())
        self.action(menu, "Fit scene around player", self.canvas.fit, "Ctrl+0")
        ranges = self.action(menu, "Show selected sound ranges", self.toggle_ranges)
        ranges.setCheckable(True)
        ranges.setChecked(True)
        menu = self.menuBar().addMenu("&Help")
        self.action(menu, "Controls & OpenAL features", self.show_help)
        toolbar = QToolBar("Tools", self)
        toolbar.setObjectName("tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        group = QActionGroup(self)
        group.setExclusive(True)
        self.tool_actions = {}
        for tool, label in [("inspect", "Inspect  [1]"), ("point", "Add point  [2]"),
                            ("line", "Draw path  [3]"), ("vertices", "Edit vertices  [4]")]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, t=tool: self.set_tool(t))
            group.addAction(action)
            toolbar.addAction(action)
            self.tool_actions[tool] = action
        toolbar.addSeparator()
        self.pause_action = QAction("Pause  [Space]", self)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.set_paused)
        toolbar.addAction(self.pause_action)
        self.action(toolbar, "Restart", self.restart)
        self.action(toolbar, "Fit scene", self.canvas.fit)
        self.action(toolbar, "Delete", self.delete_selected)

    def set_tool(self, tool):
        self.canvas.set_tool(tool)
        self.canvas.setFocus()

    def toggle_ranges(self, checked):
        self.canvas.show_ranges = checked
        self.canvas.update()

    def set_paused(self, paused):
        self.paused = paused
        self.pause_action.setText("Resume  [Space]" if paused else "Pause  [Space]")
        self.canvas.keys.clear()

    def update_title(self):
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{self.path.name if self.path else 'Untitled scene'} · OpenAL Explore")

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()

    def rebuild_tree(self):
        self.tree_busy = True
        self.tree.clear()
        item = QTreeWidgetItem(["Player / listener", "Centred"])
        item.setData(0, Qt.ItemDataRole.UserRole, "player")
        self.tree.addTopLevelItem(item)
        for e in self.scene.emitters:
            item = QTreeWidgetItem([("●  " if e.kind == "point" else "Path · ") + e.name, self.audio.state(e.id)])
            item.setData(0, Qt.ItemDataRole.UserRole, e.id)
            item.setCheckState(0, Qt.CheckState.Checked if e.enabled else Qt.CheckState.Unchecked)
            self.tree.addTopLevelItem(item)
            if self.canvas.selection == e.id:
                self.tree.setCurrentItem(item)
        if self.canvas.selection == "player":
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree_busy = False

    def tree_selected(self, item, previous):
        if not self.tree_busy and item:
            self.select(item.data(0, Qt.ItemDataRole.UserRole))

    def tree_changed(self, item, column):
        if self.tree_busy or column != 0:
            return
        e = self.scene.find(item.data(0, Qt.ItemDataRole.UserRole))
        if e:
            e.enabled = item.checkState(0) == Qt.CheckState.Checked
            self.inspector.refresh_fields()
            self.mark_dirty()

    def select(self, identifier):
        if self.canvas.selection != identifier:
            self.canvas.vertex = self.canvas.drag = None
        self.canvas.selection = identifier
        self.inspector.select(identifier)
        if identifier:
            self.inspector_dock.show()
        self.tree_busy = True
        self.tree.clearSelection()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                self.tree.setCurrentItem(item)
                item.setSelected(True)
        self.tree_busy = False
        self.canvas.update()

    def properties_edited(self):
        self.mark_dirty()
        self.rebuild_tree()
        self.canvas.vertex = None
        self.canvas.update()

    def canvas_edited(self):
        self.mark_dirty()
        # Points may have been replaced during dragging; rebind their coordinate fields.
        e = self.scene.find(self.canvas.selection)
        if e and e.kind == "point":
            self.inspector.bindings = [(w, e.points[0] if isinstance(obj, list) else obj, key)
                                       for w, obj, key in self.inspector.bindings]
        self.inspector.refresh_fields()
        self.inspector.refresh_table()

    def add_emitter(self, e):
        if len(self.scene.emitters) >= 512:
            QMessageBox.information(self, "Scene limit", "A scene supports up to 512 sound objects.")
            return
        sample = self.demo_folder / ("engine.wav" if e.kind == "line" else "beacon.wav")
        if sample.exists():
            e.file = str(sample.resolve())
        self.scene.emitters.append(e)
        self.canvas.selection = e.id
        self.rebuild_tree()
        self.select(e.id)
        self.mark_dirty()

    def delete_selected(self):
        e = self.scene.find(self.canvas.selection)
        if e:
            self.scene.emitters.remove(e)
            self.audio.restart(e.id)
            self.canvas.vertex = None
            self.canvas.selection = "player"
            self.rebuild_tree()
            self.select("player")
            self.mark_dirty()

    def replay(self, identifier):
        self.audio.restart(identifier)

    def restart(self):
        for e in self.scene.emitters:
            e.reset()
        self.audio.restart()

    def tick(self):
        now = time.perf_counter()
        dt = min(0.1, now - self.last_time)
        self.last_time = now
        vx = vy = 0
        if not self.paused and self.isActiveWindow():
            x, y, turn = self.canvas.movement()
            player = self.scene.player
            vx, vy = x * player.speed, y * player.speed
            if vx or vy or turn:
                player.x = max(-1e6, min(1e6, player.x + vx * dt))
                player.y = max(-1e6, min(1e6, player.y + vy * dt))
                if player.face_movement and (x or y):
                    player.heading = math.degrees(math.atan2(x, y))
                player.heading = (player.heading + turn * 90 * dt + 180) % 360 - 180
                self.mark_dirty()
        if not self.paused:
            self.scene.advance(dt)
        self.audio.update(self.scene, (vx, vy), self.paused)
        self.canvas.update()
        if now - self.telemetry_time > 0.2:
            self.telemetry_time = now
            self.inspector.refresh_fields()
            self.inspector.refresh_telemetry()
            self.tree_busy = True
            playing = 0
            for i in range(1, self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                state = self.audio.state(item.data(0, Qt.ItemDataRole.UserRole))
                item.setText(1, state)
                item.setToolTip(1, state)
                playing += state == "Playing"
            self.tree_busy = False
            self.audio_status.setText(self.audio.error or f"{'PAUSED' if self.paused else 'LIVE'} · {playing} playing")
            self.audio_status.setToolTip(self.audio.error or self.audio.info)

    def can_discard(self):
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, "Unsaved scene", "Save your scene changes?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def replace_scene(self, scene, path=None):
        if not self.can_discard():
            return
        self.audio.reset()
        self.scene = scene
        self.path = path
        self.dirty = False
        self.canvas.scene = self.inspector.scene = scene
        self.canvas.draft.clear()
        self.canvas.drag = self.canvas.vertex = None
        self.canvas.keys.clear()
        self.canvas.selection = "player"
        self.rebuild_tree()
        self.select("player")
        self.canvas.fit()
        self.update_title()

    def load_demo(self):
        try:
            self.replace_scene(create_demo(self.demo_folder))
        except OSError as exc:
            QMessageBox.warning(self, "Cannot create demo sounds", str(exc))

    def open_scene(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open scene", str(self.path or ""), "OpenAL scene (*.json)")
        if filename:
            try:
                scene = load_scene(Path(filename))
                self.replace_scene(scene, Path(filename))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                QMessageBox.warning(self, "Cannot load scene", str(exc))

    def save(self, save_as=False):
        # Commit an active editor before serializing the scene.
        focus = QApplication.focusWidget()
        if focus:
            focus.clearFocus()
        path = self.path
        if save_as or path is None:
            filename, _ = QFileDialog.getSaveFileName(self, "Save scene", str(path or "scene.json"), "OpenAL scene (*.json)")
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")
        try:
            save_scene(self.scene, path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot save scene", str(exc))
            return False
        self.path, self.dirty = path, False
        self.update_title()
        return True

    def show_help(self):
        QMessageBox.information(self, "OpenAL Explore", "Click the map to give it keyboard focus.\n\n"
            "WASD / arrows: move · Q / E: turn · Mouse wheel: zoom\n"
            "1: Inspect · 2: Add point · 3: Draw path · 4: Edit vertices\n"
            "Space: pause/resume · Delete: delete selected sound/vertex\n"
            "Path drawing: click vertices, Enter/double-click finishes, Esc cancels.\n"
            "Vertex editing: drag handles, double-click segments to insert.\n"
            "Inspect: drag a sound or an entire path to move it.\n\n"
            "Select the player for listener settings, HRTF, Doppler, attenuation model and reverb.\n"
            "Select sounds for files, looping, volume, pitch, altitude, range, cones and EFX.\n"
            "HRTF works best with headphones. Optional features depend on the output device.\n"
            "The Properties and Scene objects panels can float, move and dock. Reopen them under View.")

    def closeEvent(self, event):
        if not self.can_discard():
            event.ignore()
            return
        self.timer.stop()
        self.audio.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="OpenAL spatial audio playground")
    parser.add_argument("scene", nargs="?", type=Path, help="JSON scene to open")
    parser.add_argument("--no-audio", action="store_true", help="Run the editor without opening an audio device")
    parser.add_argument("--empty", action="store_true", help="Start with an empty scene")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OpenAL Explore")
    app.setFont(QFont("Segoe UI", 10))
    # Use the project folder when running from source; installed builds use user data.
    root = Path(__file__).resolve().parent.parent
    demo_folder = root / "samples" if (root / "pyproject.toml").exists() else Path.home() / "OpenAL Explore" / "samples"
    try:
        scene = load_scene(args.scene) if args.scene else Scene() if args.empty else create_demo(demo_folder)
    except (OSError, ValueError, TypeError) as exc:
        QMessageBox.critical(None, "Cannot open scene", str(exc))
        return 1
    window = MainWindow(scene, Audio(enabled=not args.no_audio), demo_folder)
    window.path = args.scene
    window.update_title()
    window.show()
    QTimer.singleShot(0, window.canvas.fit)
    window.canvas.setFocus()
    return app.exec()
