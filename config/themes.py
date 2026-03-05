"""
TransfPro Application Themes — Professional Scientific Style

Clean, professional design optimised for long HPC work sessions.
Neutral dark palette with purposeful colour accents, flat controls,
tight spacing, and high readability.
"""

# ─────────────────────────────────────────────
#  Dark Theme  —  Professional Scientific
# ─────────────────────────────────────────────
DARK_THEME_QSS = """
/* ═══════════════════════════════════════════
   GLOBAL FOUNDATION
   ═══════════════════════════════════════════ */

* {
    font-family: 'SF Pro Text', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
}

QMainWindow {
    background-color: #1a1b26;
    color: #cad3f5;
}

QWidget {
    background-color: #1a1b26;
    color: #cad3f5;
}

/* ═══════════════════════════════════════════
   TAB BAR — Clean underline indicator
   ═══════════════════════════════════════════ */

QTabWidget {
    background-color: #1a1b26;
    border: none;
}

QTabWidget::pane {
    border: none;
    background-color: #1a1b26;
    margin-top: 0px;
}

QTabBar {
    background-color: #1e2030;
    border-bottom: 1px solid #363a4f;
    padding: 0px;
}

QTabBar::tab {
    background-color: transparent;
    color: #6e738d;
    padding: 8px 16px;
    margin: 0px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 600;
    min-width: 70px;
}

QTabBar::tab:selected {
    color: #cad3f5;
    border-bottom: 2px solid #0ea5e9;
    background-color: transparent;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    color: #a5adcb;
    border-bottom: 2px solid #363a4f;
}

/* ═══════════════════════════════════════════
   BUTTONS — Flat, purposeful
   ═══════════════════════════════════════════ */

QPushButton {
    background-color: #363a4f;
    color: #cad3f5;
    border: 1px solid #494d64;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #494d64;
    border: 1px solid #5b6078;
}

QPushButton:pressed {
    background-color: #2e3244;
}

QPushButton:disabled {
    background-color: #24273a;
    color: #494d64;
    border: 1px solid #363a4f;
}

QPushButton#primaryButton {
    background-color: #0ea5e9;
    color: #ffffff;
    border: none;
}

QPushButton#primaryButton:hover {
    background-color: #0284c7;
}

QPushButton#primaryButton:pressed {
    background-color: #0369a1;
}

QPushButton#dangerButton {
    background-color: #e11d48;
    color: #ffffff;
    border: none;
}

QPushButton#dangerButton:hover {
    background-color: #be123c;
}

QPushButton#successButton {
    background-color: #059669;
    color: #ffffff;
    border: none;
}

QPushButton#successButton:hover {
    background-color: #047857;
}

/* ═══════════════════════════════════════════
   INPUT FIELDS — Clean, subtle
   ═══════════════════════════════════════════ */

QLineEdit {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
}

QLineEdit:focus {
    border: 1px solid #0ea5e9;
}

QLineEdit:disabled {
    background-color: #1e2030;
    color: #494d64;
    border: 1px solid #2e3244;
}

QTextEdit, QPlainTextEdit {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0ea5e9;
}

/* ═══════════════════════════════════════════
   COMBO BOX
   ═══════════════════════════════════════════ */

QComboBox {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
}

QComboBox:hover {
    border: 1px solid #5b6078;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 4px;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
    padding: 2px;
}

/* ═══════════════════════════════════════════
   SPIN BOX
   ═══════════════════════════════════════════ */

QSpinBox, QDoubleSpinBox {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 13px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #0ea5e9;
}

/* ═══════════════════════════════════════════
   TABLE — Clean data grid
   ═══════════════════════════════════════════ */

QTableWidget, QTableView {
    background-color: #1e2030;
    alternate-background-color: #24273a;
    gridline-color: #2e3244;
    border: 1px solid #363a4f;
    border-radius: 6px;
    font-size: 13px;
}

QTableWidget::item, QTableView::item {
    padding: 6px 10px;
    border-bottom: 1px solid #2e3244;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: rgba(14, 165, 233, 0.2);
    color: #cad3f5;
}

QHeaderView::section {
    background-color: #1e2030;
    color: #6e738d;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #363a4f;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QHeaderView::section:hover {
    color: #a5adcb;
}

/* ═══════════════════════════════════════════
   LIST WIDGET
   ═══════════════════════════════════════════ */

QListWidget {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    color: #cad3f5;
    padding: 8px 10px;
    margin: 1px 0px;
    border-radius: 4px;
    border: none;
}

QListWidget::item:selected {
    background-color: rgba(14, 165, 233, 0.2);
    color: #ffffff;
}

QListWidget::item:hover:!selected {
    background-color: #24273a;
}

/* ═══════════════════════════════════════════
   TREE WIDGET
   ═══════════════════════════════════════════ */

QTreeWidget, QTreeView {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 2px;
}

QTreeWidget::item, QTreeView::item {
    padding: 4px 6px;
}

QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: rgba(14, 165, 233, 0.2);
}

QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #24273a;
}

/* ═══════════════════════════════════════════
   SCROLL BARS — Thin, neutral
   ═══════════════════════════════════════════ */

QScrollBar:vertical {
    background-color: transparent;
    width: 6px;
    border: none;
    margin: 2px 1px;
}

QScrollBar::handle:vertical {
    background-color: #494d64;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #6e738d;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 6px;
    border: none;
    margin: 1px 2px;
}

QScrollBar::handle:horizontal {
    background-color: #494d64;
    border-radius: 3px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #6e738d;
}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    border: none;
    background: none;
    height: 0;
    width: 0;
}

/* ═══════════════════════════════════════════
   PROGRESS BAR — Solid accent fill
   ═══════════════════════════════════════════ */

QProgressBar {
    background-color: #24273a;
    border: none;
    border-radius: 4px;
    padding: 0px;
    color: #ffffff;
    text-align: center;
    font-weight: 600;
    font-size: 11px;
    min-height: 14px;
}

QProgressBar::chunk {
    background-color: #0ea5e9;
    border-radius: 4px;
}

/* ═══════════════════════════════════════════
   LABELS
   ═══════════════════════════════════════════ */

QLabel {
    color: #cad3f5;
    background-color: transparent;
    font-size: 13px;
}

/* ═══════════════════════════════════════════
   GROUP BOX — Subtle card
   ═══════════════════════════════════════════ */

QGroupBox {
    color: #a5adcb;
    border: 1px solid #363a4f;
    border-radius: 8px;
    margin-top: 10px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    font-size: 13px;
    background-color: #1e2030;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 1px 8px;
    color: #6e738d;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ═══════════════════════════════════════════
   CHECK BOX
   ═══════════════════════════════════════════ */

QCheckBox {
    color: #cad3f5;
    background-color: transparent;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #494d64;
    border-radius: 4px;
    background-color: #24273a;
}

QCheckBox::indicator:hover {
    border: 1px solid #0ea5e9;
}

QCheckBox::indicator:checked {
    background-color: #0ea5e9;
    border: 1px solid #0ea5e9;
}

/* ═══════════════════════════════════════════
   RADIO BUTTON
   ═══════════════════════════════════════════ */

QRadioButton {
    color: #cad3f5;
    background-color: transparent;
    spacing: 8px;
    font-size: 13px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #494d64;
    border-radius: 8px;
    background-color: #24273a;
}

QRadioButton::indicator:checked {
    background-color: #0ea5e9;
    border: 1px solid #0ea5e9;
}

/* ═══════════════════════════════════════════
   SPLITTER
   ═══════════════════════════════════════════ */

QSplitter::handle {
    background-color: #363a4f;
    width: 1px;
    height: 1px;
}

QSplitter::handle:hover {
    background-color: #0ea5e9;
}

/* ═══════════════════════════════════════════
   MENU BAR
   ═══════════════════════════════════════════ */

QMenuBar {
    background-color: #1a1b26;
    color: #cad3f5;
    border: none;
    padding: 2px 6px;
    font-size: 13px;
}

QMenuBar::item {
    padding: 5px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #24273a;
}

QMenu {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
    margin: 1px 2px;
}

QMenu::item:selected {
    background-color: rgba(14, 165, 233, 0.2);
}

QMenu::separator {
    height: 1px;
    background-color: #363a4f;
    margin: 4px 8px;
}

/* ═══════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════ */

QStatusBar {
    background-color: #1a1b26;
    color: #6e738d;
    border-top: 1px solid #2e3244;
    font-size: 12px;
    padding: 2px 6px;
}

QStatusBar::item {
    border: none;
}

/* ═══════════════════════════════════════════
   TOOLBAR
   ═══════════════════════════════════════════ */

QToolBar {
    background-color: transparent;
    border: none;
    spacing: 4px;
    padding: 2px;
}

QToolBar::separator {
    background-color: #363a4f;
    width: 1px;
    margin: 4px 6px;
}

/* ═══════════════════════════════════════════
   DIALOG
   ═══════════════════════════════════════════ */

QDialog {
    background-color: #1e2030;
    color: #cad3f5;
}

/* ═══════════════════════════════════════════
   TOOLTIPS
   ═══════════════════════════════════════════ */

QToolTip {
    background-color: #24273a;
    color: #cad3f5;
    border: 1px solid #363a4f;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ═══════════════════════════════════════════
   CUSTOM: METRIC CARDS
   ═══════════════════════════════════════════ */

MetricCard {
    background-color: #1e2030;
    border: 1px solid #363a4f;
    border-radius: 8px;
    padding: 14px;
}

MetricCard QLabel#titleLabel {
    color: #6e738d;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

MetricCard QLabel#valueLabel {
    color: #0ea5e9;
    font-size: 28px;
    font-weight: 700;
}

MetricCard QLabel#unitLabel {
    color: #5b6078;
    font-size: 11px;
}

/* ═══════════════════════════════════════════
   CUSTOM: CONNECTION STATUS
   ═══════════════════════════════════════════ */

ConnectionStatus {
    background-color: transparent;
}

ConnectionStatus QLabel#statusLabel {
    color: #ffffff;
    font-weight: 600;
}

ConnectionStatus[status="connected"] {
    background-color: rgba(5, 150, 105, 0.15);
    border: 1px solid rgba(5, 150, 105, 0.4);
    border-radius: 6px;
}

ConnectionStatus[status="disconnected"] {
    background-color: rgba(225, 29, 72, 0.15);
    border: 1px solid rgba(225, 29, 72, 0.4);
    border-radius: 6px;
}

ConnectionStatus[status="connecting"] {
    background-color: rgba(217, 119, 6, 0.15);
    border: 1px solid rgba(217, 119, 6, 0.4);
    border-radius: 6px;
}

/* ═══════════════════════════════════════════
   CUSTOM: JOB STATUS LABELS
   ═══════════════════════════════════════════ */

QLabel#jobStatusLabel {
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 11px;
    color: #ffffff;
}

QLabel#jobStatusLabel[status="Running"] {
    background-color: #059669;
}

QLabel#jobStatusLabel[status="Pending"] {
    background-color: #d97706;
}

QLabel#jobStatusLabel[status="Completed"] {
    background-color: #0284c7;
}

QLabel#jobStatusLabel[status="Failed"] {
    background-color: #e11d48;
}

QLabel#jobStatusLabel[status="Cancelled"] {
    background-color: #4b5563;
}

/* ═══════════════════════════════════════════
   FORM ROW LABELS
   ═══════════════════════════════════════════ */

QFormLayout QLabel {
    color: #6e738d;
    font-weight: 600;
    font-size: 12px;
}
"""

