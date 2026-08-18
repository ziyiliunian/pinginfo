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
from PyQt5.QtGui import QFont, QIcon


def _load_app_icon():
    """优先从系统主题加载 pinginfo 图标，找不到时回退到安装目录自带图标。"""
    icon = QIcon.fromTheme("pinginfo")
    if not icon.isNull():
        return icon
    # 回退路径：安装后位于 /opt/pinginfo，开发时在仓库根目录
    candidates = [
        "/opt/pinginfo/usr/share/icons/hicolor/256x256/apps/pinginfo.png",
        "/opt/pinginfo/icons/pinginfo.png",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "packaging/usr/share/icons/hicolor/256x256/apps/pinginfo.png"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return QIcon(path)
    return QIcon()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PingInfo")
    app.setApplicationDisplayName("PingInfo")
    app.setOrganizationName("PingInfo")
    # 设置窗口/任务栏图标
    app_icon = _load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
