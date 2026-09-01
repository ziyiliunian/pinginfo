# -*- coding: utf-8 -*-
"""
数据模型模块
定义目标统计数据的结构和方法
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TargetStats:
    """单个 ping 目标的统计数据"""
    address: str
    hostname: str = ""
    ping_mode: str = "ICMP"          # "ICMP" 或 "TCP"
    tcp_port: int = 80
    total_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    last_rtt: Optional[float] = None
    min_rtt: Optional[float] = None
    max_rtt: Optional[float] = None
    sum_rtt: float = 0.0
    rtt_sample_count: int = 0
    rtt_history: List[Optional[float]] = field(default_factory=list)
    last_ttl: Optional[int] = None
    last_success_time: Optional[str] = None
    last_fail_time: Optional[str] = None
    mac_address: Optional[str] = None
    is_running: bool = True
    selected: bool = False          # 是否被勾选（用于导出选择）
    sequence_number: int = 0        # 固定序号，不随排序变化
    last_error: Optional[str] = None
    resolved_ip: Optional[str] = None  # 解析地址：当 address 为域名时存储解析后的 IPv4
    response_address: Optional[str] = None  # 最近一次实际响应的 IP 地址
    # 保留最近 20 次的 RTT 用于计算
    _max_history: int = 20

    @property
    def loss_rate(self) -> float:
        """丢包率百分比"""
        if self.total_count == 0:
            return 0.0
        return (self.fail_count / self.total_count) * 100.0

    @property
    def avg_rtt(self) -> Optional[float]:
        """平均延迟，仅统计成功解析到 RTT 的样本。"""
        if self.rtt_sample_count == 0:
            return None
        return self.sum_rtt / self.rtt_sample_count

    @property
    def status_text(self) -> str:
        """状态文本"""
        if not self.is_running:
            return "已停止"
        if self.total_count == 0:
            return "等待中"
        if self.last_error is None and self.last_rtt is not None:
            return "成功"
        if self.last_error is not None:
            return "失败"
        return "运行中"

    def update_success(self, rtt: Optional[float], ttl: Optional[int] = None):
        """更新成功结果。rtt 为 None 时（如解析失败）仅计数，不参与统计运算"""
        self.total_count += 1
        self.success_count += 1
        self.last_rtt = rtt
        if rtt is not None:
            self.sum_rtt += rtt
            self.rtt_sample_count += 1
            if self.min_rtt is None or rtt < self.min_rtt:
                self.min_rtt = rtt
            if self.max_rtt is None or rtt > self.max_rtt:
                self.max_rtt = rtt
        if ttl is not None:
            self.last_ttl = ttl
        self.last_success_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_error = None
        # 更新历史
        self.rtt_history.append(rtt)
        if len(self.rtt_history) > self._max_history:
            self.rtt_history.pop(0)

    def update_fail(self, error: str = "", rtt: Optional[float] = None):
        """更新失败结果；连接被拒绝等场景可保留已测得的 RTT。"""
        self.total_count += 1
        self.fail_count += 1
        self.last_rtt = rtt
        self.last_fail_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_error = error if error else "请求失败"
        self.rtt_history.append(None)
        if len(self.rtt_history) > self._max_history:
            self.rtt_history.pop(0)

    def reset(self):
        """重置统计数据"""
        self.total_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.last_rtt = None
        self.min_rtt = None
        self.max_rtt = None
        self.sum_rtt = 0.0
        self.rtt_sample_count = 0
        self.rtt_history.clear()
        self.last_ttl = None
        self.last_success_time = None
        self.last_fail_time = None
        self.last_error = None
        self.response_address = None

    def to_dict(self) -> dict:
        """转换为字典（用于导出）"""
        return {
            "sequence_number": self.sequence_number,
            "address": self.address,
            "ping_mode": self.ping_mode,
            "tcp_port": self.tcp_port,
            "status": self.status_text,
            "last_rtt": f"{self.last_rtt:.2f}" if self.last_rtt is not None else "",
            "loss_rate": f"{self.loss_rate:.1f}",
            "succeed_count": self.success_count,
            "failed_count": self.fail_count,
            "total_count": self.total_count,
            "avg_rtt": f"{self.avg_rtt:.2f}" if self.avg_rtt is not None else "",
            "min_rtt": f"{self.min_rtt:.2f}" if self.min_rtt is not None else "",
            "max_rtt": f"{self.max_rtt:.2f}" if self.max_rtt is not None else "",
            "ttl": str(self.last_ttl) if self.last_ttl is not None else "",
            "last_success": self.last_success_time or "",
            "last_fail": self.last_fail_time or "",
            "mac_address": self.mac_address or "",
            "resolved_ip": self.resolved_ip or "",
            "response_address": self.response_address or "",
            "last_error": self.last_error or "",
        }
