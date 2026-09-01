# -*- coding: utf-8 -*-
"""
Ping 核心模块
实现 ICMP Ping 和 TCP Ping 功能
"""

import subprocess
import re
import socket
import time
import platform
import ipaddress
import sys
from dataclasses import dataclass
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class PingResult:
    """单次 ping 的结果"""
    success: bool
    rtt: Optional[float] = None       # 响应时间（毫秒）
    ttl: Optional[int] = None         # TTL 值
    error: Optional[str] = None       # 错误信息
    response_address: Optional[str] = None  # 实际响应的 IP 地址


# 单次展开的最大 IP 数量上限，防止 CIDR/范围展开耗尽内存
MAX_EXPAND_COUNT = 65535


def expand_ip_range(ip_str: str) -> List[str]:
    """
    展开 IP 范围为单独的 IP 列表
    支持格式:
      - 192.168.0.10-192.168.0.201  (完整范围)
      - 192.168.0.10-201            (简写范围)
      - 192.168.0.0/24              (CIDR)
      - 192.168.0.1                 (单个IP)
    超过 MAX_EXPAND_COUNT 时不展开，原样返回，避免内存耗尽/界面卡死。
    """
    ip_str = ip_str.strip()

    # CIDR 格式: 192.168.0.0/24
    if '/' in ip_str:
        try:
            net = ipaddress.ip_network(ip_str, strict=False)
            if net.num_addresses > MAX_EXPAND_COUNT:
                return [ip_str]  # 规模过大，不展开
            return [str(ip) for ip in net.hosts()] or [str(net.network_address)]
        except ValueError:
            return [ip_str]

    # 范围格式: 192.168.0.10-192.168.0.201 或 192.168.0.10-201
    if '-' in ip_str:
        parts = ip_str.split('-', 1)
        start_str = parts[0].strip()
        end_str = parts[1].strip()
        # 简写格式: 192.168.0.10-201 -> 192.168.0.201
        if '.' not in end_str and end_str.isdigit():
            prefix = start_str.rsplit('.', 1)[0]
            end_str = f"{prefix}.{end_str}"
        try:
            start = int(ipaddress.IPv4Address(start_str))
            end = int(ipaddress.IPv4Address(end_str))
            if start <= end:
                count = end - start + 1
                if count > MAX_EXPAND_COUNT:
                    return [ip_str]  # 范围过大，不展开
                return [str(ipaddress.IPv4Address(i)) for i in range(start, end + 1)]
        except (ValueError, ipaddress.AddressValueError):
            pass
        return [ip_str]

    # 单个 IP 或域名
    return [ip_str]


def _parse_ping_output(output: str, is_windows: bool = False) -> PingResult:
    """
    解析系统 ping 命令的输出
    支持 Linux 和 Windows 格式
    """
    if not output:
        return PingResult(success=False, error="无输出")

    # Linux 成功输出示例:
    # 64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=10.5 ms
    # Windows 成功输出示例:
    # Reply from 8.8.8.8: bytes=32 time=10ms TTL=117

    # 检查是否成功
    success_patterns = [
        r'bytes from',           # Linux
        r'Reply from',           # Windows
        r'来自.*的回复',          # Windows 中文
        r'bytes of data',        # Linux IPv6
    ]

    is_success = any(re.search(p, output, re.IGNORECASE) for p in success_patterns)

    # 检查明确的失败标志
    fail_patterns = [
        r'100% packet loss',
        r'100% 丢包',
        r'Request timed out',
        r'请求超时',
        r'Destination Host Unreachable',
        r'目标主机不可达',
        r'Name or service not known',
        r'unknown host',
        r'Network is unreachable',
        r'网络不可达',
        r'connect: Network is unreachable',
    ]

    is_fail = any(re.search(p, output, re.IGNORECASE) for p in fail_patterns)

    if is_fail or not is_success:
        # 提取错误信息
        for pattern in fail_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return PingResult(success=False, error=match.group(0))
        return PingResult(success=False, error="Ping 失败")

    # 提取实际响应 IP，兼容 host (IP)、IPv4、IPv6 和中英文输出。
    response_address = None
    candidates = re.findall(r'\(([0-9a-fA-F:.%]+)\)', output)
    for pattern in (
            r'bytes from\s+(\[?[0-9a-fA-F:.%]+\]?:?)',
            r'Reply from\s+(\[?[0-9a-fA-F:.%]+\]?:?)',
            r'来自\s*(\[?[0-9a-fA-F:.%]+\]?)\s*的回复'):
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            candidates.append(match.group(1))
    for candidate in candidates:
        candidate = candidate.strip('[]')
        for value in (candidate, candidate[:-1] if candidate.endswith(':') else candidate):
            try:
                ipaddress.ip_address(value.split('%', 1)[0])
                response_address = value
                break
            except ValueError:
                continue
        if response_address:
            break

    # 提取 RTT（响应时间），兼容英文 "time=10.5 ms" 与中文 Windows "时间=10ms"/"时间<1ms"
    rtt_patterns = [
        r'time[=<]\s*([\d.]+)\s*ms',   # time=10ms / time<1ms
        r'时间[=<]\s*([\d.]+)\s*ms',    # 时间=10ms / 时间<1ms
        r'time[=<]\s*([\d.]+)',        # 无单位
        r'时间[=<]\s*([\d.]+)',
    ]
    rtt = None
    for p in rtt_patterns:
        m = re.search(p, output, re.IGNORECASE)
        if m:
            try:
                rtt = float(m.group(1))
                break
            except ValueError:
                pass

    # 提取 TTL，兼容英文/中文（中文 Windows 通常仍输出 TTL=）
    ttl = None
    for p in (r'ttl[=<]?\s*(\d+)',):
        m = re.search(p, output, re.IGNORECASE)
        if m:
            try:
                ttl = int(m.group(1))
                break
            except ValueError:
                pass

    return PingResult(success=True, rtt=rtt, ttl=ttl,
                      response_address=response_address)


