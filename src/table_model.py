# -*- coding: utf-8 -*-
"""目标统计表格的模型/视图实现。"""

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt5.QtGui import QColor


COLUMNS = [
    (0, "监控", 58), (1, "序号", 50), (2, "地址", 150),
    (3, "Ping方式", 70), (4, "状态", 60), (5, "响应时间(ms)", 100),
    (6, "丢包率(%)", 80), (7, "成功", 50), (8, "失败", 50),
    (9, "平均(ms)", 90), (10, "最小(ms)", 80), (11, "最大(ms)", 80),
    (12, "TTL", 50), (13, "最近成功时间", 150), (14, "最近失败时间", 150),
    (15, "解析地址", 130), (16, "错误信息", 200),
]

TARGET_ROLE = Qt.UserRole + 1
SORT_ROLE = Qt.UserRole + 2


class TargetTableModel(QAbstractTableModel):
    """以 ``TargetStats`` 列表为唯一数据源的表格模型。"""

    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = targets

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.targets)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section][1]
        return None

    def target_at(self, row):
        return self.targets[row] if 0 <= row < len(self.targets) else None

    @staticmethod
    def _display_value(target, row, column):
        """按需计算单个单元格文本。

        旧实现每读取一个单元格都会格式化全部 17 列；1000 行重绘时会产生
        大量无用字符串。逐列返回可把模型读取成本限制在当前可见单元格。
        """
        if column == 0:
            return ""
        if column == 1:
            return str(target.sequence_number or row + 1)
        if column == 2:
            return target.address
        if column == 3:
            return (f"TCP:{target.tcp_port}"
                    if target.ping_mode == "TCP" else target.ping_mode)
        if column == 4:
            return target.status_text
        if column == 5:
            return f"{target.last_rtt:.2f}" if target.last_rtt is not None else "-"
        if column == 6:
            return f"{target.loss_rate:.1f}"
        if column == 7:
            return str(target.success_count)
        if column == 8:
            return str(target.fail_count)
        if column == 9:
            return f"{target.avg_rtt:.2f}" if target.avg_rtt is not None else "-"
        if column == 10:
            return f"{target.min_rtt:.2f}" if target.min_rtt is not None else "-"
        if column == 11:
            return f"{target.max_rtt:.2f}" if target.max_rtt is not None else "-"
        if column == 12:
            return str(target.last_ttl) if target.last_ttl is not None else "-"
        if column == 13:
            return target.last_success_time or "-"
        if column == 14:
            return target.last_fail_time or "-"
        if column == 15:
            return target.resolved_ip or "-"
        if column == 16:
            return target.last_error or ""
        return None

    @staticmethod
    def _sort_value(target, row, column):
        """返回当前列的原始排序值，避免比较时构造整行元组。"""
        if column == 0:
            return target.selected
        if column == 1:
            return target.sequence_number or row + 1
        if column == 2:
            return target.address.casefold()
        if column == 3:
            return (f"TCP:{target.tcp_port}" if target.ping_mode == "TCP"
                    else target.ping_mode).casefold()
        if column == 4:
            return target.status_text
        if column == 5:
            return target.last_rtt
        if column == 6:
            return target.loss_rate
        if column == 7:
            return target.success_count
        if column == 8:
            return target.fail_count
        if column == 9:
            return target.avg_rtt
        if column == 10:
            return target.min_rtt
        if column == 11:
            return target.max_rtt
        if column == 12:
            return target.last_ttl
        if column == 13:
            return target.last_success_time
        if column == 14:
            return target.last_fail_time
        if column == 15:
            return target.resolved_ip.casefold() if target.resolved_ip else None
        if column == 16:
            return target.last_error.casefold() if target.last_error else None
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        target = self.target_at(index.row())
        if target is None:
            return None
        column = index.column()
        if role == Qt.DisplayRole:
            return self._display_value(target, index.row(), column)
        if role == Qt.CheckStateRole and column == 0:
            return Qt.Checked if target.selected else Qt.Unchecked
        if role == TARGET_ROLE:
            return target
        if role == SORT_ROLE:
            return self._sort_value(target, index.row(), column)
        if role == Qt.ToolTipRole and column == 0:
            return "勾选后可按勾选范围导出；与行选择相互独立"
        if role == Qt.TextAlignmentRole and column == 0:
            return Qt.AlignCenter
        if role == Qt.ForegroundRole:
            if not target.is_running:
                return QColor("#999999")
            if column == 4:
                return {
                    "成功": QColor("#4CAF50"),
                    "失败": QColor("#f44336"),
                    "等待中": QColor("#FF9800"),
                }.get(target.status_text, QColor("#263238"))
            return QColor("#263238")
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.CheckStateRole:
            return False
        target = self.target_at(index.row())
        if target is None:
            return False
        checked = value == Qt.Checked
        if target.selected == checked:
            return False
        target.selected = checked
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, SORT_ROLE])
        return True

    def append_targets(self, targets):
        if not targets:
            return
        first = len(self.targets)
        self.beginInsertRows(QModelIndex(), first, first + len(targets) - 1)
        self.targets.extend(targets)
        self.endInsertRows()

    def remove_targets(self, targets):
        identities = {id(target) for target in targets}
        if not identities:
            return
        remaining = [target for target in self.targets if id(target) not in identities]
        if len(remaining) == len(self.targets):
            return
        self.beginResetModel()
        self.targets[:] = remaining
        self.endResetModel()

    def clear_targets(self):
        if not self.targets:
            return
        self.beginResetModel()
        self.targets.clear()
        self.endResetModel()

    def notify_targets(self, targets, first_column=0, last_column=None):
        if last_column is None:
            last_column = len(COLUMNS) - 1
        rows_by_id = {id(target): row for row, target in enumerate(self.targets)}
        rows = sorted({rows_by_id[id(target)] for target in targets
                       if id(target) in rows_by_id})
        if not rows:
            return
        # 合并连续行，避免大批量 Ping 结果触发数百次代理模型重排。
        ranges = []
        first = previous = rows[0]
        for row in rows[1:]:
            if row != previous + 1:
                ranges.append((first, previous))
                first = row
            previous = row
        ranges.append((first, previous))
        for first, last in ranges:
            self.dataChanged.emit(
                self.index(first, first_column),
                self.index(last, last_column),
                [Qt.DisplayRole, Qt.ForegroundRole, Qt.CheckStateRole, SORT_ROLE],
            )

    def notify_all(self, first_column=0, last_column=None):
        if not self.targets:
            return
        if last_column is None:
            last_column = len(COLUMNS) - 1
        self.dataChanged.emit(
            self.index(0, first_column),
            self.index(len(self.targets) - 1, last_column),
            [Qt.DisplayRole, Qt.ForegroundRole, Qt.CheckStateRole, SORT_ROLE],
        )

    def set_all_checked(self, checked):
        changed = [target for target in self.targets if target.selected != checked]
        for target in changed:
            target.selected = checked
        self.notify_targets(changed, 0, 0)


class TargetSortProxyModel(QSortFilterProxyModel):
    """按原始值排序，并保证缺失值在升降序中始终置底。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_order = Qt.AscendingOrder
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    def sort(self, column, order=Qt.AscendingOrder):
        self._sort_order = order
        super().sort(column, order)

    def lessThan(self, left, right):
        left_value = left.data(SORT_ROLE)
        right_value = right.data(SORT_ROLE)
        if left_value is None or right_value is None:
            if left_value is None and right_value is None:
                return left.row() < right.row()
            if self._sort_order == Qt.AscendingOrder:
                return left_value is not None
            return left_value is None
        try:
            return left_value < right_value
        except TypeError:
            return str(left_value).casefold() < str(right_value).casefold()
