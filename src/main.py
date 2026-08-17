# -*- coding: utf-8 -*-
"""PingInfo - 批量 Ping 与实时监控工具 主入口"""
import sys
import os

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.main_window import MainWindow
else:
    from .main_window import MainWindow

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PingInfo")
    app.setApplicationDisplayName("PingInfo")
    app.setOrganizationName("PingInfo")
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
