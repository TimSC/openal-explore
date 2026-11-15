"""Modeless, read-only view of the current OpenAL device and playback state."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit,
    QPushButton, QTabWidget, QVBoxLayout,
)


class AudioInfoDialog(QDialog):
    def __init__(self, audio, scene_provider, parent=None):
        super().__init__(parent)
        self.audio = audio
        self.scene_provider = scene_provider
        self.setWindowTitle("OpenAL Information")
        self.setModal(False)
        self.resize(820, 620)
        layout = QVBoxLayout(self)
        note = QLabel("Read-only · updates once per second while this window is open.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.views = {}
        for title in ("Overview", "Listener", "Sources", "AL extensions", "ALC extensions"):
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.views[title] = view
            self.tabs.addTab(view, title)
        layout.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons.addButton(refresh, QDialogButtonBox.ButtonRole.ActionRole)
        copy = QPushButton("Copy all")
        copy.clicked.connect(self.copy_all)
        buttons.addButton(copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)

    def refresh(self):
        for title, text in self.audio.diagnostics(self.scene_provider()).items():
            view = self.views[title]
            if view.toPlainText() != text:
                scroll = view.verticalScrollBar().value()
                horizontal = view.horizontalScrollBar().value()
                view.setPlainText(text)
                view.verticalScrollBar().setValue(scroll)
                view.horizontalScrollBar().setValue(horizontal)

    def copy_all(self):
        QApplication.clipboard().setText("\n\n".join(
            f"{title}\n{'=' * len(title)}\n{view.toPlainText()}" for title, view in self.views.items()))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
