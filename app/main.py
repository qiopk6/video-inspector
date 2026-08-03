from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.core.analyzer import VideoAnalyzer
from app.core.config import load_rules
from app.core.ffmpeg_locator import locate_ffmpeg
from app.ui.main_window import MainWindow


STYLE = """
QMainWindow { background: #f4f5f6; }
QToolBar { background: #ffffff; border: 0; border-bottom: 1px solid #d9dcdf; spacing: 4px; padding: 6px; }
QToolButton { min-height: 28px; padding: 2px 8px; border: 1px solid transparent; border-radius: 4px; }
QToolButton:hover { background: #edf0f2; border-color: #d7dade; }
QToolButton:pressed { background: #e2e5e8; }
QTableWidget { background: white; alternate-background-color: #f7f8f9; border: 0; gridline-color: #e2e4e6; }
QHeaderView::section { background: #eceff1; color: #34383c; border: 0; border-right: 1px solid #d9dcdf; border-bottom: 1px solid #cfd3d6; padding: 7px; font-weight: 600; }
QTableWidget::item { padding: 5px; }
QTableWidget::item:selected { background: #dce8f5; color: #202124; }
QTabWidget::pane { background: white; border: 1px solid #d9dcdf; }
QTabBar::tab { background: #e9ecee; padding: 7px 16px; border: 1px solid #d9dcdf; border-bottom: 0; }
QTabBar::tab:selected { background: white; }
QTextBrowser { background: white; border: 0; padding: 8px; }
QProgressBar { min-width: 100px; max-width: 130px; min-height: 17px; border: 1px solid #c8ccd0; border-radius: 3px; text-align: center; background: white; }
QProgressBar::chunk { background: #2f6f9f; }
QStatusBar { background: #ffffff; border-top: 1px solid #d9dcdf; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Video Inspector")
    app.setOrganizationName("Local Tools")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    try:
        tools = locate_ffmpeg()
    except FileNotFoundError as initial_error:
        answer = QMessageBox.question(
            None,
            "需要 FFmpeg",
            f"{initial_error}\n\n是否现在选择包含 ffmpeg.exe 和 ffprobe.exe 的文件夹？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return 1
        folder = QFileDialog.getExistingDirectory(None, "选择 FFmpeg bin 文件夹")
        if not folder:
            return 1
        try:
            tools = locate_ffmpeg(Path(folder))
        except FileNotFoundError as exc:
            QMessageBox.critical(None, "FFmpeg 不可用", str(exc))
            return 1

    window = MainWindow(VideoAnalyzer(tools, load_rules()))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