# ─────────────────────────────────────────────
#  Light Theme  —  Professional Scientific
# ─────────────────────────────────────────────
LIGHT_THEME_QSS = """
/* ═══════════════════════════════════════════
   GLOBAL FOUNDATION
   ═══════════════════════════════════════════ */

* {
    font-family: 'SF Pro Text', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
}

QMainWindow {
    background-color: #f5f5f7;
    color: #1d1d1f;
}

QWidget {
    background-color: #f5f5f7;
    color: #1d1d1f;
}

/* ═══════════════════════════════════════════
   TAB BAR
   ═══════════════════════════════════════════ */

QTabWidget {
    background-color: #f5f5f7;
    border: none;
}

QTabWidget::pane {
    border: none;
    background-color: #f5f5f7;
    margin-top: 0px;
}

QTabBar {
    background-color: #ffffff;
    border-bottom: 1px solid #d2d2d7;
    padding: 0px;
}

QTabBar::tab {
    background-color: transparent;
    color: #86868b;
    padding: 8px 16px;
    margin: 0px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 600;
    min-width: 70px;
}

QTabBar::tab:selected {
    color: #1d1d1f;
    border-bottom: 2px solid #0071e3;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    color: #6e6e73;
    border-bottom: 2px solid #d2d2d7;
}

/* ═══════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════ */

QPushButton {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #f0f0f2;
    border: 1px solid #c7c7cc;
}

QPushButton:pressed {
    background-color: #e5e5ea;
}

QPushButton:disabled {
    background-color: #f5f5f7;
    color: #aeaeb2;
    border: 1px solid #e5e5ea;
}

QPushButton#primaryButton {
    background-color: #0071e3;
    color: #ffffff;
    border: none;
}

QPushButton#primaryButton:hover {
    background-color: #0077ed;
}

QPushButton#dangerButton {
    background-color: #e11d48;
    color: #ffffff;
    border: none;
}

QPushButton#dangerButton:hover {
    background-color: #be123c;
}

QPushButton#successButton {
    background-color: #059669;
    color: #ffffff;
    border: none;
}

/* ═══════════════════════════════════════════
   INPUT FIELDS
   ═══════════════════════════════════════════ */

QLineEdit {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: #0071e3;
    selection-color: #ffffff;
}

QLineEdit:focus {
    border: 1px solid #0071e3;
}

QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 8px 10px;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0071e3;
}

/* ═══════════════════════════════════════════
   COMBO BOX
   ═══════════════════════════════════════════ */

QComboBox {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
}

QComboBox:hover {
    border: 1px solid #c7c7cc;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 4px;
    selection-background-color: rgba(0, 113, 227, 0.12);
    selection-color: #0071e3;
}

/* ═══════════════════════════════════════════
   SPIN BOX
   ═══════════════════════════════════════════ */

QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 5px 8px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #0071e3;
}

/* ═══════════════════════════════════════════
   TABLE
   ═══════════════════════════════════════════ */

QTableWidget, QTableView {
    background-color: #ffffff;
    alternate-background-color: #fafafa;
    gridline-color: #e5e5ea;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
}

QTableWidget::item, QTableView::item {
    padding: 6px 10px;
    border-bottom: 1px solid #e5e5ea;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: rgba(0, 113, 227, 0.1);
}

QHeaderView::section {
    background-color: #fafafa;
    color: #86868b;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #d2d2d7;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ═══════════════════════════════════════════
   LIST WIDGET
   ═══════════════════════════════════════════ */

QListWidget {
    background-color: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    color: #1d1d1f;
    padding: 8px 10px;
    margin: 1px 0px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: rgba(0, 113, 227, 0.1);
    color: #0071e3;
}

QListWidget::item:hover:!selected {
    background-color: #f0f0f2;
}

/* ═══════════════════════════════════════════
   TREE WIDGET
   ═══════════════════════════════════════════ */

QTreeWidget, QTreeView {
    background-color: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
}

QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: rgba(0, 113, 227, 0.1);
}

/* ═══════════════════════════════════════════
   SCROLL BARS
   ═══════════════════════════════════════════ */

QScrollBar:vertical {
    background-color: transparent;
    width: 6px;
    border: none;
    margin: 2px 1px;
}

QScrollBar::handle:vertical {
    background-color: #c7c7cc;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #aeaeb2;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 6px;
    border: none;
    margin: 1px 2px;
}

QScrollBar::handle:horizontal {
    background-color: #c7c7cc;
    border-radius: 3px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #aeaeb2;
}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    border: none;
    background: none;
    height: 0;
    width: 0;
}

/* ═══════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════ */

QProgressBar {
    background-color: #e5e5ea;
    border: none;
    border-radius: 4px;
    color: #1d1d1f;
    text-align: center;
    font-weight: 600;
    font-size: 11px;
    min-height: 14px;
}

QProgressBar::chunk {
    background-color: #0071e3;
    border-radius: 4px;
}

/* ═══════════════════════════════════════════
   LABELS
   ═══════════════════════════════════════════ */

QLabel {
    color: #1d1d1f;
    background-color: transparent;
    font-size: 13px;
}

/* ═══════════════════════════════════════════
   GROUP BOX
   ═══════════════════════════════════════════ */

QGroupBox {
    color: #6e6e73;
    border: 1px solid #d2d2d7;
    border-radius: 8px;
    margin-top: 10px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    font-size: 13px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 1px 8px;
    color: #86868b;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ═══════════════════════════════════════════
   CHECK BOX
   ═══════════════════════════════════════════ */

QCheckBox {
    color: #1d1d1f;
    background-color: transparent;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c7c7cc;
    border-radius: 4px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border: 1px solid #0071e3;
}

QCheckBox::indicator:checked {
    background-color: #0071e3;
    border: 1px solid #0071e3;
}

/* ═══════════════════════════════════════════
   RADIO BUTTON
   ═══════════════════════════════════════════ */

QRadioButton {
    color: #1d1d1f;
    background-color: transparent;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c7c7cc;
    border-radius: 8px;
    background-color: #ffffff;
}

QRadioButton::indicator:checked {
    background-color: #0071e3;
    border: 1px solid #0071e3;
}

/* ═══════════════════════════════════════════
   SPLITTER
   ═══════════════════════════════════════════ */

QSplitter::handle {
    background-color: #d2d2d7;
    width: 1px;
    height: 1px;
}

QSplitter::handle:hover {
    background-color: #0071e3;
}

/* ═══════════════════════════════════════════
   MENU BAR
   ═══════════════════════════════════════════ */

QMenuBar {
    background-color: #f5f5f7;
    color: #1d1d1f;
    border: none;
    padding: 2px 6px;
    font-size: 13px;
}

QMenuBar::item {
    padding: 5px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #e5e5ea;
}

QMenu {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
    margin: 1px 2px;
}

QMenu::item:selected {
    background-color: rgba(0, 113, 227, 0.1);
    color: #0071e3;
}

QMenu::separator {
    height: 1px;
    background-color: #e5e5ea;
    margin: 4px 8px;
}

/* ═══════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════ */

QStatusBar {
    background-color: #f5f5f7;
    color: #86868b;
    border-top: 1px solid #d2d2d7;
    font-size: 12px;
    padding: 2px 6px;
}

QStatusBar::item {
    border: none;
}

/* ═══════════════════════════════════════════
   TOOLBAR
   ═══════════════════════════════════════════ */

QToolBar {
    background-color: transparent;
    border: none;
    spacing: 4px;
    padding: 2px;
}

QToolBar::separator {
    background-color: #d2d2d7;
    width: 1px;
    margin: 4px 6px;
}

/* ═══════════════════════════════════════════
   DIALOG
   ═══════════════════════════════════════════ */

QDialog {
    background-color: #f5f5f7;
    color: #1d1d1f;
}

/* ═══════════════════════════════════════════
   TOOLTIPS
   ═══════════════════════════════════════════ */

QToolTip {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ═══════════════════════════════════════════
   CUSTOM: METRIC CARDS
   ═══════════════════════════════════════════ */

MetricCard {
    background-color: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 8px;
    padding: 14px;
}

MetricCard QLabel#titleLabel {
    color: #86868b;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

MetricCard QLabel#valueLabel {
    color: #0071e3;
    font-size: 28px;
    font-weight: 700;
}

MetricCard QLabel#unitLabel {
    color: #aeaeb2;
    font-size: 11px;
}

/* ═══════════════════════════════════════════
   CUSTOM: CONNECTION STATUS
   ═══════════════════════════════════════════ */

ConnectionStatus[status="connected"] {
    background-color: rgba(5, 150, 105, 0.08);
    border: 1px solid rgba(5, 150, 105, 0.3);
    border-radius: 6px;
}

ConnectionStatus[status="disconnected"] {
    background-color: rgba(225, 29, 72, 0.08);
    border: 1px solid rgba(225, 29, 72, 0.3);
    border-radius: 6px;
}

ConnectionStatus[status="connecting"] {
    background-color: rgba(217, 119, 6, 0.08);
    border: 1px solid rgba(217, 119, 6, 0.3);
    border-radius: 6px;
}

/* ═══════════════════════════════════════════
   CUSTOM: JOB STATUS LABELS
   ═══════════════════════════════════════════ */

QLabel#jobStatusLabel {
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 11px;
    color: #ffffff;
}

QLabel#jobStatusLabel[status="Running"] {
    background-color: #059669;
}

QLabel#jobStatusLabel[status="Pending"] {
    background-color: #d97706;
}

QLabel#jobStatusLabel[status="Completed"] {
    background-color: #0284c7;
}

QLabel#jobStatusLabel[status="Failed"] {
    background-color: #e11d48;
}

QLabel#jobStatusLabel[status="Cancelled"] {
    background-color: #9ca3af;
}

/* ═══════════════════════════════════════════
   FORM ROW LABELS
   ═══════════════════════════════════════════ */

QFormLayout QLabel {
    color: #86868b;
    font-weight: 600;
    font-size: 12px;
}
"""

import re as _re

_DEFAULT_BASE = 13  # The base font size the QSS was authored at (px)
_FONT_SIZE_RE = _re.compile(r'font-size:\s*(\d+)(px|pt)')


def scale_theme(qss: str, base_pt: int) -> str:
    """Return *qss* with every ``font-size: Npx`` or ``font-size: Npt``
    scaled to *base_pt*.

    Each hardcoded size is treated as a delta from the default 13 px
    baseline, so the relative proportions are preserved:

        scaled = original + (base_pt - 13)

    The minimum is clamped to 7 so tiny elements remain legible.
    """
    if base_pt == _DEFAULT_BASE:
        return qss  # No change needed
    delta = base_pt - _DEFAULT_BASE

    def _replace(m: _re.Match) -> str:
        orig = int(m.group(1))
        unit = m.group(2)
        scaled = max(7, orig + delta)
        return f'font-size: {scaled}{unit}'

    return _FONT_SIZE_RE.sub(_replace, qss)
