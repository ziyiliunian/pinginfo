# -*- coding: utf-8 -*-
"""主窗口模块 - PingInfo 主界面"""
from PyQt5.QtWidgets import (
    QMainWindow, QTableWidget, QTableWidgetItem, QAction, QStatusBar,
    QFileDialog, QMessageBox, QDialog, QLabel, QSpinBox, QHeaderView,
    QAbstractItemView, QProgressBar, QApplication, QMenu
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent
from concurrent.futures import ThreadPoolExecutor, as_completed
from .data_models import TargetStats
from .ping_core import ping_batch, resolve_to_ipv4, is_ip_address, expand_ip_range
from .arp_lookup import get_mac_address
from .exporters import export_results
from .dialogs import AddTargetsDialog, SettingsDialog, ExportSelectionDialog

COLUMNS = [
    (0, "选择", 40), (1, "序号", 40), (2, "地址", 140),
    (3, "Ping方式", 70), (4, "状态", 60), (5, "响应时间(ms)", 100),
    (6, "丢包率(%)", 80), (7, "成功", 50), (8, "失败", 50),
    (9, "平均(ms)", 90), (10, "最小(ms)", 80), (11, "最大(ms)", 80),
    (12, "TTL", 50), (13, "最近成功时间", 150), (14, "最近失败时间", 150),
    (15, "MAC地址", 130), (16, "解析地址", 130), (17, "错误信息", 200),
]


class PingWorker(QThread):
    batch_complete = pyqtSignal(list)
    log_message = pyqtSignal(str)

    def __init__(self, targets, interval=1, max_workers=200, timeout=3,
                 packet_size=56, ttl=0):
        super().__init__()
        self.targets = targets
        self.interval = interval
        self.max_workers = max_workers
        self.timeout = timeout
        self.packet_size = packet_size
        self.ttl = ttl
        self._stop = False

    def run(self):
        self.log_message.emit("开始监控...")
        while not self._stop:
            active = [t for t in self.targets if t.is_running]
            if active:
                results = ping_batch(active, max_workers=self.max_workers,
                                     timeout=self.timeout,
                                     packet_size=self.packet_size,
                                     ttl=self.ttl)
                self.batch_complete.emit(results)
            for _ in range(self.interval):
                if self._stop:
                    break
                self.msleep(1000)
        self.log_message.emit("监控已停止")

    def stop(self):
        self._stop = True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PingInfo - 批量 Ping 与实时监控工具")
        self.setMinimumSize(1200, 600)
        self.resize(1400, 700)
        self.targets = []
        self.worker = None
        self.ping_interval = 1
        self.max_workers = 500
        self.ping_timeout = 3
        self.packet_size = 56
        self.icmp_ttl = 0
        self.default_ping_mode = "ICMP"
        self.default_tcp_port = 80
        self._init_ui()
        self._init_menu()
        self._init_toolbar()
        self._init_statusbar()
        self.setAcceptDrops(True)

    def _init_ui(self):
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels([c[1] for c in COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        header = self.table.horizontalHeader()
        for idx, _, w in COLUMNS:
            header.resizeSection(idx, w)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(17, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.setCentralWidget(self.table)

    def _init_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("文件(&F)")
        a = QAction("添加目标...", self); a.setShortcut("Ctrl+N")
        a.triggered.connect(self.add_targets_dialog); fm.addAction(a)
        a = QAction("从新添加...", self); a.setShortcut("Ctrl+Shift+N")
        a.triggered.connect(self.reload_targets_dialog); fm.addAction(a)
        a = QAction("从文件载入地址...", self); a.setShortcut("Ctrl+O")
        a.triggered.connect(self.load_from_file); fm.addAction(a)
        a = QAction("从文件重新载入...", self); a.setShortcut("Ctrl+Shift+O")
        a.triggered.connect(self.reload_from_file); fm.addAction(a)
        fm.addSeparator()
        em = fm.addMenu("导出结果")
        for fmt, label in [("txt","TXT"),("csv","CSV"),("html","HTML"),("xml","XML")]:
            a = QAction(f"导出为 {label}...", self)
            a.triggered.connect(lambda _, f=fmt: self.export_results(f))
            em.addAction(a)
        fm.addSeparator()
        a = QAction("退出", self); a.setShortcut("Ctrl+Q")
        a.triggered.connect(self.close); fm.addAction(a)

        edm = mb.addMenu("编辑(&E)")
        a = QAction("删除选中行", self); a.setShortcut("Delete")
        a.triggered.connect(self.delete_selected); edm.addAction(a)
        a = QAction("清空全部", self); a.triggered.connect(self.clear_all); edm.addAction(a)
        a = QAction("重置统计数据", self); a.triggered.connect(self.reset_stats); edm.addAction(a)
        edm.addSeparator()
        a = QAction("启用选中", self); a.triggered.connect(lambda: self.toggle_selected(True)); edm.addAction(a)
        a = QAction("禁用选中", self); a.triggered.connect(lambda: self.toggle_selected(False)); edm.addAction(a)

        pm = mb.addMenu("Ping(&P)")
        self.act_start = QAction("开始监控", self); self.act_start.setShortcut("F5")
        self.act_start.triggered.connect(self.start_monitoring); pm.addAction(self.act_start)
        self.act_stop = QAction("停止监控", self); self.act_stop.setShortcut("F6")
        self.act_stop.triggered.connect(self.stop_monitoring)
        self.act_stop.setEnabled(False); pm.addAction(self.act_stop)
        pm.addSeparator()
        a = QAction("Ping 选项设置...", self); a.triggered.connect(self.show_settings); pm.addAction(a)

        tm = mb.addMenu("工具(&T)")
        a = QAction("查询 MAC 地址", self); a.triggered.connect(self.query_mac_addresses); tm.addAction(a)

        hm = mb.addMenu("帮助(&H)")
        a = QAction("关于", self); a.triggered.connect(self.show_about); hm.addAction(a)

    def _init_toolbar(self):
        tb = self.addToolBar("主工具栏")
        tb.setMovable(False); tb.setIconSize(QSize(24, 24))
        tb.addAction(self.act_start); tb.addAction(self.act_stop); tb.addSeparator()
        a = QAction("添加目标", self); a.triggered.connect(self.add_targets_dialog); tb.addAction(a)
        a = QAction("删除选中", self); a.triggered.connect(self.delete_selected); tb.addAction(a)
        a = QAction("清空全部", self); a.triggered.connect(self.clear_all); tb.addAction(a)
        tb.addSeparator()
        a = QAction("查询MAC", self); a.triggered.connect(self.query_mac_addresses); tb.addAction(a)
        tb.addSeparator()
        a = QAction("导出CSV", self); a.triggered.connect(lambda: self.export_results("csv")); tb.addAction(a)

    def _init_statusbar(self):
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪"); self.status_bar.addWidget(self.status_label)
        self.count_label = QLabel("目标数: 0"); self.status_bar.addPermanentWidget(self.count_label)
        self.progress = QProgressBar(); self.progress.setMaximumWidth(200)
        self.progress.setVisible(False); self.status_bar.addPermanentWidget(self.progress)

    def add_targets(self, target_list):
        added = []
        for host, mode, port in target_list:
            if any(t.address == host and t.ping_mode == mode for t in self.targets):
                continue
            t = TargetStats(address=host, ping_mode=mode, tcp_port=port)
            self.targets.append(t)
            added.append(t)
        self.refresh_table(); self.update_count()
        # 异步解析域名 -> IPv4
        if added:
            self._resolve_targets_async(added)

    def _resolve_targets_async(self, targets):
        """并行解析域名对应的 IPv4 地址，完成后刷新表格"""
        domains = [t for t in targets if not is_ip_address(t.address)]
        if not domains:
            return
        self.status_label.setText("正在解析域名 IPv4 地址..."); QApplication.processEvents()
        try:
            with ThreadPoolExecutor(max_workers=min(50, len(domains))) as ex:
                future_to_target = {ex.submit(resolve_to_ipv4, t.address): t for t in domains}
                for future in as_completed(future_to_target):
                    t = future_to_target[future]
                    try:
                        ip = future.result()
                        if ip:
                            t.resolved_ip = ip
                    except Exception:
                        pass
        except Exception:
            pass
        self.refresh_table()
        self.status_label.setText(f"已解析 {sum(1 for t in targets if t.resolved_ip)} 个域名")

    def add_targets_dialog(self):
        dlg = AddTargetsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            ts = dlg.get_targets()
            if ts:
                self.add_targets(ts)
                self.status_label.setText(f"已添加 {len(ts)} 个目标")

    def reload_targets_dialog(self):
        """清空所有目标后重新添加"""
        self.stop_monitoring()
        self.targets.clear()
        self.refresh_table(); self.update_count()
        dlg = AddTargetsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            ts = dlg.get_targets()
            if ts:
                self.add_targets(ts)
                self.status_label.setText(f"已重新添加 {len(ts)} 个目标")
            else:
                self.status_label.setText("已清空所有目标")
        else:
            self.status_label.setText("已清空所有目标")

    def reload_from_file(self):
        """清空所有目标后从文件重新载入"""
        fp, _ = QFileDialog.getOpenFileName(self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if fp:
            self.stop_monitoring()
            self.targets.clear()
            self.refresh_table(); self.update_count()
            self._load_file(fp)
            self.status_label.setText("已从文件重新载入目标")

    def load_from_file(self):
        fp, _ = QFileDialog.getOpenFileName(self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if fp:
            self._load_file(fp)

    def _load_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取文件失败: {e}"); return
        tl = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            port = self.default_tcp_port; host = line
            if ":" in line and line.count(":") == 1:
                parts = line.rsplit(":", 1)
                if parts[1].isdigit():
                    host = parts[0]; port = int(parts[1])
                    tl.append((host, "TCP", port)); continue
            # 展开 IP 范围
            for ip in expand_ip_range(host):
                tl.append((ip, self.default_ping_mode, port))
        if tl:
            self.add_targets(tl)
            self.status_label.setText(f"从文件载入了 {len(tl)} 个目标")

    def delete_selected(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        if not rows:
            return
        for r in rows:
            if r < len(self.targets):
                del self.targets[r]
        self.refresh_table(); self.update_count()

    def clear_all(self):
        if not self.targets:
            return
        if QMessageBox.question(self, "确认", "确定要清空所有目标吗?") == QMessageBox.Yes:
            self.stop_monitoring(); self.targets.clear()
            self.refresh_table(); self.update_count()
            self.status_label.setText("已清空所有目标")

    def reset_stats(self):
        for t in self.targets:
            t.reset()
        self.refresh_table(); self.status_label.setText("统计数据已重置")

    def toggle_selected(self, enabled):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        for r in rows:
            if r < len(self.targets):
                self.targets[r].is_running = enabled
        self.refresh_table()

    def start_monitoring(self):
        if not self.targets:
            QMessageBox.information(self, "提示", "请先添加 Ping 目标"); return
        if self.worker and self.worker.isRunning():
            return
        self.worker = PingWorker(self.targets, self.ping_interval, self.max_workers,
                                 self.ping_timeout, self.packet_size, self.icmp_ttl)
        self.worker.batch_complete.connect(self.on_batch_complete)
        self.worker.log_message.connect(self.on_log_message)
        self.worker.start()
        self.act_start.setEnabled(False); self.act_stop.setEnabled(True)
        self.progress.setVisible(True); self.progress.setRange(0, 0)

    def stop_monitoring(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(5000)
        self.worker = None
        self.act_start.setEnabled(True); self.act_stop.setEnabled(False)
        self.progress.setVisible(False)

    def on_batch_complete(self, results):
        for target, result in results:
            if result.success:
                target.update_success(result.rtt, result.ttl)
            else:
                target.update_fail(result.error or "失败")
        self.refresh_table(); self.update_count()

    def on_log_message(self, msg):
        self.status_label.setText(msg)

    def _on_item_changed(self, item):
        """处理 checkbox 状态变化"""
        if item.column() == 0:
            row = item.row()
            if row < len(self.targets):
                self.targets[row].selected = (item.checkState() == Qt.Checked)

    def _show_context_menu(self, pos):
        """表格右键菜单（中文）"""
        menu = QMenu(self)
        act_add = menu.addAction("添加目标...")
        act_del = menu.addAction("删除选中行")
        menu.addSeparator()
        act_enable = menu.addAction("启用选中")
        act_disable = menu.addAction("禁用选中")
        menu.addSeparator()
        act_check_all = menu.addAction("全选勾选")
        act_uncheck_all = menu.addAction("取消全部勾选")
        menu.addSeparator()
        act_mac = menu.addAction("查询 MAC 地址")
        menu.addSeparator()
        act_export = menu.addAction("导出结果...")

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == act_add:
            self.add_targets_dialog()
        elif action == act_del:
            self.delete_selected()
        elif action == act_enable:
            self.toggle_selected(True)
        elif action == act_disable:
            self.toggle_selected(False)
        elif action == act_check_all:
            for t in self.targets:
                t.selected = True
            self.refresh_table()
        elif action == act_uncheck_all:
            for t in self.targets:
                t.selected = False
            self.refresh_table()
        elif action == act_mac:
            self.query_mac_addresses()
        elif action == act_export:
            self.export_results("csv")

    def refresh_table(self):
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.targets))
        for row, s in enumerate(self.targets):
            self._set_row(row, s)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)

    def _set_row(self, row, s):
        # 第0列：复选框
        cb_item = QTableWidgetItem()
        cb_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        cb_item.setCheckState(Qt.Checked if s.selected else Qt.Unchecked)
        self.table.setItem(row, 0, cb_item)
        # 第1列起：数据
        self._c(row, 1, str(row + 1))                                   # 序号
        self._c(row, 2, s.address)                                        # 地址
        self._c(row, 3, f"TCP:{s.tcp_port}" if s.ping_mode == "TCP" else s.ping_mode)  # Ping方式
        st = s.status_text                                                # 状态
        item = self._c(row, 4, st)
        if st == "成功":
            item.setForeground(QColor("#4CAF50"))
        elif st == "失败":
            item.setForeground(QColor("#f44336"))
        elif st == "等待中":
            item.setForeground(QColor("#FF9800"))
        self._c(row, 5, f"{s.last_rtt:.2f}" if s.last_rtt is not None else "-")    # 响应时间
        self._c(row, 6, f"{s.loss_rate:.1f}")                              # 丢包率
        self._c(row, 7, str(s.success_count))                             # 成功
        self._c(row, 8, str(s.fail_count))                                # 失败
        self._c(row, 9, f"{s.avg_rtt:.2f}" if s.avg_rtt is not None else "-")     # 平均
        self._c(row, 10, f"{s.min_rtt:.2f}" if s.min_rtt is not None else "-")    # 最小
        self._c(row, 11, f"{s.max_rtt:.2f}" if s.max_rtt is not None else "-")    # 最大
        self._c(row, 12, str(s.last_ttl) if s.last_ttl is not None else "-")      # TTL
        self._c(row, 13, s.last_success_time or "-")                      # 最近成功时间
        self._c(row, 14, s.last_fail_time or "-")                         # 最近失败时间
        self._c(row, 15, s.mac_address or "-")                            # MAC地址
        self._c(row, 16, s.resolved_ip or "-")                            # 解析地址
        self._c(row, 17, s.last_error or "")                             # 错误信息
        if not s.is_running:
            for col in range(1, self.table.columnCount()):
                it = self.table.item(row, col)
                if it:
                    it.setForeground(QColor("#999999"))

    def _c(self, row, col, text):
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem(text); self.table.setItem(row, col, item)
        else:
            item.setText(text)
        return item

    def update_count(self):
        total = len(self.targets)
        active = sum(1 for t in self.targets if t.is_running)
        self.count_label.setText(f"目标数: {total} (启用: {active})")

    def query_mac_addresses(self):
        if not self.targets:
            QMessageBox.information(self, "提示", "没有目标可查询"); return
        self.status_label.setText("正在查询 MAC 地址..."); QApplication.processEvents()
        for s in self.targets:
            if s.is_running:
                mac = get_mac_address(s.address)
                if mac:
                    s.mac_address = mac
        self.refresh_table(); self.status_label.setText("MAC 地址查询完成")

    def show_settings(self):
        dlg = SettingsDialog(self, self.ping_interval, self.max_workers,
                             self.ping_timeout, self.packet_size, self.icmp_ttl)
        if dlg.exec_() == QDialog.Accepted:
            settings = dlg.get_settings()
            self.ping_interval = settings[0]
            self.max_workers = settings[1]
            self.ping_timeout = settings[2]
            self.packet_size = settings[3]
            self.icmp_ttl = settings[4]
            self.status_label.setText(
                f"设置已更新: 间隔={self.ping_interval}s, 并发={self.max_workers}, "
                f"超时={self.ping_timeout}s, 包大小={self.packet_size}, TTL={self.icmp_ttl}")

    def show_about(self):
        QMessageBox.about(self, "关于 PingInfo",
            "<h2>PingInfo v1.0.0</h2><p>批量 Ping 与实时监控工具</p>"
            "<ul><li>支持 ICMP Ping 和 TCP Ping</li><li>支持 IPv4 / IPv6</li>"
            "<li>批量目标管理和实时监控</li><li>响应时间、丢包率、延迟统计</li>"
            "<li>TTL、MAC 地址查询</li><li>导出 TXT / CSV / HTML / XML</li></ul>"
            "<p>支持拖放文本文件导入地址</p>")

    def export_results(self, fmt):
        if not self.targets:
            QMessageBox.information(self, "提示", "没有数据可导出"); return

        # 获取表格选中的行和勾选的目标
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        selected_count = len(selected_rows)
        checked_count = sum(1 for t in self.targets if t.selected)

        # 弹出导出选择对话框
        dlg = ExportSelectionDialog(self, len(self.targets), selected_count, checked_count)
        if dlg.exec_() != QDialog.Accepted:
            return

        mode = dlg.get_export_mode()
        if mode == "checked":
            targets_to_export = [t for t in self.targets if t.selected]
        elif mode == "selected" and selected_count > 0:
            targets_to_export = [self.targets[r] for r in selected_rows if r < len(self.targets)]
        else:
            targets_to_export = self.targets

        if not targets_to_export:
            QMessageBox.information(self, "提示", "没有可导出的数据"); return

        fm = {"txt": "文本文件 (*.txt)", "csv": "CSV 文件 (*.csv)",
              "html": "HTML 文件 (*.html)", "xml": "XML 文件 (*.xml)"}
        fp, _ = QFileDialog.getSaveFileName(self, "导出结果",
            f"pinginfo_result.{fmt}", fm.get(fmt, "所有文件 (*)"))
        if fp:
            if export_results(targets_to_export, fp, fmt):
                QMessageBox.information(self, "成功",
                    f"已导出 {len(targets_to_export)} 条结果到:\n{fp}")
                self.status_label.setText(f"已导出 {len(targets_to_export)} 条到 {fp}")
            else:
                QMessageBox.warning(self, "失败", "导出失败")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fp = url.toLocalFile()
                if fp.lower().endswith(('.txt', '.csv', '.list', '.dat')):
                    self._load_file(fp)
        elif event.mimeData().hasText():
            text = event.mimeData().text().strip()
            tl = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                port = self.default_tcp_port; host = line
                if ":" in line and line.count(":") == 1:
                    parts = line.rsplit(":", 1)
                    if parts[1].isdigit():
                        host = parts[0]; port = int(parts[1])
                        tl.append((host, "TCP", port)); continue
                for ip in expand_ip_range(host):
                    tl.append((ip, self.default_ping_mode, port))
            if tl:
                self.add_targets(tl)
                self.status_label.setText(f"从拖放添加了 {len(tl)} 个目标")

    def closeEvent(self, event):
        self.stop_monitoring()
        event.accept()
