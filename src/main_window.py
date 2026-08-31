# -*- coding: utf-8 -*-
"""主窗口模块 - PingInfo 主界面"""
import time

from PyQt5.QtWidgets import (
    QMainWindow, QTableView, QAction, QStatusBar,
    QFileDialog, QMessageBox, QDialog, QLabel, QSpinBox, QHeaderView,
    QAbstractItemView, QProgressBar, QMenu, QApplication,
    QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QStyle
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QEvent, QRect, QTimer
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent, QKeySequence, QPen
from concurrent.futures import (FIRST_COMPLETED, ThreadPoolExecutor, wait)
from .data_models import TargetStats
from .ping_core import (ping_batch, resolve_to_ipv4, resolve_hostname,
                        is_ip_address, expand_ip_range, normalize_host,
                        icmp_ping, parse_host_port)
from .arp_lookup import get_mac_address
from .exporters import export_results
from .dialogs import (AddTargetsDialog, SettingsDialog, ExportSelectionDialog,
                      TargetDetailsDialog)
from .table_model import COLUMNS, TARGET_ROLE, TargetSortProxyModel, TargetTableModel


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
            # 每轮使用稳定快照；列表在 GUI 线程增删时不会影响本轮遍历
            active = [t for t in list(self.targets) if t.is_running]
            if active:
                results = []
                # 按并发上限分波执行，每波后检查停止请求
                chunk_size = max(1, self.max_workers)
                for start in range(0, len(active), chunk_size):
                    if self._stop:
                        break
                    results.extend(ping_batch(
                        active[start:start + chunk_size],
                        max_workers=self.max_workers,
                        timeout=self.timeout,
                        packet_size=self.packet_size,
                        ttl=self.ttl))
                if results and not self._stop:
                    self.batch_complete.emit(results)
            for _ in range(self.interval):
                if self._stop:
                    break
                self.msleep(1000)
        self.log_message.emit("监控已停止")

    def stop(self):
        self._stop = True


class ResolveWorker(QThread):
    """后台线程并行解析域名 -> IPv4，避免阻塞 GUI 主线程"""
    resolve_done = pyqtSignal(list)  # [(target, ip), ...]

    OVERALL_TIMEOUT = 30  # 整体最长等待秒数，慢 DNS 不再卡住

    def __init__(self, targets):
        super().__init__()
        self.targets = targets
        self._stop = False

    def stop(self):
        self._stop = True
        self.requestInterruption()

    @staticmethod
    def _resolve_target(target):
        if is_ip_address(target.address):
            hostname = resolve_hostname(target.address)
            return target, target.address, ("" if hostname == target.address else hostname)
        return target, resolve_to_ipv4(target.address), target.address

    def run(self):
        results = []
        executor = ThreadPoolExecutor(max_workers=min(50, max(1, len(self.targets))))
        futures = {executor.submit(self._resolve_target, target)
                   for target in self.targets}
        deadline = time.monotonic() + self.OVERALL_TIMEOUT
        try:
            while futures and not self._stop and time.monotonic() < deadline:
                done, futures = wait(futures, timeout=0.2,
                                     return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        target, ip, hostname = future.result()
                        if ip or hostname:
                            results.append((target, ip, hostname))
                    except Exception:
                        pass
        finally:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False)
        if not self._stop:
            self.resolve_done.emit(results)


class MacWorker(QThread):
    """后台线程并行查询 MAC 地址，避免阻塞 GUI 主线程。
    域名目标先解析为 IPv4；查询前先 ping 一次以填充 ARP 缓存。"""

    mac_done = pyqtSignal(list)  # [(target, mac), ...]

    def __init__(self, targets):
        super().__init__()
        self.targets = targets
        self._stop = False

    def stop(self):
        self._stop = True
        self.requestInterruption()

    @staticmethod
    def _query_one(t):
        ip = t.address
        if not is_ip_address(ip):
            # 域名目标：优先用已解析的 IPv4，否则现场解析
            ip = t.resolved_ip or resolve_to_ipv4(ip)
        if not ip:
            return (t, None)
        try:
            icmp_ping(ip, timeout=1)  # 触发 ARP 解析，填充邻居缓存
        except Exception:
            pass
        return (t, get_mac_address(ip))

    def run(self):
        results = []
        executor = ThreadPoolExecutor(max_workers=min(20, max(1, len(self.targets))))
        futures = {executor.submit(self._query_one, target)
                   for target in self.targets}
        deadline = time.monotonic() + 35
        try:
            while futures and not self._stop and time.monotonic() < deadline:
                done, futures = wait(futures, timeout=0.2,
                                     return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        target, mac = future.result()
                        if mac:
                            results.append((target, mac))
                    except Exception:
                        pass
        finally:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False)
        if not self._stop:
            self.mac_done.emit(results)


def _draw_row_selection_frame(painter, option, index):
    """为选中行绘制连续的上下边线，仅在首末列绘制左右边线。"""
    if not (option.state & QStyle.State_Selected):
        return
    pen = painter.pen()
    painter.setPen(QPen(QColor('#3978a8'), 2))
    rect = option.rect.adjusted(0, 0, -1, -1)
    painter.drawLine(rect.topLeft(), rect.topRight())
    painter.drawLine(rect.bottomLeft(), rect.bottomRight())
    if index.column() == 0:
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
    if index.column() == index.model().columnCount() - 1:
        painter.drawLine(rect.topRight(), rect.bottomRight())
    painter.setPen(pen)


class RowSelectionDelegate(QStyledItemDelegate):
    """普通单元格委托：保留默认内容并为整行选中绘制外围框线。"""

    def paint(self, painter, option, index):
        item_option = QStyleOptionViewItem(option)
        item_option.state &= ~QStyle.State_HasFocus
        super().paint(painter, item_option, index)
        _draw_row_selection_frame(painter, option, index)


class CenteredCheckBoxDelegate(QStyledItemDelegate):
    """居中绘制复选框：点击中心切换，点击外围空白高亮整行。"""

    row_select_requested = pyqtSignal(int)

    @staticmethod
    def _indicator_rect(style, option):
        check_option = QStyleOptionButton()
        indicator = style.subElementRect(QStyle.SE_CheckBoxIndicator,
                                         check_option, option.widget)
        return QRect(
            option.rect.center().x() - indicator.width() // 2,
            option.rect.center().y() - indicator.height() // 2,
            indicator.width(), indicator.height()
        )

    def paint(self, painter, option, index):
        style = option.widget.style() if option.widget else QApplication.style()

        # 先绘制单元格背景/选中背景，不绘制默认左对齐复选框和文本
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_option.state &= ~QStyle.State_HasFocus
        item_option.features &= ~QStyleOptionViewItem.HasCheckIndicator
        item_option.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, option.widget)

        check_option = QStyleOptionButton()
        check_option.state = QStyle.State_Enabled
        state = index.data(Qt.CheckStateRole)
        check_option.state |= QStyle.State_On if state == Qt.Checked else QStyle.State_Off
        check_option.rect = self._indicator_rect(style, option)
        style.drawPrimitive(QStyle.PE_IndicatorCheckBox,
                            check_option, painter, option.widget)
        _draw_row_selection_frame(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemIsUserCheckable):
            return False
        keyboard_toggle = (event.type() == QEvent.KeyPress and
                           event.key() in (Qt.Key_Space, Qt.Key_Select))
        mouse_release = (event.type() == QEvent.MouseButtonRelease and
                         event.button() == Qt.LeftButton)
        if mouse_release:
            style = option.widget.style() if option.widget else QApplication.style()
            # 仅点击中心复选框本身才切换；外围空白高亮整行
            if not self._indicator_rect(style, option).contains(event.pos()):
                self.row_select_requested.emit(index.row())
                return True
        elif not keyboard_toggle:
            return False
        new_state = Qt.Unchecked if index.data(Qt.CheckStateRole) == Qt.Checked else Qt.Checked
        return model.setData(index, new_state, Qt.CheckStateRole)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PingInfo - 批量 Ping 与实时监控工具")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumSize(1200, 600)
        self.resize(1400, 700)
        self.targets = []
        self.worker = None
        self._bg_workers = []   # 后台线程（DNS 解析 / MAC 查询）引用
        self._child_windows = []  # 保持本窗口创建的新窗口引用
        self._close_pending = False
        app = QApplication.instance()
        if app is not None:
            windows = getattr(app, "_pinginfo_windows", None)
            if windows is None:
                windows = []
                app._pinginfo_windows = windows
            windows.append(self)
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
        self.table_model = TargetTableModel(self.targets, self)
        self.proxy_model = TargetSortProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 按单元格选择，解析地址、MAC 等内容可独立复制
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setFocusPolicy(Qt.NoFocus)  # 取消点击后的焦点框线
        self.table.setItemDelegate(RowSelectionDelegate(self.table))
        monitor_delegate = CenteredCheckBoxDelegate(self.table)
        monitor_delegate.row_select_requested.connect(self._highlight_row)
        self.table.setItemDelegateForColumn(0, monitor_delegate)
        self.table.setStyleSheet("""
            QTableView {
                background: #ffffff;
                alternate-background-color: #f7f9fc;
                color: #263238;
                border: none;
                outline: none;
                selection-background-color: #c7def2;
                selection-color: #102f49;
            }
            QTableView::item {
                padding: 5px 8px;
                border: none;
            }
            QTableView::item:selected {
                background: #c7def2;
                color: #102f49;
                border: none;
                outline: none;
            }
            QHeaderView::section {
                background: #f2f4f7;
                color: #37474f;
                padding: 7px 6px;
                border: none;
                border-right: 1px solid #e0e4e8;
                border-bottom: 1px solid #d5dadd;
                font-weight: 600;
            }
            QTableCornerButton::section {
                background: #f2f4f7;
                border: none;
                border-bottom: 1px solid #d5dadd;
            }
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        header = self.table.horizontalHeader()
        for idx, _, width in COLUMNS:
            header.resizeSection(idx, width)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(17, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
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
        a = QAction("复制选中单元格", self); a.setShortcut(QKeySequence.Copy)
        a.triggered.connect(self.copy_selected_cells); edm.addAction(a)
        edm.addSeparator()
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
        # 用集合做 O(1) 去重；键含端口，避免 host:80 与 host:443 被误去重
        existing = {(t.address, t.ping_mode, t.tcp_port) for t in self.targets}
        added = []
        for host, mode, port in target_list:
            host = normalize_host(host)  # 清理协议前缀/路径等，统一入口规范化
            if not host:
                continue
            if (host, mode, port) in existing:
                continue
            t = TargetStats(
                address=host,
                hostname=host if not is_ip_address(host) else "",
                ping_mode=mode,
                tcp_port=port,
            )
            existing.add((host, mode, port))
            added.append(t)
        if not added:
            return
        self.table_model.append_targets(added)
        self.update_count()
        # 异步解析域名 -> IPv4
        self._resolve_targets_async(added)

    def _resolve_targets_async(self, targets):
        """后台解析域名 IP，并反向解析 IP 目标的主机名。"""
        if not targets:
            return
        self.status_label.setText("正在解析目标地址和主机名...")
        worker = ResolveWorker(targets)
        worker.resolve_done.connect(self._on_resolve_done)
        self._start_bg_worker(worker)

    def _on_resolve_done(self, results):
        for target, ip, hostname in results:
            if ip:
                target.resolved_ip = ip
            if hostname:
                target.hostname = hostname
        self.table_model.notify_targets((result[0] for result in results), 16, 16)
        self.status_label.setText(f"已解析 {len(results)} 个目标")

    def _start_bg_worker(self, worker):
        """启动后台线程并持有引用，结束后安全清理。"""
        self._bg_workers.append(worker)

        def cleanup():
            if worker in self._bg_workers:
                self._bg_workers.remove(worker)
            worker.deleteLater()

        worker.finished.connect(cleanup)
        worker.start()

    def add_targets_dialog(self):
        dlg = AddTargetsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            targets = dlg.get_targets()
            if targets:
                self.add_targets(targets)
                self.status_label.setText(f"已添加 {len(targets)} 个目标")
                return True
        return False

    def _create_independent_window(self):
        """创建拥有独立目标、模型和后台任务的新主窗口。"""
        window = MainWindow()
        window.ping_interval = self.ping_interval
        window.max_workers = self.max_workers
        window.ping_timeout = self.ping_timeout
        window.packet_size = self.packet_size
        window.icmp_ttl = self.icmp_ttl
        window.default_ping_mode = self.default_ping_mode
        window.default_tcp_port = self.default_tcp_port
        window.setWindowIcon(self.windowIcon())
        self._child_windows.append(window)
        window.destroyed.connect(
            lambda _=None, child=window: self._forget_child_window(child))
        return window

    def _forget_child_window(self, window):
        if window in self._child_windows:
            self._child_windows.remove(window)
        app = QApplication.instance()
        windows = getattr(app, "_pinginfo_windows", []) if app else []
        if window in windows:
            windows.remove(window)

    def reload_targets_dialog(self):
        """在独立的新窗口中添加目标，不修改当前窗口。"""
        window = self._create_independent_window()
        dialog = AddTargetsDialog(window)
        if dialog.exec_() == QDialog.Accepted and dialog.get_targets():
            targets = dialog.get_targets()
            window.add_targets(targets)
            window.status_label.setText(f"已添加 {len(targets)} 个目标")
            window.show()
        else:
            self._forget_child_window(window)
            window.deleteLater()

    def reload_from_file(self):
        """在独立的新窗口中载入文件，不修改当前窗口。"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if not filepath:
            return
        window = self._create_independent_window()
        if window._load_file(filepath):
            window.show()
            window.status_label.setText("已从文件载入目标")
        else:
            self._forget_child_window(window)
            window.deleteLater()

    def load_from_file(self):
        fp, _ = QFileDialog.getOpenFileName(self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if fp:
            self._load_file(fp)

    def _load_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取文件失败: {e}")
            return False
        tl = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            host, port, valid = parse_host_port(line, self.default_tcp_port)
            if not valid:
                continue
            explicit_tcp = line.startswith('[') and ']:' in line
            explicit_tcp = explicit_tcp or (line.count(':') == 1 and line.rsplit(':', 1)[1].isdigit())
            if explicit_tcp:
                tl.append((host, "TCP", port)); continue
            # 展开 IP 范围
            for ip in expand_ip_range(host):
                tl.append((ip, self.default_ping_mode, port))
        if tl:
            self.add_targets(tl)
            self.status_label.setText(f"从文件载入了 {len(tl)} 个目标")
            return True
        QMessageBox.information(self, "提示", "文件中没有有效的 Ping 目标")
        return False

    def delete_selected(self):
        targets = self._selected_targets()
        if not targets:
            return
        # 模型原地更新列表，保证运行中的 PingWorker 继续引用同一对象。
        self.table_model.remove_targets(targets)
        self.update_count()

    def clear_all(self):
        if not self.targets:
            return
        if QMessageBox.question(self, "确认", "确定要清空所有目标吗?") == QMessageBox.Yes:
            self.stop_monitoring()
            self.table_model.clear_targets()
            self.update_count()
            self.status_label.setText("已清空所有目标")

    def reset_stats(self):
        for target in self.targets:
            target.reset()
        self.table_model.notify_all(4, 17)
        self.status_label.setText("统计数据已重置")

    def toggle_selected(self, enabled):
        targets = self._selected_targets()
        for target in targets:
            target.is_running = enabled
        self.table_model.notify_targets(targets)
        self.update_count()

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
        """非阻塞请求停止；旧线程真正结束前不允许启动新监控。"""
        worker = self.worker
        if not worker:
            return
        worker.stop()
        try:
            worker.batch_complete.disconnect(self.on_batch_complete)
            worker.log_message.disconnect(self.on_log_message)
        except (TypeError, RuntimeError):
            pass
        self.act_start.setEnabled(False)
        self.act_stop.setEnabled(False)
        self.status_label.setText("正在停止监控...")

        def finished():
            if self.worker is worker:
                self.worker = None
            self.act_start.setEnabled(True)
            self.progress.setVisible(False)
            self.status_label.setText("监控已停止")
            worker.deleteLater()

        if worker.isRunning():
            worker.finished.connect(finished)
        else:
            finished()

    def on_batch_complete(self, results):
        for target, result in results:
            if result.success:
                target.update_success(result.rtt, result.ttl)
                if result.response_address:
                    target.response_address = result.response_address
            else:
                target.update_fail(result.error or "失败", result.rtt)
        self.table_model.notify_targets((target for target, _ in results), 4, 17)
        self.update_count()

    def on_log_message(self, msg):
        self.status_label.setText(msg)

    def _highlight_row(self, row):
        """监控列非中心区域被点击时，仅高亮整行，不改变复选框状态。"""
        if 0 <= row < self.proxy_model.rowCount():
            self.table.clearSelection()
            self.table.selectRow(row)

    def _target_from_index(self, index):
        """把排序后的视图索引映射为稳定的目标对象。"""
        return index.data(TARGET_ROLE) if index.isValid() else None

    def _selected_targets(self):
        """按当前视觉顺序返回去重后的选中目标。"""
        targets = []
        seen = set()
        for index in sorted(self.table.selectedIndexes(), key=lambda item: item.row()):
            target = self._target_from_index(index)
            if target is not None and id(target) not in seen:
                seen.add(id(target))
                targets.append(target)
        return targets

    def copy_selected_cells(self):
        """按行列顺序复制选中单元格；多单元格使用制表符和换行分隔"""
        indexes = sorted(self.table.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indexes:
            return
        selected = {(i.row(), i.column()) for i in indexes}
        min_row, max_row = indexes[0].row(), indexes[-1].row()
        min_col = min(i.column() for i in indexes)
        max_col = max(i.column() for i in indexes)
        lines = []
        for row in range(min_row, max_row + 1):
            values = []
            for col in range(min_col, max_col + 1):
                index = self.proxy_model.index(row, col)
                value = index.data(Qt.DisplayRole) if (row, col) in selected else ""
                values.append("" if value is None else str(value))
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))
        self.status_label.setText(f"已复制 {len(indexes)} 个单元格")

    def _show_context_menu(self, pos):
        """表格右键菜单。右键单元格时保留单元格级选择，便于精确复制"""
        index = self.table.indexAt(pos)
        menu = QMenu(self)
        if not index.isValid():
            # 空白区域仅提供可执行的全局操作
            act_add = menu.addAction("添加目标...")
            action = menu.exec_(self.table.viewport().mapToGlobal(pos))
            if action == act_add:
                self.add_targets_dialog()
            return

        if not self.table.selectionModel().isSelected(index):
            self.table.clearSelection()
            self.table.setCurrentIndex(index)
        context_target = self._target_from_index(index)
        act_details = menu.addAction("详情...")
        menu.addSeparator()
        act_copy = menu.addAction("复制单元格内容")
        menu.addSeparator()
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
        if action == act_details and context_target is not None:
            TargetDetailsDialog(context_target, self).exec_()
        elif action == act_copy:
            self.copy_selected_cells()
        elif action == act_add:
            self.add_targets_dialog()
        elif action == act_del:
            self.delete_selected()
        elif action == act_enable:
            self.toggle_selected(True)
        elif action == act_disable:
            self.toggle_selected(False)
        elif action == act_check_all:
            self.table_model.set_all_checked(True)
        elif action == act_uncheck_all:
            self.table_model.set_all_checked(False)
        elif action == act_mac:
            self.query_mac_addresses()
        elif action == act_export:
            self.export_results("csv")

    def update_count(self):
        total = len(self.targets)
        active = sum(1 for t in self.targets if t.is_running)
        self.count_label.setText(f"目标数: {total} (启用: {active})")

    def query_mac_addresses(self):
        if not self.targets:
            QMessageBox.information(self, "提示", "没有目标可查询"); return
        # 优先查询选中的条目；未选中则查询全部启用中的目标
        candidates = self._selected_targets()
        if not candidates:
            candidates = [target for target in self.targets if target.is_running]
        if not candidates:
            self.status_label.setText("没有可查询的目标"); return
        self.status_label.setText(f"正在后台查询 {len(candidates)} 个目标的 MAC 地址...")
        worker = MacWorker(candidates)
        worker.mac_done.connect(self._on_mac_done)
        self._start_bg_worker(worker)

    def _on_mac_done(self, results):
        for target, mac in results:
            target.mac_address = mac
        self.table_model.notify_targets((target for target, _ in results), 15, 15)
        if results:
            self.status_label.setText(f"MAC 地址查询完成（获取 {len(results)} 个）")
        else:
            self.status_label.setText(
                "未获取到 MAC 地址（仅同一子网且可达的目标可查询）")

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
        from . import __version__
        QMessageBox.about(self, "关于 PingInfo",
            f"<h2>PingInfo v{__version__}</h2><p>批量 Ping 与实时监控工具</p>"
            "<ul><li>支持 ICMP Ping 和 TCP Ping</li><li>支持 IPv4 / IPv6</li>"
            "<li>批量目标管理和实时监控</li><li>响应时间、丢包率、延迟统计</li>"
            "<li>TTL、MAC 地址查询</li><li>导出 TXT / CSV / HTML / XML</li></ul>"
            "<p>支持拖放文本文件导入地址</p>")

    def export_results(self, fmt):
        if not self.targets:
            QMessageBox.information(self, "提示", "没有数据可导出"); return

        # 获取表格选中的目标和勾选的目标
        selected_targets = self._selected_targets()
        selected_count = len(selected_targets)
        checked_count = sum(1 for target in self.targets if target.selected)

        # 弹出导出选择对话框
        dlg = ExportSelectionDialog(self, len(self.targets), selected_count, checked_count)
        if dlg.exec_() != QDialog.Accepted:
            return

        mode = dlg.get_export_mode()
        if mode == "checked":
            targets_to_export = [t for t in self.targets if t.selected]
        elif mode == "selected" and selected_count > 0:
            targets_to_export = selected_targets
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
        mime = event.mimeData()
        supported_urls = mime.hasUrls() and any(
            u.isLocalFile() and u.toLocalFile().lower().endswith(('.txt', '.csv', '.list', '.dat'))
            for u in mime.urls())
        if supported_urls or (mime.hasText() and mime.text().strip()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        handled = False
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fp = url.toLocalFile()
                if fp.lower().endswith(('.txt', '.csv', '.list', '.dat')):
                    self._load_file(fp)
                    handled = True
        elif event.mimeData().hasText():
            text = event.mimeData().text().strip()
            tl = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                host, port, valid = parse_host_port(line, self.default_tcp_port)
                if not valid:
                    continue
                explicit_tcp = line.startswith('[') and ']:' in line
                explicit_tcp = explicit_tcp or (line.count(':') == 1 and line.rsplit(':', 1)[1].isdigit())
                if explicit_tcp:
                    tl.append((host, "TCP", port)); continue
                for ip in expand_ip_range(host):
                    tl.append((ip, self.default_ping_mode, port))
            if tl:
                self.add_targets(tl)
                self.status_label.setText(f"从拖放添加了 {len(tl)} 个目标")
                handled = True
        if handled:
            event.acceptProposedAction()
        else:
            event.ignore()
            self.status_label.setText("拖放内容不受支持或未包含有效目标")

    def closeEvent(self, event):
        """非阻塞等待后台线程结束，避免关闭窗口时 GUI 假死。"""
        running_bg = any(w.isRunning() for w in self._bg_workers)
        running_monitor = bool(self.worker and self.worker.isRunning())
        if running_monitor or running_bg:
            event.ignore()
            if not self._close_pending:
                self._close_pending = True
                self.stop_monitoring()
                for worker in self._bg_workers:
                    stop = getattr(worker, "stop", None)
                    if stop:
                        stop()
                self.status_label.setText("正在结束后台任务，完成后自动关闭...")
            QTimer.singleShot(200, self.close)
            return
        app = QApplication.instance()
        windows = getattr(app, "_pinginfo_windows", []) if app else []
        if self in windows:
            windows.remove(self)
        event.accept()
