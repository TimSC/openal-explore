from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class Inspector(QWidget):
    changed = Signal()
    replay = Signal(str)
    editVertices = Signal()

    def __init__(self, scene, audio):
        super().__init__()
        self.scene, self.audio = scene, audio
        self.identifier = "player"
        self.bindings = []
        self.table = None
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(12, 12, 12, 12)
        self.title = QLabel()
        self.title.setObjectName("inspectorTitle")
        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("muted")
        self.root.addWidget(self.title)
        self.root.addWidget(self.subtitle)
        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs, 1)
        self.select("player")

    def page(self, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 12, 4, 8)
        layout.setSpacing(14)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, name)
        return layout

    @staticmethod
    def group(layout, title):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setContentsMargins(10, 22, 10, 12)
        form.setSpacing(10)
        layout.addWidget(group)
        return form

    @staticmethod
    def note(layout, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("muted")
        layout.addWidget(label)

    def number(self, form, label, obj, key, low, high, step=0.1, suffix="", tip=""):
        widget = QDoubleSpinBox()
        widget.setRange(low, high)
        widget.setDecimals(2)
        widget.setSingleStep(step)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        widget.setValue(getattr(obj, key))
        widget.setToolTip(tip)
        widget.valueChanged.connect(lambda value: self.assign(obj, key, value))
        form.addRow(label, widget)
        self.bindings.append((widget, obj, key))
        return widget

    def check(self, form, label, obj, key, tip=""):
        widget = QCheckBox(label)
        widget.setChecked(getattr(obj, key))
        widget.setToolTip(tip)
        widget.toggled.connect(lambda value: self.assign(obj, key, value))
        form.addRow(widget)
        self.bindings.append((widget, obj, key))
        return widget

    def combo(self, form, label, obj, key, choices):
        widget = QComboBox()
        for value, text in choices:
            widget.addItem(text, value)
        widget.setCurrentIndex(widget.findData(getattr(obj, key)))
        widget.currentIndexChanged.connect(lambda index: self.assign(obj, key, widget.itemData(index)))
        form.addRow(label, widget)
        return widget

    def assign(self, obj, key, value):
        setattr(obj, key, value)
        if hasattr(obj, "max_distance"):
            if key == "reference_distance" and obj.max_distance <= value:
                obj.max_distance = value + 0.01
            elif key == "max_distance" and obj.reference_distance >= value:
                obj.reference_distance = value - 0.01
            if key == "cone_inner" and obj.cone_outer < value:
                obj.cone_outer = value
            elif key == "cone_outer" and obj.cone_inner > value:
                obj.cone_inner = value
        self.refresh_fields()
        self.changed.emit()

    def select(self, identifier):
        old_index = self.tabs.currentIndex() if identifier == self.identifier else 0
        self.identifier = identifier
        self.bindings.clear()
        self.table = None
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        if identifier == "player":
            self.player_ui()
        elif (emitter := self.scene.find(identifier)):
            self.emitter_ui(emitter)
        else:
            self.title.setText("Inspector")
            self.subtitle.setText("Select the player, a sound point, or a path on the map.")
        if 0 <= old_index < self.tabs.count():
            self.tabs.setCurrentIndex(old_index)

    def player_ui(self):
        player, settings = self.scene.player, self.scene.settings
        self.title.setText("Player / listener")
        self.subtitle.setText("Your ears in the scene. Movement keeps you at the centre of the map.")
        page = self.page("Listener")
        form = self.group(page, "Position & movement")
        for key, label in [("x", "X · east"), ("y", "Y · north"), ("altitude", "Altitude")]:
            self.number(form, label, player, key, -1e6, 1e6, 1, " m")
        self.number(form, "Move speed", player, "speed", 0, 100, 1, " m/s")
        self.number(form, "Facing", player, "heading", -360, 360, 5, "°", "0° is north. Left / Right or Q / E turn while the map has focus. The map stays north-up.")
        form = self.group(page, "Output")
        self.number(form, "Master volume", settings, "volume", 0, 1, 0.05)
        hrtf = self.check(form, "Headphone spatialization (HRTF)", settings, "hrtf",
                          "Binaural rendering helps locate sources above, behind and in front. Use headphones.")
        hrtf.setEnabled(self.audio.hrtf)
        self.hrtf_control = hrtf
        self.hrtf_status = QLabel()
        self.hrtf_status.setWordWrap(True)
        form.addRow("HRTF status", self.hrtf_status)
        self.note(page, self.audio.info or self.audio.error)
        page.addStretch()
        page = self.page("Acoustics")
        form = self.group(page, "Distance & Doppler")
        self.combo(form, "Distance model", settings, "distance_model", [
            ("NONE", "None"), ("INVERSE_CLAMPED", "Inverse · clamped"), ("INVERSE", "Inverse"),
            ("LINEAR_CLAMPED", "Linear · clamped"), ("LINEAR", "Linear"),
            ("EXPONENT_CLAMPED", "Exponent · clamped"), ("EXPONENT", "Exponent")])
        self.number(form, "Doppler factor", settings, "doppler", 0, 10, 0.1,
                    tip="0 disables velocity-driven pitch changes. Higher values exaggerate the effect.")
        self.number(form, "Speed of sound", settings, "speed_of_sound", 10, 10000, 10, " m/s")
        form = self.group(page, "Reverb · EFX")
        enabled = self.check(form, "Enable room reverb", settings, "reverb")
        gain = self.number(form, "Return volume", settings, "reverb_gain", 0, 1, 0.05)
        decay = self.number(form, "Decay time", settings, "reverb_decay", 0.1, 20, 0.1, " s")
        for widget in (enabled, gain, decay):
            widget.setEnabled(self.audio.efx)
        self.note(page, "EFX available: reverb, low-pass filtering and air absorption." if self.audio.efx else
                  "EFX is unavailable on this audio device. Effects controls are disabled.")
        self.note(page, "Positions are measured in metres. Altitude is OpenAL's vertical axis. Scene velocity is sent to OpenAL for Doppler mixing.")
        page.addStretch()

    def emitter_ui(self, e):
        self.title.setText(e.name)
        self.subtitle.setText("Moving source on an editable polyline" if e.kind == "line" else "Stationary spatial sound source")
        page = self.page("Sound")
        form = self.group(page, "Sound asset")
        name = QLineEdit(e.name)
        name.editingFinished.connect(lambda: self.assign(e, "name", name.text().strip() or "Sound"))
        form.addRow("Name", name)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        filename = QLineEdit(e.file)
        filename.setPlaceholderText("Choose an audio file…")
        filename.setToolTip(e.file)
        filename.editingFinished.connect(lambda: self.assign(e, "file", str(Path(filename.text()).resolve()) if filename.text() else ""))
        browse = QPushButton("…")
        browse.setFixedWidth(32)

        def choose():
            path, _ = QFileDialog.getOpenFileName(self, "Choose sound", e.file,
                "Audio (*.wav *.flac *.ogg *.mp3 *.aiff *.aif *.opus);;All files (*)")
            if path:
                filename.setText(path)
                filename.setToolTip(path)
                self.assign(e, "file", path)
        browse.clicked.connect(choose)
        layout.addWidget(filename, 1)
        layout.addWidget(browse)
        form.addRow("File", row)
        self.check(form, "Enabled", e, "enabled")
        self.check(form, "Loop sound", e, "looping", "Unchecked: play once when entering range or pressing Replay.")
        self.number(form, "Volume", e, "gain", 0, 4, 0.05, tip="OpenAL source gain. 1 is the original level; values above 1 amplify.")
        self.number(form, "Pitch", e, "pitch", 0.1, 4, 0.05, "×", "Also changes playback speed. Doppler applies on top of this.")
        replay = QPushButton("Replay / retry sound")
        replay.clicked.connect(lambda: self.replay.emit(e.id))
        form.addRow(replay)
        self.playback = QLabel()
        self.playback.setWordWrap(True)
        form.addRow("Playback", self.playback)
        if e.kind == "point":
            form = self.group(page, "Position")
            for index, label in enumerate(("X · east", "Y · north")):
                spin = QDoubleSpinBox()
                spin.setRange(-1e6, 1e6)
                spin.setDecimals(2)
                spin.setSuffix(" m")
                spin.setKeyboardTracking(False)
                spin.setValue(e.points[0][index])
                spin.valueChanged.connect(lambda value, i=index: self.set_point(e, i, value))
                form.addRow(label, spin)
                self.bindings.append((spin, e.points[0], index))
        else:
            form = self.group(page, "Path motion")
            self.number(form, "Travel speed", e, "speed", 0, 100, 0.5, " m/s")
            self.combo(form, "At path ends", e, "motion", [("pingpong", "Back and forth"), ("loop", "Loop · close path")])
            self.check(form, "Face along path", e, "follow_path")
            edit = QPushButton("Edit vertices on map  [4]")
            edit.clicked.connect(self.editVertices.emit)
            form.addRow(edit)
        self.number(form, "Altitude", e, "altitude", -1e6, 1e6, 0.5, " m")
        self.position_label = QLabel()
        self.velocity_label = QLabel()
        form.addRow("Current X / Y", self.position_label)
        form.addRow("Velocity", self.velocity_label)
        self.note(page, "Files are decoded and downmixed to mono for positional audio. The original file stays unchanged.")
        page.addStretch()
        page = self.page("Spatial")
        form = self.group(page, "Range & attenuation")
        self.number(form, "Audible radius", e, "radius", 0.1, 10000, 1, " m",
                    "The demo stops sources outside this 3D distance, including altitude. Re-entering retriggers the sound.")
        self.number(form, "Reference distance", e, "reference_distance", 0.01, 9999.99, 0.5, " m",
                    "The distance at which attenuation starts for clamped models.")
        self.number(form, "Max distance", e, "max_distance", 0.02, 10000, 1, " m",
                    "OpenAL attenuation clamp distance. This is not an automatic mute radius.")
        self.number(form, "Rolloff factor", e, "rolloff", 0, 10, 0.1,
                    tip="0 removes distance attenuation; 1 is the normal curve.")
        form = self.group(page, "Directional sound cone")
        self.number(form, "Facing", e, "heading", -360, 360, 5, "°",
                    "0° north, 90° east. Moving lines can face their current path segment instead.")
        self.number(form, "Inner cone", e, "cone_inner", 0, 360, 5, "°", "Full volume inside this angle. 360° is omnidirectional.")
        self.number(form, "Outer cone", e, "cone_outer", 0, 360, 5, "°")
        self.number(form, "Outside volume", e, "cone_gain", 0, 1, 0.05,
                    tip="Gain outside the outer cone. The transition between cones is interpolated by OpenAL.")
        self.note(page, "Selected sounds show their audible radius, reference/max distances and directional cone on the map.")
        page.addStretch()
        page = self.page("Effects")
        form = self.group(page, "Environmental effects · EFX")
        controls = [self.check(form, "Send to room reverb", e, "reverb_send"),
                    self.number(form, "Air absorption", e, "air_absorption", 0, 10, 0.1,
                                tip="Higher values absorb more high frequencies over distance."),
                    self.check(form, "Low-pass filter", e, "lowpass"),
                    self.number(form, "High-frequency gain", e, "lowpass_hf", 0, 1, 0.05,
                                tip="1 is clear; 0 removes high frequencies, like a muffled source.")]
        for control in controls:
            control.setEnabled(self.audio.efx)
        self.note(page, "Enable and tune the shared reverb under Player → Acoustics. Each sound can opt into it." if self.audio.efx else
                  "This device does not support EFX. These controls are unavailable.")
        page.addStretch()
        if e.kind == "line":
            page = self.page("Vertices")
            self.note(page, "Edit coordinates here, or use Edit Vertices on the map. Double-click a map segment to insert a point.")
            self.table = QTableWidget(0, 2)
            self.table.setHorizontalHeaderLabels(["X · east (m)", "Y · north (m)"])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setMinimumHeight(200)
            self.refresh_table()
            self.table.cellChanged.connect(self.table_changed)
            page.addWidget(self.table)
            row = QHBoxLayout()
            add, remove = QPushButton("Add after selected"), QPushButton("Remove selected")
            add.clicked.connect(lambda: self.change_vertex(True))
            remove.clicked.connect(lambda: self.change_vertex(False))
            row.addWidget(add)
            row.addWidget(remove)
            page.addLayout(row)
            page.addStretch()
        self.refresh_telemetry()

    def set_point(self, e, index, value):
        e.points[0][index] = value
        self.changed.emit()

    def refresh_table(self):
        e = self.scene.find(self.identifier)
        if self.table is None or e is None:
            return
        self.table.blockSignals(True)
        self.table.setRowCount(len(e.points))
        for row, point in enumerate(e.points):
            for column, value in enumerate(point):
                self.table.setItem(row, column, QTableWidgetItem(f"{value:.2f}"))
        self.table.blockSignals(False)

    def table_changed(self, row, column):
        e = self.scene.find(self.identifier)
        try:
            value = float(self.table.item(row, column).text())
            if not math.isfinite(value) or abs(value) > 1e6:
                raise ValueError()
            e.points[row][column] = value
            self.changed.emit()
        except ValueError:
            self.refresh_table()

    def change_vertex(self, add):
        e = self.scene.find(self.identifier)
        row = self.table.currentRow()
        if row < 0:
            row = len(e.points) - 1
        if add:
            a = e.points[row]
            b = e.points[row + 1] if row + 1 < len(e.points) else [a[0] + 4, a[1]]
            e.points.insert(row + 1, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
        elif len(e.points) > 2:
            e.points.pop(row)
        self.refresh_table()
        self.changed.emit()

    def refresh_fields(self):
        focus = QApplication.focusWidget()
        for widget, obj, key in self.bindings:
            if focus and (widget == focus or widget.isAncestorOf(focus)):
                continue
            value = obj[key] if isinstance(obj, list) else getattr(obj, key)
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)
            widget.blockSignals(False)

    def refresh_telemetry(self):
        if self.identifier == "player":
            self.hrtf_status.setText(self.audio.hrtf_actual)
            self.hrtf_control.setEnabled(self.audio.hrtf)
            return
        e = self.scene.find(self.identifier)
        if e:
            pos, velocity = e.sample()
            self.title.setText(e.name)
            self.playback.setText(self.audio.state(e.id))
            self.position_label.setText(f"{pos[0]:.2f} / {pos[1]:.2f} m")
            self.velocity_label.setText(f"{velocity[0]:.1f} / {velocity[1]:.1f} m/s")
