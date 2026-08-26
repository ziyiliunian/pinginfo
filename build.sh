#!/bin/bash
# PingInfo Debian 打包脚本
# 用法: ./build.sh [版本号]
#   默认版本 1.1.5；可传参覆盖，如 ./build.sh 1.1.6
set -e

cd "$(dirname "$0")"

APP_NAME="pinginfo"
VERSION="${1:-1.1.5}"
ARCH="all"
PKG="${APP_NAME}_${VERSION}_${ARCH}.deb"
OUT_DIR="dist"
mkdir -p build
PKGROOT=$(mktemp -d "build/pkgroot.${VERSION}.XXXXXX")
trap 'find "$PKGROOT" -depth -delete 2>/dev/null || true' EXIT

echo "=== PingInfo Debian Build (v${VERSION}) ==="

# 检查依赖工具
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "错误: 未找到 dpkg-deb，请安装 dpkg-dev (sudo apt-get install dpkg-dev)"
    exit 1
fi

# 以 packaging/ 为骨架复制到临时构建根
cp -r packaging/* "$PKGROOT/"

# 复制源码（保持 src/ 包结构，启动器通过 /opt/pinginfo/src 导入）
mkdir -p "$PKGROOT/opt/${APP_NAME}"
cp -r src "$PKGROOT/opt/${APP_NAME}/src"

# 生成图标（始终重新绘制，确保设计生效）
ICON="$PKGROOT/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
mkdir -p "$(dirname "$ICON")"
echo "生成图标(雷达探测 + 目标节点)..."
QT_QPA_PLATFORM=offscreen ICON_OUT="$ICON" python3 - << 'PYEOF'
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QRadialGradient
from PyQt5.QtCore import Qt, QPointF, QRectF
import os, math

app = QApplication([])
S = 256
pix = QPixmap(S, S)
pix.fill(QColor(0, 0, 0, 0))  # 透明背景
p = QPainter(pix)
p.setRenderHint(QPainter.Antialiasing)

cx, cy = S / 2, S / 2

# 背景圆角方块（科技蓝渐变）
bg = QRadialGradient(cx, cy, S * 0.7)
bg.setColorAt(0.0, QColor('#1E88E5'))
bg.setColorAt(1.0, QColor('#0D47A1'))
pen = QPen(QColor('#0D47A1'))
pen.setWidth(0)
p.setPen(pen)
p.setBrush(QBrush(bg))
r = 36
p.drawRoundedRect(QRectF(8, 8, S - 16, S - 16), r, r)

# 外圈三道同心弧 = 向外扩散的 Ping 探测信号
p.setPen(Qt.NoPen)
ring_colors = ['#BBDEFB', '#90CAF9', '#64B5F6']
for i, (rad, col) in enumerate(zip([96, 74, 52], ring_colors)):
    p.setPen(QPen(QColor(col), 5, Qt.SolidLine, Qt.RoundCap))
    # 画约 300° 的弧，留缺口表示信号发射方向
    p.drawArc(QRectF(cx - rad, cy - rad, rad * 2, rad * 2),
              int(120 * 16), int(300 * 16))

# 对角信号射线（从左下到中心目标）= 单次探测往返路径
p.setPen(QPen(QColor('#E3F2FD'), 4, Qt.SolidLine, Qt.RoundCap))
p.drawLine(QPointF(cx - 70, cy + 70), QPointF(cx, cy))
# 射线末端小端点（探测起点）
p.setBrush(QBrush(QColor('#E3F2FD')))
p.setPen(Qt.NoPen)
p.drawEllipse(QPointF(cx - 70, cy + 70), 6, 6)

# 中心实心圆点 = 被监控的目标主机
p.setBrush(QBrush(QColor('#FFFFFF')))
p.setPen(QPen(QColor('#0D47A1'), 3))
p.drawEllipse(QPointF(cx, cy), 16, 16)
# 中心绿点（成功/在线状态）
p.setBrush(QBrush(QColor('#43A047')))
p.setPen(Qt.NoPen)
p.drawEllipse(QPointF(cx, cy), 7, 7)

p.end()
out = os.environ.get("ICON_OUT")
pix.save(out, 'PNG')
print("Icon generated:", out)
PYEOF

# 设置权限
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/postrm"
chmod 755 "$PKGROOT/usr/bin/${APP_NAME}"
chmod 644 "$PKGROOT/usr/share/applications/${APP_NAME}.desktop"
chmod 644 "$ICON"

# 写入版本号并自动计算 Installed-Size（KB，向上取整）
sed -i "s/^Version:.*/Version: ${VERSION}/" "$PKGROOT/DEBIAN/control"
SIZE_KB=$(du -sk "$PKGROOT/opt" "$PKGROOT/usr" 2>/dev/null | awk '{s+=$1} END {print s}')
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
