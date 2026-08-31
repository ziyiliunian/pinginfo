# -*- coding: utf-8 -*-
"""
结果导出模块
支持 TXT、CSV、HTML、XML 格式导出
"""

import csv
import html
import os
import time
from xml.etree import ElementTree as ET
from xml.dom import minidom


# 导出列定义
EXPORT_COLUMNS = [
    ("address", "地址"),
    ("ping_mode", "Ping方式"),
    ("tcp_port", "TCP端口"),
    ("status", "状态"),
    ("last_rtt", "响应时间(ms)"),
    ("loss_rate", "丢包率(%)"),
    ("succeed_count", "成功次数"),
    ("failed_count", "失败次数"),
    ("total_count", "总次数"),
    ("avg_rtt", "平均延迟(ms)"),
    ("min_rtt", "最小延迟(ms)"),
    ("max_rtt", "最大延迟(ms)"),
    ("ttl", "TTL"),
    ("last_success", "最近成功时间"),
    ("last_fail", "最近失败时间"),
    ("mac_address", "MAC地址"),
    ("resolved_ip", "解析地址"),
    ("last_error", "错误信息"),
]


def export_txt(stats_list, filepath: str) -> bool:
    """导出为 TXT 格式"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            header = " | ".join(label for _, label in EXPORT_COLUMNS)
            f.write(header + "\n")
            f.write("=" * len(header) + "\n")
            for stats in stats_list:
                data = stats.to_dict()
                row = " | ".join(str(data.get(key, "")) for key, _ in EXPORT_COLUMNS)
                f.write(row + "\n")
        return True
    except Exception as e:
        print(f"导出 TXT 失败: {e}")
        return False


def _safe_csv_value(value):
    """防止表格软件把用户可控文本解释为公式。"""
    text = "" if value is None else str(value)
    if text.startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + text
    return text


def export_csv(stats_list, filepath: str) -> bool:
    """导出为 CSV 格式"""
    try:
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([label for _, label in EXPORT_COLUMNS])
            for stats in stats_list:
                data = stats.to_dict()
                writer.writerow([_safe_csv_value(data.get(key, ""))
                                 for key, _ in EXPORT_COLUMNS])
        return True
    except Exception as e:
        print(f"导出 CSV 失败: {e}")
        return False


def export_html(stats_list, filepath: str) -> bool:
    """导出为 HTML 格式"""
    try:
        parts = []
        parts.append("<!DOCTYPE html>")
        parts.append('<html lang="zh-CN">')
        parts.append("<head>")
        parts.append('<meta charset="UTF-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        parts.append("<title>PingInfo 测试结果</title>")
        parts.append("<style>")
        parts.append("body{font-family:'Microsoft YaHei',Arial,sans-serif;margin:20px;background:#f5f5f5;}")
        parts.append("h1{color:#333;text-align:center;}")
        parts.append("table{width:100%;border-collapse:collapse;background:white;box-shadow:0 1px 3px rgba(0,0,0,0.1);}")
        parts.append("th{background:#4CAF50;color:white;padding:10px 8px;text-align:left;font-size:13px;}")
        parts.append("td{padding:8px;border-bottom:1px solid #ddd;font-size:12px;}")
        parts.append("tr:hover{background:#f0f0f0;}")
        parts.append(".success{color:#4CAF50;font-weight:bold;}")
        parts.append(".fail{color:#f44336;font-weight:bold;}")
        parts.append(".waiting{color:#FF9800;}")
        parts.append(".timestamp{text-align:center;color:#666;margin:10px 0;}")
        parts.append("</style>")
        parts.append("</head>")
        parts.append("<body>")
        parts.append("<h1>PingInfo 测试结果报告</h1>")
        parts.append(f'<p class="timestamp">生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>')
        parts.append('<table>')
        parts.append("<tr>")
        for _, label in EXPORT_COLUMNS:
            parts.append(f"<th>{label}</th>")
        parts.append("</tr>")

        for stats in stats_list:
            data = stats.to_dict()
            status = data.get("status", "")
            css_class = ""
            if status == "成功":
                css_class = "success"
            elif status == "失败":
                css_class = "fail"
            elif status == "等待中":
                css_class = "waiting"
            parts.append(f'<tr class="{css_class}">')
            for key, _ in EXPORT_COLUMNS:
                value = html.escape(str(data.get(key, "")))
                parts.append(f"<td>{value}</td>")
            parts.append("</tr>")

        parts.append("</table>")
        parts.append("</body>")
        parts.append("</html>")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(parts))
        return True
    except Exception as e:
        print(f"导出 HTML 失败: {e}")
        return False


def export_xml(stats_list, filepath: str) -> bool:
    """导出为 XML 格式"""
    try:
        root = ET.Element("PingInfoReport")
        root.set("generated", time.strftime("%Y-%m-%d %H:%M:%S"))
        root.set("total_targets", str(len(stats_list)))

        for stats in stats_list:
            data = stats.to_dict()
            target_elem = ET.SubElement(root, "Target")
            for key, _ in EXPORT_COLUMNS:
                elem = ET.SubElement(target_elem, key)
                elem.text = str(data.get(key, ""))

        rough_string = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(rough_string)
        pretty_xml = dom.toprettyxml(indent="  ", encoding='utf-8')

        with open(filepath, 'wb') as f:
            f.write(pretty_xml)
        return True
    except Exception as e:
        print(f"导出 XML 失败: {e}")
        return False


def export_results(stats_list, filepath: str, format_type: str) -> bool:
    """
    根据格式类型导出结果
    format_type: 'txt', 'csv', 'html', 'xml'
    """
    format_type = format_type.lower()
    exporters = {
        'txt': export_txt,
        'csv': export_csv,
        'html': export_html,
        'xml': export_xml,
    }
    exporter = exporters.get(format_type)
    if exporter:
        return exporter(stats_list, filepath)
    print(f"不支持的导出格式: {format_type}")
    return False
