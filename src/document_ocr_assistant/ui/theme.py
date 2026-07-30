from __future__ import annotations


LIGHT_STYLE = """
QWidget {
    color: #172033;
    background: #F5F7FB;
    font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog { background: #F5F7FB; }
QLabel { background: transparent; }
QFrame#Sidebar { background: #FFFFFF; border-right: 1px solid #E6EAF1; }
QFrame#Card, QFrame#DropZone, QFrame#Inspector, QFrame#SettingsCard {
    background: #FFFFFF;
    border: 1px solid #E4E9F1;
    border-radius: 14px;
}
QFrame#DropZone:hover, QFrame#DropZone:focus {
  border: 2px solid #75A7FF;
  background: #F6F9FF;
}
QFrame#DropZone[dragActive="true"] {
  border: 2px solid #3478F6;
  background: #EEF4FF;
}
QLabel#AppTitle { font-size: 20px; font-weight: 700; color: #162033; }
QLabel#PageTitle { font-size: 26px; font-weight: 700; color: #111827; }
QLabel#Muted { color: #6B7280; }
QPushButton {
    background: #FFFFFF;
    border: 1px solid #DDE3EC;
    border-radius: 9px;
    min-height: 34px;
    padding: 0 14px;
}
QPushButton:hover { background: #F4F7FB; border-color: #BFC9D8; }
QPushButton:pressed { background: #EAF0F8; }
QPushButton:disabled { color: #A4ADBA; background: #F7F8FA; }
QPushButton[primary="true"] { background: #3478F6; color: white; border-color: #3478F6; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #2869DF; }
QPushButton[nav="true"] {
    border: 0; border-radius: 10px; text-align: left; padding-left: 16px;
    background: transparent; color: #4B5563; min-height: 42px;
}
QPushButton[nav="true"]:hover { background: #F2F5FA; color: #1F2937; }
QPushButton[nav="true"]:checked { background: #EAF1FF; color: #2563EB; font-weight: 650; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QKeySequenceEdit {
    background: #FFFFFF;
    border: 1px solid #DDE3EC;
    border-radius: 9px;
    padding: 7px 9px;
    selection-background-color: #BFD5FF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {
    border-color: #4C8BF7;
}
QTableWidget {
    background: #FFFFFF; border: 0; gridline-color: #EEF1F5; alternate-background-color: #FAFBFD;
}
QHeaderView::section {
    background: #F8FAFC; color: #64748B; border: 0; border-bottom: 1px solid #E6EAF1;
    padding: 10px; font-weight: 600;
}
QProgressBar { background: #E9EEF6; border: 0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #3478F6; border-radius: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #C8D0DC; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QToolTip { background: #1F2937; color: white; border: 0; padding: 6px; }
"""


DARK_STYLE = LIGHT_STYLE + """
QWidget { color: #E5E7EB; background: #151922; }
QLabel { background: transparent; }
QMainWindow, QDialog { background: #151922; }
QFrame#Sidebar, QFrame#Card, QFrame#DropZone, QFrame#Inspector, QFrame#SettingsCard {
    background: #1D2430; border-color: #303847;
}
QFrame#DropZone:hover, QFrame#DropZone:focus {
  border: 2px solid #477AC5;
  background: #222C3A;
}
QFrame#DropZone[dragActive="true"] {
  border: 2px solid #4C8BF7;
  background: #24344D;
}
QFrame#Sidebar { border-right-color: #303847; }
QLabel#AppTitle, QLabel#PageTitle { color: #F3F4F6; }
QLabel#Muted { color: #9CA3AF; }
QPushButton { background: #252D3A; border-color: #3A4556; color: #E5E7EB; }
QPushButton:hover { background: #2D3746; }
QPushButton[nav="true"] { background: transparent; color: #B7C0CC; }
QPushButton[nav="true"]:checked { background: #243B67; color: #82AEFF; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QKeySequenceEdit, QTableWidget {
    background: #1D2430; border-color: #3A4556; color: #E5E7EB;
}
QHeaderView::section { background: #222A36; color: #AEB8C6; border-bottom-color: #303847; }
QTableWidget { gridline-color: #303847; alternate-background-color: #202834; }
"""


def use_dark_palette(application) -> bool:
    color = application.palette().window().color()
    return color.lightness() < 128
