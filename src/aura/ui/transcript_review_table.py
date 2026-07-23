from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from aura.review import (
    CONFIRMED,
    LOW_CONFIDENCE_FLAG,
    PROVISIONAL,
    SPEAKER_OVERLAP_FLAG,
    UNKNOWN_SPEAKER,
    UNKNOWN_SPEAKER_FLAG,
    ReviewSegment,
    TranscriptReview,
    parse_transcript_lines,
    stable_segment_id,
)


SUMMARY_MARKER = "===== LLM Summary ====="
REVIEW_FLAG_LABELS = {
    UNKNOWN_SPEAKER_FLAG: "講者",
    SPEAKER_OVERLAP_FLAG: "重疊",
    LOW_CONFIDENCE_FLAG: "低信心",
}


def display_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, int(milliseconds)) // 1000, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class TranscriptReviewTable(QTableWidget):
    TIME_COLUMN = 0
    SPEAKER_COLUMN = 1
    TEXT_COLUMN = 2
    STATE_COLUMN = 3

    seek_requested = pyqtSignal(int)
    review_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(0, 4, parent)
        self.review = TranscriptReview()
        self.summary_text = ""
        self._updating = False
        self.setHorizontalHeaderLabels(["時間", "講者", "逐字稿", "確認"])
        self.horizontalHeader().setSectionResizeMode(self.TIME_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(self.SPEAKER_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(self.TEXT_COLUMN, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(self.STATE_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setAccessibleName("逐字稿覆核表")
        self.setToolTip("雙擊任一列可從該段時間播放；可直接修正講者與逐字稿並勾選確認。")
        self.cellChanged.connect(self._on_cell_changed)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

    def set_segments(
        self,
        segments: list[ReviewSegment],
        *,
        clear_summary: bool = True,
    ) -> None:
        self.review = TranscriptReview(segments)
        if clear_summary:
            self.summary_text = ""
        self._render()

    def _render(self) -> None:
        self._updating = True
        try:
            self.setRowCount(len(self.review.segments))
            for row, segment in enumerate(self.review.segments):
                self._render_row(row, segment)
        finally:
            self._updating = False

    def _render_row(self, row: int, segment: ReviewSegment) -> None:
        time_item = QTableWidgetItem(display_timestamp(segment.start_ms))
        time_item.setData(Qt.ItemDataRole.UserRole, segment.segment_id)
        time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, self.TIME_COLUMN, time_item)
        self.setItem(row, self.SPEAKER_COLUMN, QTableWidgetItem(segment.speaker))
        self.setItem(row, self.TEXT_COLUMN, QTableWidgetItem(segment.text))
        pending_flags = "／".join(
            REVIEW_FLAG_LABELS[flag]
            for flag in segment.review_flags
            if flag in REVIEW_FLAG_LABELS
        )
        state_text = (
            "已確認"
            if segment.state == CONFIRMED
            else f"待確認：{pending_flags}" if pending_flags else "待確認"
        )
        state_item = QTableWidgetItem(state_text)
        state_item.setFlags(
            (state_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable
        )
        state_item.setCheckState(
            Qt.CheckState.Checked if segment.state == CONFIRMED else Qt.CheckState.Unchecked
        )
        self.setItem(row, self.STATE_COLUMN, state_item)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._updating or not 0 <= row < len(self.review.segments):
            return
        segment = self.review.segments[row]
        if column == self.SPEAKER_COLUMN:
            updated = self.review.edit(segment.segment_id, speaker=self.item(row, column).text())
        elif column == self.TEXT_COLUMN:
            updated = self.review.edit(segment.segment_id, text=self.item(row, column).text())
        elif column == self.STATE_COLUMN:
            if self.item(row, column).checkState() != Qt.CheckState.Checked:
                self._updating = True
                try:
                    self._render_row(row, segment)
                finally:
                    self._updating = False
                return
            updated = self.review.confirm(segment.segment_id)
        else:
            return
        self._updating = True
        try:
            self._render_row(row, updated)
        finally:
            self._updating = False
        self.review_changed.emit(updated)

    def confirm_row(self, row: int) -> None:
        if not 0 <= row < len(self.review.segments):
            return
        updated = self.review.confirm(self.review.segments[row].segment_id)
        self._updating = True
        try:
            self._render_row(row, updated)
        finally:
            self._updating = False
        self.review_changed.emit(updated)

    def rename_speaker(self, current_name: str, new_name: str) -> int:
        changed = self.review.rename_speaker(current_name, new_name)
        if changed:
            self._render()
            self.review_changed.emit({"speaker": new_name, "changed_segments": changed})
        return changed

    def _on_cell_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.review.segments):
            self.seek_requested.emit(self.review.segments[row].start_ms)

    def select_segment(self, segment_id: str) -> ReviewSegment | None:
        for row, segment in enumerate(self.review.segments):
            if segment.segment_id == segment_id:
                self.selectRow(row)
                self.scrollToItem(self.item(row, self.TEXT_COLUMN))
                return segment
        return None

    def select_next_pending(self) -> ReviewSegment | None:
        count = len(self.review.segments)
        if not count:
            return None
        start = self.currentRow()
        for offset in range(1, count + 1):
            row = (start + offset) % count
            segment = self.review.segments[row]
            if segment.state != CONFIRMED:
                self.selectRow(row)
                self.scrollToItem(self.item(row, self.TEXT_COLUMN))
                return segment
        return None

    def append(self, content: str) -> None:
        cleaned = str(content).strip()
        if not cleaned:
            return
        if SUMMARY_MARKER in cleaned:
            self.summary_text = cleaned.split(SUMMARY_MARKER, 1)[1].strip()
            return
        for line in cleaned.splitlines():
            parsed = parse_transcript_lines([line], state=PROVISIONAL)
            if not parsed:
                continue
            item = parsed[0]
            index = len(self.review.segments)
            item = replace(item, segment_id=stable_segment_id(index, item.start_ms))
            if self.review.segments:
                previous = self.review.segments[-1]
                if previous.end_ms <= previous.start_ms and item.start_ms >= previous.start_ms:
                    self.review.segments[-1] = replace(previous, end_ms=item.start_ms)
            self.review.segments.append(item)
        self._render()
        self.scrollToBottom()

    def clear(self) -> None:
        self.review = TranscriptReview()
        self.summary_text = ""
        self.setRowCount(0)

    def toPlainText(self) -> str:
        lines = []
        for segment in self.review.segments:
            prefix = f"[{display_timestamp(segment.start_ms)}] [{segment.segment_id}] "
            if segment.speaker != UNKNOWN_SPEAKER:
                prefix += f"{segment.speaker}: "
            lines.append(prefix + segment.text)
        transcript = "\n".join(lines)
        if transcript and self.summary_text:
            return f"{transcript}\n\n{SUMMARY_MARKER}\n{self.summary_text}"
        if self.summary_text:
            return f"{SUMMARY_MARKER}\n{self.summary_text}"
        return transcript

    def setPlainText(self, content: str) -> None:
        cleaned = str(content).strip()
        if SUMMARY_MARKER in cleaned:
            transcript, summary = cleaned.split(SUMMARY_MARKER, 1)
            self.summary_text = summary.strip()
        else:
            transcript = cleaned
            self.summary_text = ""
        self.set_segments(
            parse_transcript_lines(transcript.splitlines()),
            clear_summary=False,
        )

    def setReadOnly(self, read_only: bool) -> None:
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
            if read_only
            else (
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.SelectedClicked
            )
        )

    def setFontPointSize(self, size: float) -> None:
        font = QFont(self.font())
        font.setPointSizeF(float(size))
        self.setFont(font)

    def setPlaceholderText(self, text: str) -> None:
        self.setAccessibleDescription(str(text))
