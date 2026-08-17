#!/bin/bash
# PingInfo Debian 打包脚本
# 用法: ./build.sh
set -e

cd "$(dirname "$0")"

APP_NAME="pinginfo"
VERSION="1.0.0"
ARCH="amd64"
PKG="${APP_NAME}_${VERSION}_${ARCH}.deb"

echo "=== PingInfo Debian Build ==="

# 检查依赖工具
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "错误: 未找到 dpkg-deb，请安装 dpkg-dev (sudo apt-get install dpkg-dev)"
    exit 1
fi

# 清理旧的打包目录副本
rm -rf build/pkgroot
mkdir -p build/pkgroot

# 以 packaging/ 为骨架复制到构建根
cp -r packaging/* build/pkgroot/

# 复制源码到 /usr/share/pinginfo
mkdir -p "build/pkgroot/usr/share/${APP_NAME}"
cp -r src/*.py "build/pkgroot/usr/share/${APP_NAME}/"

# 生成图标（若缺失）
ICON="build/pkgroot/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
if [ ! -s "$ICON" ]; then
    echo "生成图标..."
    python3 - << 'PYEOF'
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QRect
import os
app = QApplication([])
pix = QPixmap(256, 256)
pix.fill(QColor('#2196F3'))
p = QPainter(pix)
p.setPen(QColor('white'))
p.setFont(QFont('Arial', 72, QFont.Bold))
p.drawText(QRect(0, 0, 256, 256), Qt.AlignCenter, 'P')
p.end()
out = os.environ.get("ICON_OUT")
pix.save(out, 'PNG')
print("Icon generated:", out)
PYEOF
fi

# 设置权限
chmod 755 "build/pkgroot/DEBIAN/postinst" "build/pkgroot/DEBIAN/postrm"
chmod 755 "build/pkgroot/usr/bin/${APP_NAME}"
chmod 644 "build/pkgroot/usr/share/applications/${APP_NAME}.desktop"
chmod 644 "$ICON"

# 计算 Installed-Size（KB，向上取整）
SIZE_KB=$(du -sk "build/pkgroot/usr" | cut -f1)
sed -i "s/^Installed-Size:.*/Installed-Size: ${SIZE_KB}/" "build/pkgroot/DEBIAN/control"

# 构建 deb（保持 root 拥有者）
echo "构建 ${PKG} ..."
dpkg-deb --build --root-owner-group build/pkgroot "$PKG"

if [ -f "$PKG" ]; then
    echo "=== SUCCESS: $PKG ($(du -h "$PKG" | cut -f1)) ==="
    echo "安装: sudo dpkg -i $PKG"
else
    echo "=== 打包失败 ==="
    exit 1
fi
