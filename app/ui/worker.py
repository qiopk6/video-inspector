from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.core.analyzer import AnalysisCancelled, VideoAnalyzer


class AnalysisThread(QThread):
    item_started = Signal(int)
    item_progress = Signal(int, int)
    item_completed = Signal(int, object)
    item_failed = Signal(int, str)
    batch_cancelled = Signal()

    def __init__(self, analyzer: VideoAnalyzer, paths: list[Path], row_indexes: list[int]) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.paths = paths
        self.row_indexes = row_indexes
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            for path, row in zip(self.paths, self.row_indexes, strict=True):
                if self.cancel_event.is_set():
                    raise AnalysisCancelled("检测已取消")
                self.item_started.emit(row)
                try:
                    result = self.analyzer.analyze(
                        path,
                        progress=lambda fraction, current=row: self.item_progress.emit(current, round(fraction * 100)),
                        cancel_event=self.cancel_event,
                    )
                    self.item_completed.emit(row, result)
                except AnalysisCancelled:
                    raise
                except Exception as exc:
                    self.item_failed.emit(row, str(exc))
        except AnalysisCancelled:
            self.batch_cancelled.emit()
