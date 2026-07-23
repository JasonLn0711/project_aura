from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from aura.claim_review import load_claims, record_claim_edit, record_claim_review


class SummaryClaimsTable(QTableWidget):
    FIELD_COLUMN = 0
    CLAIM_COLUMN = 1
    SOURCE_COLUMN = 2
    SUPPORT_COLUMN = 3
    REVIEW_COLUMN = 4

    source_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.session_dir: Path | None = None
        self.claims: list[dict] = []
        self.setHorizontalHeaderLabels(["欄位", "摘要主張", "來源片段", "證據", "人工覆核"])
        self.horizontalHeader().setSectionResizeMode(
            self.CLAIM_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        for column in (
            self.FIELD_COLUMN,
            self.SOURCE_COLUMN,
            self.SUPPORT_COLUMN,
            self.REVIEW_COLUMN,
        ):
            self.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setAccessibleName("摘要主張與來源覆核表")
        self.setToolTip("雙擊來源片段可回到逐字稿並播放；確認或退回會留下覆核紀錄。")
        self.cellDoubleClicked.connect(self._request_source)

    def load_session(self, session_dir: str | Path) -> None:
        self.session_dir = Path(session_dir)
        self.claims = load_claims(self.session_dir)
        self._render()

    def clear_session(self) -> None:
        self.session_dir = None
        self.claims = []
        self.setRowCount(0)

    def _render(self) -> None:
        self.setRowCount(len(self.claims))
        for row, claim in enumerate(self.claims):
            sources = [str(item) for item in claim.get("source_segment_ids", [])]
            values = (
                str(claim.get("field") or ""),
                str(claim.get("text") or ""),
                ", ".join(sources),
                str(claim.get("support_status") or "unsupported"),
                str(claim.get("review_status") or "unreviewed"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, column, item)

    def review_selected(self, review_status: str) -> None:
        row = self.currentRow()
        if self.session_dir is None or not 0 <= row < len(self.claims):
            return
        claim_id = str(self.claims[row].get("claim_id") or "")
        self.claims[row] = record_claim_review(
            self.session_dir, claim_id, review_status
        )
        self.item(row, self.REVIEW_COLUMN).setText(review_status)

    def edit_selected(self, text: str) -> None:
        row = self.currentRow()
        if self.session_dir is None or not 0 <= row < len(self.claims):
            return
        claim_id = str(self.claims[row].get("claim_id") or "")
        self.claims[row] = record_claim_edit(self.session_dir, claim_id, text)
        self.item(row, self.CLAIM_COLUMN).setText(self.claims[row]["text"])

    def _request_source(self, row: int, _column: int) -> None:
        if not 0 <= row < len(self.claims):
            return
        sources = self.claims[row].get("source_segment_ids", [])
        if sources:
            self.source_requested.emit(str(sources[0]))
