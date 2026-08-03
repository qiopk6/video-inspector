from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QWidget,
)

from app.core.analyzer import VideoAnalyzer
from app.core.models import AnalysisResult, Severity
from app.core.report import STATUS_TEXT, export_html, export_json
from app.ui.worker import AnalysisThread


VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".m4v",
    ".mts", ".m2ts", ".ts", ".mpg", ".mpeg", ".3gp", ".vob", ".mxf",
}

STATUS_COLORS = {
    Severity.PASS: QColor("#14733b"),
    Severity.WARNING: QColor("#9a5b00"),
    Severity.FAILURE: QColor("#b3261e"),
    Severity.INFO: QColor("#5f6368"),
}


class MainWindow(QMainWindow):
    def __init__(self, analyzer: VideoAnalyzer) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.paths: list[Path] = []
        self.results: dict[int, AnalysisResult] = {}
        self.worker: AnalysisThread | None = None
        self.setWindowTitle("Video Inspector - 本地视频质检")
        self.resize(1180, 760)
        self.setMinimumSize(860, 560)
        self.setAcceptDrops(True)
        self._build_toolbar()
        self._build_content()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("添加视频文件后即可开始检测")
        self._update_actions()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主要操作")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        self.add_files_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "添加文件", self)
        self.add_files_action.setToolTip("添加一个或多个视频文件")
        self.add_files_action.triggered.connect(self._choose_files)
        toolbar.addAction(self.add_files_action)

        self.add_folder_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "添加文件夹", self)
        self.add_folder_action.setToolTip("递归添加文件夹内的视频")
        self.add_folder_action.triggered.connect(self._choose_folder)
        toolbar.addAction(self.add_folder_action)

        self.remove_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "移除", self)
        self.remove_action.setToolTip("移除选中的队列项目")
        self.remove_action.triggered.connect(self._remove_selected)
        toolbar.addAction(self.remove_action)
        toolbar.addSeparator()

        self.start_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "开始检测", self)
        self.start_action.setToolTip("检测队列中尚未完成的视频")
        self.start_action.triggered.connect(self._start_analysis)
        toolbar.addAction(self.start_action)

        self.cancel_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop), "取消", self)
        self.cancel_action.setToolTip("取消当前批量检测")
        self.cancel_action.triggered.connect(self._cancel_analysis)
        toolbar.addAction(self.cancel_action)
        toolbar.addSeparator()

        self.export_html_action = QAction("导出 HTML", self)
        self.export_html_action.triggered.connect(lambda: self._export("html"))
        toolbar.addAction(self.export_html_action)
        self.export_json_action = QAction("导出 JSON", self)
        self.export_json_action.triggered.connect(lambda: self._export("json"))
        toolbar.addAction(self.export_json_action)

    def _build_content(self) -> None:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["状态", "文件名", "时长", "分辨率", "评分", "进度", "路径"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_selected_details)
        splitter.addWidget(self.table)

        self.tabs = QTabWidget()
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.details.setHtml("<p style='color:#6b7075'>选择队列中的文件查看检测详情。</p>")
        self.log_view = QTextBrowser()
        self.tabs.addTab(self.details, "检测详情")
        self.tabs.addTab(self.log_view, "FFmpeg 日志")
        splitter.addWidget(self.tabs)
        splitter.setSizes([470, 250])
        self.setCentralWidget(splitter)

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            QDir.homePath(),
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.wmv *.flv *.webm *.m4v *.mts *.m2ts *.ts *.mpg *.mpeg *.3gp *.vob *.mxf);;所有文件 (*)",
        )
        self._add_paths([Path(item) for item in files])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹", QDir.homePath())
        if folder:
            paths = [item for item in Path(folder).rglob("*") if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS]
            self._add_paths(paths)

    def _add_paths(self, candidates: list[Path]) -> None:
        existing = {str(path.resolve()).lower() for path in self.paths}
        added = 0
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            key = str(path.resolve()).lower()
            if key in existing:
                continue
            existing.add(key)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.paths.append(path.resolve())
            self.table.setItem(row, 0, QTableWidgetItem("待检测"))
            self.table.setItem(row, 1, QTableWidgetItem(path.name))
            self.table.setItem(row, 2, QTableWidgetItem("-"))
            self.table.setItem(row, 3, QTableWidgetItem("-"))
            self.table.setItem(row, 4, QTableWidgetItem("-"))
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            progress.setTextVisible(True)
            self.table.setCellWidget(row, 5, progress)
            self.table.setItem(row, 6, QTableWidgetItem(str(path.resolve())))
            added += 1
        if added:
            self.statusBar().showMessage(f"已添加 {added} 个视频，共 {len(self.paths)} 个")
        self._update_actions()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            self.paths.pop(row)
        if rows:
            old_results = self.results
            removed = set(rows)
            self.results = {}
            new_row = 0
            for old_row in range(len(self.paths) + len(rows)):
                if old_row in removed:
                    continue
                if old_row in old_results:
                    self.results[new_row] = old_results[old_row]
                new_row += 1
        self._update_actions()

    def _start_analysis(self) -> None:
        rows = [row for row in range(len(self.paths)) if row not in self.results]
        if not rows:
            return
        self.worker = AnalysisThread(self.analyzer, [self.paths[row] for row in rows], rows)
        self.worker.item_started.connect(self._item_started)
        self.worker.item_progress.connect(self._item_progress)
        self.worker.item_completed.connect(self._item_completed)
        self.worker.item_failed.connect(self._item_failed)
        self.worker.batch_cancelled.connect(lambda: self.statusBar().showMessage("检测已取消"))
        self.worker.finished.connect(self._batch_finished)
        self.worker.start()
        self.statusBar().showMessage(f"正在检测 {len(rows)} 个视频...")
        self._update_actions()

    def _cancel_analysis(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.statusBar().showMessage("正在取消...")

    def _item_started(self, row: int) -> None:
        self.table.item(row, 0).setText("检测中")

    def _item_progress(self, row: int, value: int) -> None:
        widget = self.table.cellWidget(row, 5)
        if isinstance(widget, QProgressBar):
            widget.setValue(value)

    def _item_completed(self, row: int, result: AnalysisResult) -> None:
        self.results[row] = result
        status_item = self.table.item(row, 0)
        status_item.setText(STATUS_TEXT[result.status])
        status_item.setForeground(STATUS_COLORS[result.status])
        status_item.setData(Qt.ItemDataRole.UserRole, result.status.value)
        metadata = result.metadata
        self.table.item(row, 2).setText(self._format_duration(metadata.duration))
        self.table.item(row, 3).setText(f"{metadata.width}x{metadata.height}")
        self.table.item(row, 4).setText(str(result.score))
        self._item_progress(row, 100)
        if self.table.currentRow() == row:
            self._show_result(result)

    def _item_failed(self, row: int, message: str) -> None:
        item = self.table.item(row, 0)
        item.setText("错误")
        item.setForeground(STATUS_COLORS[Severity.FAILURE])
        self.statusBar().showMessage(f"{self.paths[row].name}：{message}")

    def _batch_finished(self) -> None:
        completed = len(self.results)
        self.worker = None
        self.statusBar().showMessage(f"检测结束，已完成 {completed}/{len(self.paths)} 个")
        self._update_actions()

    def _show_selected_details(self) -> None:
        row = self.table.currentRow()
        result = self.results.get(row)
        if result:
            self._show_result(result)
        elif row >= 0:
            self.details.setHtml("<p style='color:#6b7075'>该文件尚未完成检测。</p>")
            self.log_view.clear()

    def _show_result(self, result: AnalysisResult) -> None:
        metadata = result.metadata
        finding_html = []
        for finding in result.findings:
            color = STATUS_COLORS[finding.severity].name()
            segments = ""
            if finding.segments:
                segments = "<br><span style='color:#6b7075'>" + "；".join(
                    f"{self._format_duration(item.start)} - {self._format_duration(item.end)}"
                    for item in finding.segments
                ) + "</span>"
            finding_html.append(
                f"<tr><td style='color:{color};font-weight:600'>{STATUS_TEXT[finding.severity]}</td>"
                f"<td><b>{finding.title}</b><br>{finding.message}{segments}</td></tr>"
            )
        self.details.setHtml(
            f"<h2 style='margin:4px 0'>{metadata.filename}</h2>"
            f"<p style='color:#5f6368'>{metadata.format_name} · {self._format_duration(metadata.duration)} · "
            f"{metadata.width}x{metadata.height} · {metadata.frame_rate:.2f} fps · 评分 {result.score}</p>"
            "<table cellspacing='0' cellpadding='7' width='100%'>"
            f"{''.join(finding_html)}</table>"
        )
        self.log_view.setPlainText(result.raw_log)

    def _export(self, format_name: str) -> None:
        completed = [self.results[row] for row in sorted(self.results)]
        if not completed:
            return
        suffix = ".html" if format_name == "html" else ".json"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出检测报告", str(Path.home() / f"video-inspector-report{suffix}"),
            "HTML 报告 (*.html)" if format_name == "html" else "JSON 数据 (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != suffix:
            destination = destination.with_suffix(suffix)
        try:
            (export_html if format_name == "html" else export_json)(completed, destination)
            self.statusBar().showMessage(f"报告已导出：{destination}")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _update_actions(self) -> None:
        running = bool(self.worker and self.worker.isRunning())
        has_rows = bool(self.paths)
        has_results = bool(self.results)
        self.add_files_action.setEnabled(not running)
        self.add_folder_action.setEnabled(not running)
        self.remove_action.setEnabled(has_rows and not running)
        self.start_action.setEnabled(has_rows and len(self.results) < len(self.paths) and not running)
        self.cancel_action.setEnabled(running)
        self.export_html_action.setEnabled(has_results and not running)
        self.export_json_action.setEnabled(has_results and not running)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        candidates: list[Path] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                candidates.extend(item for item in path.rglob("*") if item.is_file())
            else:
                candidates.append(path)
        self._add_paths(candidates)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(self, "检测正在运行", "确定要取消检测并退出吗？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
        event.accept()

    @staticmethod
    def _format_duration(seconds: float) -> str:
        minutes, seconds = divmod(max(0.0, seconds), 60)
        hours, minutes = divmod(int(minutes), 60)
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d}"