def icmp_ping(host: str, timeout: int = 3, packet_size: int = 56, ttl: int = 0) -> PingResult:
    """
    使用系统 ping 命令进行 ICMP Ping
    支持 IPv4 和 IPv6，自动检测
    packet_size: ICMP 包大小（字节），默认 56
    ttl: TTL 起始值，0 表示使用系统默认
    """
    is_win = platform.system() == "Windows"
    # 只有 0 表示系统默认；Windows 默认负载为 32，设置 56 时必须显式传 -l 56
    use_default_size = packet_size == 0

    if is_win:
        cmd = ['ping', '-n', '1', '-w', str(timeout * 1000)]
        if not use_default_size:
            cmd.extend(['-l', str(packet_size)])
        if ttl > 0:
            cmd.extend(['-i', str(ttl)])
        cmd.append(host)
    else:
        # Linux: -c 1 发送1个包, -W 超时(秒), -s 包大小, -t TTL
        cmd = ['ping', '-c', '1', '-W', str(timeout)]
        if not use_default_size:
            cmd.extend(['-s', str(packet_size)])
        if ttl > 0:
            cmd.extend(['-t', str(ttl)])
        cmd.append(host)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5
        )
        output = result.stdout + result.stderr
        return _parse_ping_output(output, is_win)
    except subprocess.TimeoutExpired:
        return PingResult(success=False, error="命令超时")
    except FileNotFoundError:
        return PingResult(success=False, error="ping 命令未找到")
    except Exception as e:
        return PingResult(success=False, error=str(e))


def tcp_ping(host: str, port: int, timeout: int = 3) -> PingResult:
    """
    TCP Ping - 测试目标端口的 TCP 连接
    支持 IPv4 和 IPv6
    """
    start_time = time.time()
    sock = None
    try:
        # create_connection 自动处理 IPv4/IPv6
        sock = socket.create_connection((host, port), timeout=timeout)
        rtt = (time.time() - start_time) * 1000
        response_address = sock.getpeername()[0]
        sock.close()
        sock = None  # 置 None，避免 finally 中重复 close
        return PingResult(success=True, rtt=round(rtt, 2),
                          response_address=response_address)
    except socket.timeout:
        return PingResult(success=False, error="连接超时")
    except ConnectionRefusedError:
        # 连接被拒绝说明主机可达但端口未开放
        rtt = (time.time() - start_time) * 1000
        return PingResult(success=False, error="连接被拒绝", rtt=round(rtt, 2))
    except socket.gaierror as e:
        return PingResult(success=False, error=f"域名解析失败: {e}")
    except OSError as e:
        return PingResult(success=False, error=str(e))
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def resolve_hostname(ip: str, timeout: float = 2.0) -> str:
    """在可终止子进程中反向解析主机名，避免系统解析器无限阻塞。"""
    script = (
        "import socket,sys; "
        "print(socket.gethostbyaddr(sys.argv[1])[0])"
    )
    try:
        result = subprocess.run(
            [sys.executable, '-c', script, ip],
            capture_output=True, text=True, timeout=max(0.1, timeout),
            check=False,
        )
        hostname = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        return hostname or ip
    except (subprocess.TimeoutExpired, OSError):
        return ip


