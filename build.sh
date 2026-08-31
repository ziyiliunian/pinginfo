#!/bin/bash
# PingInfo Debian 打包脚本
# 用法: ./build.sh [版本号]
# 版本以 src/__init__.py 的 __version__ 为唯一数据源；传参仅用于一致性校验。
set -e

cd "$(dirname "$0")"

APP_NAME="pinginfo"
VERSION=$(PYTHONDONTWRITEBYTECODE=1 python3 -c "import src; print(src.__version__)")
if [ -n "${1:-}" ] && [ "$1" != "$VERSION" ]; then
    echo "错误: 传入版本 $1 与源码版本 $VERSION 不一致"
    exit 1
fi
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
find "$PKGROOT/opt/${APP_NAME}/src" -type f -name '*.pyc' -delete
find "$PKGROOT/opt/${APP_NAME}/src" -type d -name '__pycache__' -empty -delete

# 图标已作为静态资源纳入 packaging，构建时无需 PyQt5
ICON="$PKGROOT/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
if [ ! -s "$ICON" ]; then
    echo "错误: 缺少图标资源 $ICON"
    exit 1
fi

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
