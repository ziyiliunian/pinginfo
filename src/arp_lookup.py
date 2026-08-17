# -*- coding: utf-8 -*-
"""
ARP 查询模块
通过系统命令查询局域网内 IP 的 MAC 地址
"""

import subprocess
import re
import platform
from typing import Optional


def get_mac_address(ip: str) -> Optional[str]:
    """
    查询指定 IP 的 MAC 地址
    依次尝试 ip neigh、arp -n 命令
    仅对同一子网的 IP 有效
    """
    # 尝试使用 ip neigh（更现代）
    mac = _get_mac_ip_neigh(ip)
    if mac:
        return mac

    # 尝试使用 arp -n
    mac = _get_mac_arp(ip)
    if mac:
        return mac

    return None


def _get_mac_ip_neigh(ip: str) -> Optional[str]:
    """使用 ip neigh 命令查询 MAC 地址"""
    try:
        result = subprocess.run(
            ['ip', 'neigh', 'show', ip],
            capture_output=True,
            text=True,
            timeout=3
        )
        output = result.stdout.strip()
        if output:
            # 输出格式: 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
            mac_match = re.search(
                r'([0-9a-fA-F]{2}[:]){5}[0-9a-fA-F]{2}',
                output
            )
            if mac_match:
                return mac_match.group(0).upper()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def _get_mac_arp(ip: str) -> Optional[str]:
    """使用 arp -n 命令查询 MAC 地址"""
    try:
        result = subprocess.run(
            ['arp', '-n', ip],
            capture_output=True,
            text=True,
            timeout=3
        )
        output = result.stdout + result.stderr
        if output:
            # 输出格式:
            # Address     HWtype  HWaddress       Flags Mask  Iface
            # 192.168.1.1 ether   aa:bb:cc:dd:ee:ff  C         eth0
            mac_match = re.search(
                r'([0-9a-fA-F]{2}[:]){5}[0-9a-fA-F]{2}',
                output
            )
            if mac_match:
                return mac_match.group(0).upper()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def batch_get_mac_addresses(ip_list):
    """
    批量查询 MAC 地址
    返回 {ip: mac_address} 字典
    """
    result = {}
    for ip in ip_list:
        mac = get_mac_address(ip)
        if mac:
            result[ip] = mac
    return result