def is_ip_address(address: str) -> bool:
    """判断字符串是否为合法 IPv4 或 IPv6 地址。"""
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def parse_host_port(value: str, default_port: int):
    """解析域名/IPv4/IPv6 与可选端口，支持 host:port 和 [IPv6]:port。"""
    value = value.strip()
    host, port = value, default_port
    if value.startswith('['):
        end = value.find(']')
        if end > 0:
            host = value[1:end]
            suffix = value[end + 1:]
            if suffix:
                if not suffix.startswith(':') or not suffix[1:].isdigit():
                    return value, default_port, False
                port = int(suffix[1:])
    elif value.count(':') == 1:
        candidate_host, candidate_port = value.rsplit(':', 1)
        if candidate_port.isdigit():
            host, port = candidate_host, int(candidate_port)
    # 裸多冒号字符串按 IPv6 地址处理，不猜测末段端口
    if not host or not 1 <= port <= 65535:
        return value, default_port, False
    return host, port, True


def normalize_host(line: str) -> str:
    """
    规范化用户输入的目标地址：
    - 去除首尾空白
    - 去除协议前缀（http://、https://、ftp://）
    - 去除 URL 路径与尾部斜杠（保留 host:port、CIDR 写法）
    例: "http://www.example.com/index.html" -> "www.example.com"
        "www.example.com/" -> "www.example.com"
        "192.168.0.0/24"  -> "192.168.0.0/24"（CIDR 保留）
    """
    s = line.strip()
    lowered = s.lower()
    for scheme in ("http://", "https://", "ftp://"):
        if lowered.startswith(scheme):
            s = s[len(scheme):]
            break
    else:
        # 无协议前缀：仅当斜杠部分不是 CIDR（host 非 IP 或掩码非数字）时才去掉路径
        if '/' in s:
            head, _, tail = s.partition('/')
            if not (tail.isdigit() and is_ip_address(head)):
                s = head
        return s
    # 有协议前缀：去掉路径部分
    if '/' in s:
        s = s.split('/', 1)[0]
    return s


def resolve_to_ipv4(address: str, timeout: float = 2.0) -> Optional[str]:
    """将域名解析为 IPv4；使用标准库子进程提供真实、可终止的超时。"""
    address = normalize_host(address)
    if is_ip_address(address):
        return None
    script = (
        "import socket,sys; "
        "infos=socket.getaddrinfo(sys.argv[1],None,socket.AF_INET,socket.SOCK_STREAM); "
        "print(infos[0][4][0] if infos else '')"
    )
    try:
        result = subprocess.run(
            [sys.executable, '-c', script, address],
            capture_output=True, text=True, timeout=max(0.1, timeout),
            check=False
        )
        ip = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if ip:
            ipaddress.IPv4Address(ip)
            return ip
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def ping_target(stats, timeout: int = 3, packet_size: int = 56, ttl: int = 0) -> PingResult:
    """
    对一个 TargetStats 对象执行 ping 操作
    根据 ping_mode 选择 ICMP 或 TCP
    """
    if stats.ping_mode == "TCP":
        return tcp_ping(stats.address, stats.tcp_port, timeout=timeout)
    else:
        return icmp_ping(stats.address, timeout=timeout, packet_size=packet_size, ttl=ttl)


def ping_batch(targets, max_workers: int = 500, timeout: int = 3,
               packet_size: int = 56, ttl: int = 0):
    """
    批量并发 ping 多个目标
    返回 (target, PingResult) 的列表
    """
    results = []
    if not targets:
        return results

    with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as executor:
        future_to_target = {
            executor.submit(ping_target, t, timeout, packet_size, ttl): t for t in targets
        }
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                result = future.result()
            except Exception as e:
                result = PingResult(success=False, error=str(e))
            results.append((target, result))

    return results
