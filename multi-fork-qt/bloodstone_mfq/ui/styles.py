"""Bloodstone dark theme for Multi-Fork Qt."""

APP_STYLESHEET = """
QWidget {
    background-color: #0f1419;
    color: #e7ecf3;
    font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #0f1419;
}
QListWidget {
    background-color: #151b24;
    border: 1px solid #243041;
    border-radius: 8px;
    outline: none;
    padding: 4px;
}
QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 0;
}
QListWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #1a2738;
}
QTabWidget::pane {
    border: 1px solid #243041;
    border-radius: 8px;
    top: -1px;
    background: #121820;
}
QTabBar::tab {
    background: #151b24;
    color: #9aa7b8;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #243041;
}
QTabBar::tab:selected {
    background: #1e3a5f;
    color: #ffffff;
    border-bottom-color: #1e3a5f;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0c1016;
    border: 1px solid #2a3a50;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #2d5a8a;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #4a90d9;
}
QPushButton {
    background-color: #1e4d7b;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2863a0;
}
QPushButton:pressed {
    background-color: #163a5c;
}
QPushButton:disabled {
    background-color: #2a3340;
    color: #6a7685;
}
QPushButton#dangerBtn {
    background-color: #8b2e2e;
}
QPushButton#dangerBtn:hover {
    background-color: #a83a3a;
}
QPushButton#secondaryBtn {
    background-color: #243041;
}
QPushButton#secondaryBtn:hover {
    background-color: #2f3f55;
}
QTableWidget {
    background-color: #121820;
    gridline-color: #243041;
    border: 1px solid #243041;
    border-radius: 8px;
}
QHeaderView::section {
    background-color: #151b24;
    color: #9aa7b8;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #243041;
    font-weight: 600;
}
QTableWidget::item {
    padding: 6px;
}
QTableWidget::item:selected {
    background-color: #1e3a5f;
}
QGroupBox {
    border: 1px solid #243041;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8ab4e8;
}
QLabel#titleLabel {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#balanceLabel {
    font-size: 28px;
    font-weight: 700;
    color: #6ec6ff;
}
QLabel#mutedLabel {
    color: #8a96a8;
}
QLabel#onlineDot {
    color: #3dce7a;
    font-weight: 700;
}
QLabel#offlineDot {
    color: #e06060;
    font-weight: 700;
}
QStatusBar {
    background: #0c1016;
    color: #8a96a8;
    border-top: 1px solid #243041;
}
QScrollBar:vertical {
    background: #0f1419;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2a3a50;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QToolTip {
    background-color: #1a2738;
    color: #e7ecf3;
    border: 1px solid #2a3a50;
    padding: 4px;
}
"""
