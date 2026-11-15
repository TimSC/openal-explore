import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    app = QApplication.instance() or QApplication([])
    # The Windows offscreen plugin does not enumerate system fonts.
    if not QFontDatabase.families():
        for font in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"):
            if os.path.exists(font):
                QFontDatabase.addApplicationFont(font)
    yield app


@pytest.fixture
def demo(tmp_path):
    from openal_explore.demo import create_demo
    return create_demo(tmp_path / "samples")


@pytest.fixture
def audio():
    from openal_py import LoopbackDevice
    from openal_explore.audio import Audio
    with LoopbackDevice() as device:
        backend = Audio(device=device)
        assert backend.available, backend.error
        yield backend
        backend.close()
