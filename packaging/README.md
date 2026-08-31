# PingInfo Debian 打包说明

本目录存放打包 `.deb` 安装包所需的配置文件与骨架。

## 目录结构

```
packaging/
├── DEBIAN/
│   ├── control        # 包元信息（名称、版本、依赖、架构等）
│   ├── postinst       # 安装后脚本（刷新桌面/图标缓存）
│   └── postrm         # 卸载后脚本（清理桌面缓存）
├── usr/
│   ├── bin/
│   │   └── pinginfo   # 启动器脚本（放到 /usr/bin）
│   └── share/
│       ├── applications/
│       │   └── pinginfo.desktop       # 桌面快捷方式
│       └── icons/hicolor/256x256/apps/
│           └── pinginfo.png           # 应用图标
└── README.md          # 本文件
```

> 注意：Python 源码由 `build.sh` 复制到独立临时包根，不会写入或污染
> `packaging/` 骨架。程序安装后位于 `/opt/pinginfo`。

## 依赖

- `python3` (>= 3.8)
- `python3-pyqt5`
- （可选）`python3-pip`，用于安装非系统源的额外 Python 依赖

## 构建 deb 包

推荐直接运行根目录脚本（需 `python3` 与 `dpkg-deb`）：

```bash
./build.sh 1.3.0
```

脚本会从 `src.__version__` 读取版本、校验传入版本一致性，在 `build/`
创建临时包根并输出到 `dist/`。不要直接向 `packaging/` 写入源码。

## 安装与卸载

```bash
sudo dpkg -i pinginfo_1.3.0_all.deb
sudo apt-get install -f   # 若依赖未满足，自动修复

# 卸载
sudo dpkg -r pinginfo
```
