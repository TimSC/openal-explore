from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .model import Emitter, ReverbZone, Scene, direction


def segment_projection(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denominator)) if denominator else 0
    return a[0] + dx * t, a[1] + dy * t


class MapCanvas(QWidget):
    selected = Signal(str)
    edited = Signal()
    added = Signal(object)
    deleteRequested = Signal()
    pauseRequested = Signal()
    toolRequested = Signal(str)
    toolChanged = Signal(str)
    hintChanged = Signal(str)
    movement_keys = {Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Right}

    def __init__(self, scene: Scene):
        super().__init__()
        self.scene = scene
        self.selection = "player"
        self.tool = "inspect"
        self.scale = 20.0
        self.keys = set()
        self.draft = []
        self.cursor_world = (0, 0)
        self.vertex = None
        self.drag = None
        self.show_ranges = True
        self.zone_start = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(400, 350)

    def set_tool(self, tool):
        self.tool = tool
        self.draft.clear()
        self.drag = self.vertex = None
        self.zone_start = None
        self.setCursor(Qt.CursorShape.CrossCursor if tool in ("point", "line", "zone") else Qt.CursorShape.ArrowCursor)
        self.toolChanged.emit(tool)
        self.hintChanged.emit({
            "inspect": "Up / Down forward / backward · Left / Right or Q / E turn · Wheel zooms",
            "point": "Click to place a sound point · Esc returns to Inspect",
            "line": "Click to add vertices · Enter or double-click finishes · Backspace undoes · Esc cancels",
            "vertices": "Select a line · Drag handles · Double-click a segment to insert · Delete removes a selected vertex",
            "zone": "Drag a rectangle to create a reverb zone · Inspect to move or resize · Esc cancels",
        }[tool])
        self.update()

    def select(self, identifier):
        self.selection = identifier
        self.vertex = None
        self.selected.emit(identifier)
        self.update()

    def to_screen(self, p):
        return QPointF(self.width() / 2 + (p[0] - self.scene.player.x) * self.scale,
                       self.height() / 2 - (p[1] - self.scene.player.y) * self.scale)

    def to_world(self, p):
        return (self.scene.player.x + (p.x() - self.width() / 2) / self.scale,
                self.scene.player.y - (p.y() - self.height() / 2) / self.scale)

    def fit(self):
        p = self.scene.player
        points = [point for e in self.scene.emitters for point in e.points]
        points += [(z.x, z.y) for z in self.scene.zones] + [(z.x + z.width, z.y + z.height) for z in self.scene.zones]
        extent_x = max((abs(x - p.x) for x, y in points), default=15) + 5
        extent_y = max((abs(y - p.y) for x, y in points), default=15) + 5
        self.scale = max(2, min(90, self.width() / (2 * extent_x), self.height() / (2 * extent_y)))
        self.update()

    def movement(self):
        k = self.keys
        forward = int(Qt.Key.Key_Up in k) - int(Qt.Key.Key_Down in k)
        dx, dy = direction(self.scene.player.heading)
        turn = int(bool(k & {Qt.Key.Key_E, Qt.Key.Key_Right})) - int(bool(k & {Qt.Key.Key_Q, Qt.Key.Key_Left}))
        return dx * forward, dy * forward, turn

    def wheelEvent(self, event):
        self.scale = max(2, min(100, self.scale * 1.15 ** (event.angleDelta().y() / 120)))
        self.update()
        event.accept()

    def focusOutEvent(self, event):
        self.keys.clear()
        self.drag = None
        self.zone_start = None
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in self.movement_keys or key in (Qt.Key.Key_Q, Qt.Key.Key_E):
            self.keys.add(key)
            event.accept()
        elif key == Qt.Key.Key_Escape:
            self.set_tool("inspect")
        elif key == Qt.Key.Key_Space:
            self.pauseRequested.emit()
        elif key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5):
            self.toolRequested.emit({Qt.Key.Key_1: "inspect", Qt.Key.Key_2: "point",
                                     Qt.Key.Key_3: "line", Qt.Key.Key_4: "vertices", Qt.Key.Key_5: "zone"}[key])
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.tool == "line":
            self.finish_line()
        elif key == Qt.Key.Key_Backspace and self.draft:
            self.draft.pop()
            self.update()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            e = self.scene.find(self.selection)
            if self.tool == "vertices" and self.vertex is not None and e:
                if len(e.points) > 2:
                    e.points.pop(self.vertex)
                    self.vertex = None
                    self.edited.emit()
                    self.update()
                else:
                    self.hintChanged.emit("A line needs at least two vertices")
            elif not self.draft:
                self.deleteRequested.emit()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.keys.discard(event.key())
        event.accept()

    def hit(self, point):
        player = self.scene.player
        if math.dist(point, (player.x, player.y)) * self.scale < 17:
            return "player"
        for e in reversed(self.scene.emitters):
            pos, _ = e.sample()
            if math.dist(point, pos) * self.scale < 13:
                return e.id
            if e.kind == "line":
                segments = list(zip(e.points, e.points[1:]))
                if e.motion == "loop":
                    segments.append((e.points[-1], e.points[0]))
                if any(math.dist(point, segment_projection(point, a, b)) * self.scale < 8 for a, b in segments):
                    return e.id
        for z in reversed(self.scene.zones):
            if z.x <= point[0] <= z.x + z.width and z.y <= point[1] <= z.y + z.height:
                return z.id
        return ""

    def mousePressEvent(self, event):
        self.setFocus()
        point = self.to_world(event.position())
        if event.button() == Qt.MouseButton.RightButton:
            self.draft.clear()
            self.drag = None
            self.zone_start = None
            self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.tool == "zone":
            self.zone_start = self.cursor_world = point
            return
        if self.tool == "point":
            e = Emitter(name=f"Point {len(self.scene.emitters) + 1}", points=[list(point)])
            self.added.emit(e)
            return
        if self.tool == "line":
            if not self.draft or math.dist(self.draft[-1], point) > 0.01:
                self.draft.append(point)
            self.update()
            return
        e = self.scene.find(self.selection)
        z = self.scene.find_zone(self.selection)
        if z and self.tool == "inspect":
            corners = self.zone_corners(z)
            for index, corner in enumerate(corners):
                if math.dist(corner, point) * self.scale < 10:
                    self.drag = ("zone-resize", z, corners[(index + 2) % 4])
                    return
        if self.tool == "vertices" and e and e.kind == "line":
            nearest = min(range(len(e.points)), key=lambda i: math.dist(point, e.points[i]))
            if math.dist(point, e.points[nearest]) * self.scale < 12:
                self.vertex = nearest
                self.drag = ("vertex", e, nearest)
                self.update()
                return
        hit = self.hit(point)
        self.select(hit)
        e = self.scene.find(hit)
        if e and self.tool == "inspect":
            self.drag = ("object", e, point, [p[:] for p in e.points])
        z = self.scene.find_zone(hit)
        if z and self.tool == "inspect":
            self.drag = ("zone", z, point, (z.x, z.y))

    def mouseMoveEvent(self, event):
        point = self.to_world(event.position())
        self.cursor_world = point
        if self.drag:
            kind, e, *details = self.drag
            if kind == "zone":
                origin, original = details
                e.x, e.y = original[0] + point[0] - origin[0], original[1] + point[1] - origin[1]
            elif kind == "zone-resize":
                opposite = details[0]
                e.x, e.y = min(opposite[0], point[0]), min(opposite[1], point[1])
                e.width, e.height = max(0.1, abs(point[0] - opposite[0])), max(0.1, abs(point[1] - opposite[1]))
            elif kind == "vertex":
                e.points[details[0]] = list(point)
            else:
                origin, original = details
                e.points = [[p[0] + point[0] - origin[0], p[1] + point[1] - origin[1]] for p in original]
            self.edited.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.zone_start is not None and event.button() == Qt.MouseButton.LeftButton:
            a, b = self.zone_start, self.to_world(event.position())
            self.zone_start = None
            if abs(a[0] - b[0]) >= 0.5 and abs(a[1] - b[1]) >= 0.5:
                self.added.emit(ReverbZone(name=f"Zone {len(self.scene.zones) + 1}",
                    x=min(a[0], b[0]), y=min(a[1], b[1]), width=abs(a[0] - b[0]), height=abs(a[1] - b[1])))
        self.drag = None
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.tool == "line":
            self.finish_line()
        elif self.tool == "vertices":
            e = self.scene.find(self.selection)
            if e and e.kind == "line":
                point = self.to_world(event.position())
                segments = list(zip(e.points, e.points[1:]))
                if e.motion == "loop":
                    segments.append((e.points[-1], e.points[0]))
                projected = [segment_projection(point, a, b) for a, b in segments]
                index = min(range(len(projected)), key=lambda i: math.dist(point, projected[i]))
                if math.dist(point, projected[index]) * self.scale < 12:
                    e.points.insert(index + 1, list(projected[index]))
                    self.vertex = index + 1
                    self.drag = None
                    self.edited.emit()
                    self.update()

    def finish_line(self):
        if len(self.draft) < 2:
            return
        e = Emitter(name=f"Path {len(self.scene.emitters) + 1}", kind="line", points=[list(p) for p in self.draft])
        self.draft.clear()
        self.added.emit(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101923"))
        self._grid(p)
        for zone in self.scene.zones:
            self._zone(p, zone)
        if self.zone_start is not None:
            p.setPen(QPen(QColor("#be9cff"), 2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(160, 120, 220, 25))
            p.drawRect(QRectF(self.to_screen(self.zone_start), self.to_screen(self.cursor_world)).normalized())
        for e in self.scene.emitters:
            self._emitter(p, e)
        if self.draft:
            path = QPainterPath(self.to_screen(self.draft[0]))
            for vertex in [*self.draft[1:], self.cursor_world]:
                path.lineTo(self.to_screen(vertex))
            p.setPen(QPen(QColor("#74dcb9"), 2, Qt.PenStyle.DashLine))
            p.drawPath(path)
            for v in self.draft:
                p.drawEllipse(self.to_screen(v), 4, 4)
        self._player(p)
        self._overlay(p)
        p.end()

    def _grid(self, p):
        step = 5 if self.scale >= 10 else 10 if self.scale >= 5 else 25
        low = self.to_world(QPointF(0, self.height()))
        high = self.to_world(QPointF(self.width(), 0))
        p.setFont(QFont("Segoe UI", 8))
        for axis in (0, 1):
            for n in range(math.floor(low[axis] / step), math.ceil(high[axis] / step) + 1):
                value = n * step
                p.setPen(QPen(QColor("#2a3c4a" if value == 0 else "#1c2b38"), 1))
                if axis == 0:
                    pixel = self.to_screen((value, 0)).x()
                    p.drawLine(QPointF(pixel, 0), QPointF(pixel, self.height()))
                    p.setPen(QColor("#566d7d"))
                    p.drawText(QPointF(pixel + 4, self.height() - 38), str(value))
                else:
                    pixel = self.to_screen((0, value)).y()
                    p.drawLine(QPointF(0, pixel), QPointF(self.width(), pixel))
                    p.setPen(QColor("#566d7d"))
                    p.drawText(QPointF(8, pixel - 4), str(value))

    def _emitter(self, p, e):
        selected = self.selection == e.id
        color = QColor("#79dbb7" if e.kind == "point" else "#ecbb70") if e.enabled else QColor("#67717d")
        pos, velocity = e.sample()
        center = self.to_screen(pos)
        if selected and self.show_ranges:
            p.setBrush(QColor(color.red(), color.green(), color.blue(), 10))
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 70), 1, Qt.PenStyle.DashLine))
            r = min(20000, e.radius * self.scale)
            p.drawEllipse(center, r, r)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for dist in (e.reference_distance, e.max_distance):
                r = min(20000, dist * self.scale)
                p.drawEllipse(center, r, r)
            if e.directional and e.cone_outer < 360:
                heading = e.facing()
                cone = QPainterPath(center)
                r = min(e.max_distance * self.scale, 250)
                for i in range(33):
                    dx, dy = direction(heading - e.cone_outer / 2 + e.cone_outer * i / 32)
                    cone.lineTo(center + QPointF(dx * r, -dy * r))
                cone.closeSubpath()
                p.setBrush(QColor(color.red(), color.green(), color.blue(), 25))
                p.drawPath(cone)
        if e.kind == "line":
            path = QPainterPath(self.to_screen(e.points[0]))
            for point in e.points[1:]:
                path.lineTo(self.to_screen(point))
            if e.motion == "loop":
                path.closeSubpath()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 35), 10 if selected else 6))
            p.drawPath(path)
            p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine if e.enabled else Qt.PenStyle.DashLine))
            p.drawPath(path)
            if selected and self.tool == "vertices":
                for index, point in enumerate(e.points):
                    c = self.to_screen(point)
                    p.setPen(QPen(color, 2))
                    p.setBrush(color if index == self.vertex else QColor("#14212d"))
                    p.drawRect(QRectF(c.x() - 5, c.y() - 5, 10, 10))
                    p.drawText(c + QPointF(9, -9), str(index + 1))
        p.setPen(QPen(color, 2))
        p.setBrush(QColor("#14212d"))
        p.drawEllipse(center, 10 if selected else 8, 10 if selected else 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(center, 3, 3)
        if e.directional:
            p.save()
            p.translate(center)
            p.rotate(e.facing())
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(0, -11), QPointF(0, -34))
            p.drawLine(QPointF(0, -34), QPointF(-5, -26))
            p.drawLine(QPointF(0, -34), QPointF(5, -26))
            p.restore()
        p.setPen(color)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
        p.drawText(center + QPointF(15, -12), e.name)
        if selected:
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(center + QPointF(15, 5), f"{e.altitude:g} m altitude")

    @staticmethod
    def zone_corners(z):
        return [(z.x, z.y), (z.x + z.width, z.y),
                (z.x + z.width, z.y + z.height), (z.x, z.y + z.height)]

    def _zone(self, p, z):
        colors = {"cave": "#b69ae5", "hall": "#71b6da", "outdoor": "#76bf87"}
        color = QColor(colors[z.preset] if z.enabled else "#67717d")
        selected = self.selection == z.id
        rect = QRectF(self.to_screen((z.x, z.y)), self.to_screen((z.x + z.width, z.y + z.height))).normalized()
        p.setPen(QPen(color, 2 if selected else 1, Qt.PenStyle.SolidLine if z.enabled else Qt.PenStyle.DashLine))
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 24))
        p.drawRect(rect)
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(rect.topLeft() + QPointF(8, 18), f"{z.name} · {z.preset.title()}")
        if selected:
            p.setBrush(color)
            for corner in self.zone_corners(z):
                c = self.to_screen(corner)
                p.drawRect(QRectF(c.x() - 4, c.y() - 4, 8, 8))

    def _player(self, p):
        center = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(QPen(QColor("#8abaff"), 1))
        p.setBrush(QColor(91, 153, 245, 20))
        p.drawEllipse(center, 26, 26)
        if self.selection == "player":
            p.drawEllipse(center, 32, 32)
        p.save()
        p.translate(center)
        p.rotate(self.scene.player.heading)
        p.setPen(QPen(QColor("#d2e5ff"), 1.5))
        p.setBrush(QColor("#80b4ff"))
        p.drawPolygon(QPolygonF([QPointF(0, -15), QPointF(10, 11), QPointF(0, 6), QPointF(-10, 11)]))
        p.restore()
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor("#9bbce6"))
        p.drawText(center + QPointF(36, 5), "YOU")

    def _overlay(self, p):
        p.setPen(QColor("#e0eaf4"))
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        p.drawText(QPointF(22, 34), "Spatial playground")
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor("#7e94a7"))
        p.drawText(QPointF(23, 55), "TOP VIEW  /  METRES     ·     N ↑")
        p.fillRect(QRectF(0, self.height() - 29, self.width(), 29), QColor("#131f2b"))
        player = self.scene.player
        p.setPen(QColor("#a3b8cc"))
        p.drawText(QPointF(14, self.height() - 10),
                   f"X {player.x:7.2f}    Y {player.y:7.2f}    ALT {player.altitude:.1f} m    HEADING {player.heading:.0f}°")
        pixels = 5 * self.scale
        if pixels < self.width() / 4:
            x, y = self.width() - pixels - 20, self.height() - 50
            p.drawLine(QPointF(x, y), QPointF(x + pixels, y))
            p.drawText(QPointF(x + pixels / 2 - 10, y - 6), "5 m")
