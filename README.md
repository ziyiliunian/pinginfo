# PingInfo - 批量 Ping 与实时监控工具

类似 PingInfoView 的批量 Ping 监控软件，支持 ICMP/TCP Ping、IPv4/IPv6、实时统计和多种格式导出。

## 功能特性

### 批量目标管理
- 支持同时添加数百甚至数千个 IP 地址或域名
- 通过"文件 > 添加目标"手动输入
- 通过"文件 > 从文件载入地址"批量导入（每行一个地址）
- 支持直接拖放文本文件到主窗口

### 灵活的 Ping 方式
- **ICMP Ping**：通过系统 ping 命令发送 ICMP 数据包测试可达性
- **TCP Ping**：测试特定端口的 TCP 连接（如 192.168.0.100:80）
- **IPv6 支持**：自动支持 IPv6 地址的 Ping

### 实时结果展示
按设定间隔自动 Ping 所有目标，表格清晰呈现：
- 响应时间（最近一次 Ping 耗时）
- 丢包率（成功/失败次数及百分比）
- 平均/最小/最大延迟
- TTL（数据包生存时间）
- 最近成功/失败时间
- MAC 地址（同子网目标）

### 便捷的结果导出
支持 TXT、CSV、HTML、XML 四种格式导出。

## 使用方法

### 安装 deb 包
```bash
sudo dpkg -i pinginfo_1.5.0_all.deb
# 若提示依赖未满足，执行：
sudo apt-get install -f
```
安装后在应用菜单搜索 "PingInfo" 即可启动，或在终端运行 `pinginfo`。

### 从源码运行
```bash
pip install PyQt5
python3 src/main.py
```

### 添加目标
1. 菜单"文件 > 添加目标"或 Ctrl+N
2. 选择 ICMP 或 TCP Ping 方式
3. 每行输入一个 IP/域名，TCP 可带端口号（host:port）
4. 或从文件导入（IP.txt 格式）

### 开始监控
- 按 F5 或点击"开始监控"
- 在"Ping > Ping 选项设置"中调整间隔、并发数、超时

### 快捷键
| 快捷键 | 功能 |
|--------|------|
| Ctrl+N | 添加目标 |
| Ctrl+O | 从文件载入 |
| F5 | 开始监控 |
| F6 | 停止监控 |
| Delete | 删除选中行 |
| Ctrl+Q | 退出 |

## 项目结构
```
pinginfo/
├── src/                  # 源代码
│   ├── main.py           # 主入口
│   ├── main_window.py    # 主窗口 GUI
│   ├── dialogs.py        # 对话框
│   ├── data_models.py    # 数据模型
│   ├── ping_core.py      # Ping 核心模块
│   ├── arp_lookup.py     # MAC 地址查询
│   ├── exporters.py      # 结果导出
├── build/                # 构建中间文件
├── packaging/            # deb 打包配置文件（control / desktop / 图标等）
├── build.sh              # deb 打包脚本
├── requirements.txt      # 依赖
├── IP.txt                # 示例地址文件
└── pinginfo_1.5.0_all.deb  # 打包后的 deb 安装包（架构无关 all）
```

## 打包为 deb

详见 `packaging/README.md`，或直接运行：

```bash
./build.sh 1.5.0
sudo dpkg -i dist/pinginfo_1.5.0_all.deb
```

## 技术栈
- Python 3.8+
- PyQt5 (GUI)
- 系统命令 ping (ICMP)
- socket (TCP Ping)
- dpkg-deb (deb 打包)

## 修改记录

详见 [CHANGELOG.md](CHANGELOG.md)。

## 作者与联系方式

- 作者：ziyiliunian
- 邮箱：316878142@qq.com
- 项目地址：https://github.com/ziyiliunian/pinginfo

欢迎通过邮件或 GitHub Issues 交流反馈问题与建议。
