#!/bin/bash
# PingInfo Debian 打包脚本
# 用法: ./build.sh [版本号]
#   默认版本 1.0；可传参覆盖，如 ./build.sh 1.0.1
set -e

cd "$(dirname "$0")"

APP_NAME="pinginfo"
VERSION="${1:-1.0}"
ARCH="amd64"
PKG="${APP_NAME}_${VERSION}_${ARCH}.deb"
OUT_DIR="dist"
PKGROOT="build/pkgroot"

echo "=== PingInfo Debian Build (v${VERSION}) ==="

# 检查依赖工具
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "错误: 未找到 dpkg-deb，请安装 dpkg-dev (sudo apt-get install dpkg-dev)"
    exit 1
fi

# 清理旧构建
rm -rf "$PKGROOT"
mkdir -p "$PKGROOT"

# 以 packaging/ 为骨架复制到构建根
cp -r packaging/* "$PKGROOT/"

# 复制源码（保持 src/ 包结构，启动器通过 /usr/share/pinginfo/src 导入）
mkdir -p "$PKGROOT/usr/share/${APP_NAME}"
cp -r src "$PKGROOT/usr/share/${APP_NAME}/src"

# 生成图标（若缺失）
ICON="$PKGROOT/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
if [ ! -s "$ICON" ]; then
    echo "生成图标..."
    QT_QPA_PLATFORM=offscreen python3 - << 'PYEOF'
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
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/postrm"
chmod 755 "$PKGROOT/usr/bin/${APP_NAME}"
chmod 644 "$PKGROOT/usr/share/applications/${APP_NAME}.desktop"
chmod 644 "$ICON"

# 写入版本号并自动计算 Installed-Size（KB，向上取整）
sed -i "s/^Version:.*/Version: ${VERSION}/" "$PKGROOT/DEBIAN/control"
SIZE_KB=$(du -sk "$PKGROOT/usr" | cut -f1)
sed -i "s/^Installed-Size:.*/Installed-Size: ${SIZE_KB}/" "$PKGROOT/DEBIAN/control"

# 构建 deb（保持 root 拥有者）
mkdir -p "$OUT_DIR"
echo "构建 ${OUT_DIR}/${PKG} ..."
dpkg-deb --build --root-owner-group "$PKGROOT" "${OUT_DIR}/${PKG}"

if [ -f "${OUT_DIR}/${PKG}" ]; then
    echo "=== SUCCESS: ${OUT_DIR}/${PKG} ($(du -h "${OUT_DIR}/${PKG}" | cut -f1)) ==="
    echo "安装: sudo dpkg -i ${OUT_DIR}/${PKG}"
else
    echo "=== 打包失败 ==="
    exit 1
fi
