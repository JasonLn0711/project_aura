import logging
import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from aura.ui.main_window import MainWindow


AURA_STYLE = """
QWidget {
    font-family: "Noto Sans CJK TC", "Segoe UI", sans-serif;
}
QMainWindow, QTabWidget::pane {
    background: #0f151c;
}
QWidget#transcriptionWorkspace,
QWidget#splitterWorkspace {
    background: #0f151c;
}
QTabWidget::pane {
    border: 0;
}
QTabBar::tab {
    background: transparent;
    color: #8393a4;
    min-width: 150px;
    padding: 12px 18px;
    border: 0;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #e9f1f6;
    border-bottom-color: #48c7b8;
}
QTabBar::tab:hover:!selected {
    color: #b9c6d2;
    background: #141c25;
}
QFrame#workspaceHeader,
QFrame#sidePanel,
QFrame#mainPanel,
QFrame#splitterPanel {
    background: #151e27;
    border: 1px solid #273442;
    border-radius: 10px;
}
QLabel#workspaceStatus {
    color: #e9f1f6;
    font-size: 14px;
    font-weight: 600;
}
QLabel#statusChip {
    background: #0f171f;
    color: #aebdca;
    border: 1px solid #2b3947;
    border-radius: 8px;
    padding: 6px 10px;
}
QLabel[role="sectionTitle"] {
    color: #e7eef4;
    font-size: 13px;
    font-weight: 600;
}
QLabel[role="muted"] {
    color: #8798a8;
}
QLabel[role="eyebrow"] {
    color: #48c7b8;
    font-size: 11px;
    font-weight: 600;
}
QPushButton {
    min-height: 36px;
    padding: 7px 12px;
    color: #d9e4ec;
    background: #202c38;
    border: 1px solid #314152;
    border-radius: 7px;
    font-weight: 500;
}
QPushButton:hover:enabled {
    background: #283746;
    border-color: #486074;
}
QPushButton:pressed:enabled {
    background: #1a2530;
}
QPushButton:focus {
    border: 2px solid #65d5c8;
}
QPushButton:disabled {
    color: #5f6d7a;
    background: #172029;
    border-color: #24313d;
}
QPushButton[role="primary"] {
    color: #071512;
    background: #48c7b8;
    border-color: #48c7b8;
    font-weight: 700;
}
QPushButton[role="primary"]:hover:enabled {
    background: #61d3c5;
    border-color: #61d3c5;
}
QPushButton[role="primary"]:disabled {
    color: #5f6d7a;
    background: #172029;
    border-color: #24313d;
}
QPushButton[role="danger"] {
    color: #fff4f2;
    background: #b84f52;
    border-color: #d86b6e;
    font-weight: 700;
}
QPushButton[role="scheduled"] {
    color: #f5f8fa;
    background: #476479;
    border-color: #5f7f96;
    font-weight: 700;
}
QPushButton[role="quiet"] {
    background: transparent;
    border-color: #2b3947;
}
QPushButton[role="quiet"]:checked {
    color: #d9e4ec;
    background: #1a2530;
    border-color: #3a4c5d;
}
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QTextEdit, QTableWidget {
    color: #e3ebf1;
    background: #0f171f;
    border: 1px solid #2d3b49;
    border-radius: 7px;
    padding: 6px 8px;
    selection-background-color: #327d76;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTimeEdit:focus, QTextEdit:focus, QTableWidget:focus {
    border: 1px solid #48c7b8;
}
QTableWidget#transcriptArea {
    font-size: 13px;
    gridline-color: #24313d;
    alternate-background-color: #121d26;
}
QTableWidget#transcriptArea::item {
    padding: 8px;
}
QTableWidget#transcriptArea QHeaderView::section {
    color: #b9c8d3;
    background: #17222c;
    border: 0;
    border-bottom: 1px solid #324252;
    padding: 8px;
    font-weight: 700;
}
QTextEdit#runtimeLog {
    font-family: "Noto Sans Mono", "Consolas", monospace;
    color: #9bb8b4;
    background: #0b1117;
    font-size: 11px;
}
QScrollArea#settingsScroll {
    background: transparent;
    border: 0;
}
QScrollArea#settingsScroll > QWidget > QWidget {
    background: transparent;
}
QSplitter::handle {
    background: transparent;
    image: none;
    width: 8px;
}
QSplitter::handle:hover {
    background: #24323f;
}
QProgressBar {
    min-height: 7px;
    max-height: 7px;
    padding: 0;
    border: 0;
    border-radius: 3px;
    background: #26323d;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #48c7b8;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #344555;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QStatusBar {
    color: #80909e;
    background: #111820;
    border-top: 1px solid #222f3a;
}
"""


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="dark_teal.xml")
    app.setFont(QFont("Noto Sans CJK TC", 10))
    app.setStyleSheet(app.styleSheet() + AURA_STYLE)

    window = MainWindow()
    window.show()
    return app.exec()
