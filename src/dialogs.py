# -*- coding: utf-8 -*-
"""
对话框模块
包含添加目标对话框和设置对话框
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QSpinBox, QRadioButton, QButtonGroup, QTextEdit, QPushButton,
    QGroupBox, QFileDialog, QMessageBox, QApplication, QMenu,
    QDialogButtonBox, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt
from .ping_core import expand_ip_range, parse_host_port


class ChineseTextEdit(QTextEdit):
    """支持中文右键菜单的文本编辑框"""
    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        for action in menu.actions():
            text = action.text()
            if "Undo" in text:
                action.setText("撤销")
            elif "Redo" in text:
                action.setText("重做")
            elif "Cut" in text:
                action.setText("剪切")
            elif "Copy" in text:
                action.setText("复制")
            elif "Paste" in text:
                action.setText("粘贴")
            elif "Delete" in text:
                action.setText("删除")
            elif "Select All" in text:
                action.setText("全选")
        menu.exec_(event.globalPos())


class AddTargetsDialog(QDialog):
    """添加目标对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加 Ping 目标")
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)
        self.targets = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Ping 方式选择
        mode_group = QGroupBox("Ping 方式")
        mode_layout = QHBoxLayout()
        self.radio_icmp = QRadioButton("ICMP Ping")
        self.radio_tcp = QRadioButton("TCP Ping")
        self.radio_icmp.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_icmp)
        self.mode_group.addButton(self.radio_tcp)
        mode_layout.addWidget(self.radio_icmp)
        mode_layout.addWidget(self.radio_tcp)

        self.port_label = QLabel("TCP 端口:")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(80)
        self.port_spin.setEnabled(False)
        mode_layout.addWidget(self.port_label)
        mode_layout.addWidget(self.port_spin)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        self.radio_tcp.toggled.connect(lambda c: self.port_spin.setEnabled(c))
        self.radio_tcp.toggled.connect(lambda c: self.port_label.setEnabled(c))

        # 目标输入
        input_group = QGroupBox("目标地址 (每行一个，支持 IP 范围和 CIDR)")
        input_layout = QVBoxLayout()
        self.text_edit = ChineseTextEdit()
        # 不换行：长 IP/域名超宽时显示水平滚动条，保证每行一个目标
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_edit.setPlaceholderText(
            "支持以下格式:\n"
            "192.168.1.1\n"
            "8.8.8.8\n"
            "www.example.com\n"
            "192.168.0.10-192.168.0.201  (IP范围)\n"
            "192.168.0.10-201             (简写范围)\n"
            "192.168.0.0/24               (CIDR)\n"
            "192.168.0.100:80             (TCP Ping 带端口)"
        )
        input_layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        btn_paste = QPushButton("粘贴")
        btn_paste.setToolTip("粘贴剪贴板内容 (Ctrl+V)")
        btn_paste.clicked.connect(self._paste_content)
        btn_layout.addWidget(btn_paste)
        btn_load = QPushButton("从文件载入...")
        btn_load.clicked.connect(self._load_from_file)
        btn_layout.addWidget(btn_load)
        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 按钮
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("添加")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

        # QTextEdit 原生支持 Ctrl+V；不重复注册快捷键，避免一次粘贴触发多次
        self.text_edit.setFocus()

    def _paste_content(self):
        """粘贴剪贴板内容到文本框"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.text_edit.insertPlainText(text)
        self.text_edit.setFocus()

    def _load_from_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    self.text_edit.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "错误", f"读取文件失败: {e}")

    def _accept(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请输入至少一个目标地址")
            return

        ping_mode = "TCP" if self.radio_tcp.isChecked() else "ICMP"
        tcp_port = self.port_spin.value()

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            host, port, valid = parse_host_port(line, tcp_port)
            if not valid:
                QMessageBox.warning(self, "格式错误", f"无效的目标或端口: {line}")
                return
            has_explicit_port = (line.startswith('[') and ']:' in line) or (
                line.count(':') == 1 and line.rsplit(':', 1)[1].isdigit())
            if has_explicit_port and ping_mode != "TCP":
                QMessageBox.warning(self, "格式错误",
                    f"带端口的目标必须选择 TCP Ping: {line}")
                return
            # 展开 IP 范围 (如 192.168.0.10-201 或 192.168.0.0/24)
            expanded = expand_ip_range(host)
            for ip in expanded:
                self.targets.append((ip, ping_mode, port))
        self.accept()

    def get_targets(self):
        return self.targets


class TargetDetailsDialog(QDialog):
    """显示单个目标的完整实时统计信息。"""

    def __init__(self, target, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"目标详情 - {target.address}")
        self.setMinimumSize(520, 560)
        self._init_ui(target)

    @staticmethod
    def _text(value, suffix=""):
        if value is None or value == "":
            return "-"
        return f"{value}{suffix}"

    def _init_ui(self, target):
        layout = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        form = QFormLayout(content)
        response_address = target.response_address or "-"
        ping_method = (f"TCP:{target.tcp_port}" if target.ping_mode == "TCP"
                       else target.ping_mode)
        history = ", ".join(
            "失败" if value is None else f"{value:.2f} ms"
            for value in target.rtt_history
        ) or "-"
        fields = (
            ("主机名", target.hostname or "-"),
            ("目标地址", target.address),
            ("IP 地址", target.resolved_ip or
             ("-" if target.hostname else target.address)),
            ("响应地址", response_address),
            ("Ping 方式", ping_method),
            ("当前状态", target.status_text),
            ("是否启用", "是" if target.is_running else "否"),
            ("总请求次数", target.total_count),
            ("成功次数", target.success_count),
            ("失败次数", target.fail_count),
            ("丢包率", f"{target.loss_rate:.1f}%"),
            ("最近响应时间", self._text(
                f"{target.last_rtt:.2f}" if target.last_rtt is not None else None,
                " ms")),
            ("平均响应时间", self._text(
                f"{target.avg_rtt:.2f}" if target.avg_rtt is not None else None,
                " ms")),
            ("最小响应时间", self._text(
                f"{target.min_rtt:.2f}" if target.min_rtt is not None else None,
                " ms")),
            ("最大响应时间", self._text(
                f"{target.max_rtt:.2f}" if target.max_rtt is not None else None,
                " ms")),
            ("TTL", self._text(target.last_ttl)),
            ("MAC 地址", self._text(target.mac_address)),
            ("最近成功时间", self._text(target.last_success_time)),
            ("最近失败时间", self._text(target.last_fail_time)),
            ("最近错误", self._text(target.last_error)),
            ("最近 20 次结果", history),
        )
        for name, value in fields:
            label = QLabel(str(value))
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            label.setStyleSheet("padding: 3px; color: #263238;")
            form.addRow(f"{name}:", label)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SettingsDialog(QDialog):
    """Ping 设置对话框"""
    def __init__(self, parent=None, interval=1, max_workers=500, timeout=3,
                 packet_size=56, ttl=0):
        super().__init__(parent)
        self.setWindowTitle("Ping 选项设置")
        self.setMinimumWidth(380)
        self._init_ui(interval, max_workers, timeout, packet_size, ttl)

    def _init_ui(self, interval, max_workers, timeout, packet_size, ttl):
        layout = QFormLayout(self)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setValue(interval)
        self.interval_spin.setSuffix(" 秒")
        layout.addRow("Ping 间隔:", self.interval_spin)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 2000)
        self.workers_spin.setValue(max_workers)
        layout.addRow("并发线程数:", self.workers_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(timeout)
        self.timeout_spin.setSuffix(" 秒")
        layout.addRow("超时时间:", self.timeout_spin)

        layout.addRow(QLabel("<b>ICMP 高级选项</b>"))

        self.packet_size_spin = QSpinBox()
        self.packet_size_spin.setRange(0, 65500)
        self.packet_size_spin.setValue(packet_size)
        self.packet_size_spin.setSuffix(" 字节")
        self.packet_size_spin.setToolTip("ICMP 数据包大小，默认 56 字节（0=系统默认）")
        layout.addRow("ICMP 包大小:", self.packet_size_spin)

        self.ttl_spin = QSpinBox()
        self.ttl_spin.setRange(0, 255)
        self.ttl_spin.setValue(ttl)
        self.ttl_spin.setToolTip("TTL 起始值，0 表示使用系统默认(64)")
        layout.addRow("TTL 起始值:", self.ttl_spin)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addRow(btn_box)

    def get_settings(self):
        return (
            self.interval_spin.value(),
            self.workers_spin.value(),
            self.timeout_spin.value(),
            self.packet_size_spin.value(),
            self.ttl_spin.value()
        )


class ExportSelectionDialog(QDialog):
    """导出选择对话框 - 选择导出全部或选中的目标"""
    def __init__(self, parent=None, total_count=0, selected_count=0, checked_count=0):
        super().__init__(parent)
        self.setWindowTitle("选择导出范围")
        self.setMinimumWidth(380)
        self._init_ui(total_count, selected_count, checked_count)

    def _init_ui(self, total_count, selected_count, checked_count):
        layout = QVBoxLayout(self)

        info = QLabel(f"总目标数: {total_count}    表格选中: {selected_count} 行    勾选: {checked_count} 个")
        info.setStyleSheet("font-size: 13px; color: #555;")
        layout.addWidget(info)
        layout.addSpacing(10)

        self.radio_all = QRadioButton(f"导出全部目标 ({total_count} 个)")
        self.radio_checked = QRadioButton(
            f"仅导出勾选目标 ({checked_count} 个)" if checked_count > 0
            else "仅导出勾选目标 (未勾选任何行)"
        )
        self.radio_selected = QRadioButton(
            f"仅导出表格选中行 ({selected_count} 行)" if selected_count > 0
            else "仅导出表格选中行 (未选中任何行)"
        )
        self.radio_all.setChecked(True)
        if checked_count == 0:
            self.radio_checked.setEnabled(False)
        if selected_count == 0:
            self.radio_selected.setEnabled(False)
        layout.addWidget(self.radio_all)
        layout.addWidget(self.radio_checked)
        layout.addWidget(self.radio_selected)
        layout.addSpacing(10)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def get_export_mode(self):
        """返回导出模式: 'all', 'checked', 'selected'"""
        if self.radio_checked.isChecked():
            return "checked"
        elif self.radio_selected.isChecked():
            return "selected"
        return "all"
