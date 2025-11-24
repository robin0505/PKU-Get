#!/bin/bash

# ----------------------------------------------------------------------
# 脚本名称: svg2icns_fix.sh (修复版本)
# 功能: 将一个 SVG 文件转换为 macOS 兼容的 ICNS 文件。
# ----------------------------------------------------------------------

# 确保脚本遇到错误时立即退出
set -e

# --- 检查依赖项 ---
if ! command -v rsvg-convert &> /dev/null; then
    echo "错误：未找到 'rsvg-convert' 命令。" >&2
    echo "请通过 Homebrew 安装：brew install librsvg" >&2
    exit 1
fi

if ! command -v iconutil &> /dev/null; then
    echo "错误：未找到 'iconutil' 命令 (macOS 内置工具)。" >&2
    exit 1
fi

# --- 参数处理 ---
if [ "$#" -lt 1 ]; then
    echo "使用方法: $0 <input_file.svg> [output_file.icns]"
    exit 1
fi

SVG_FILE="$1"

# 检查输入文件是否存在且是 SVG 文件
if [ ! -f "$SVG_FILE" ]; then
    echo "错误: 文件不存在: $SVG_FILE" >&2
    exit 1
fi

# 从 SVG 文件名推断基础名称
BASE_NAME=$(basename "$SVG_FILE" .svg)

# 确定输出 ICNS 文件名
if [ -n "$2" ]; then
    ICNS_FILE="$2"
else
    ICNS_FILE="${BASE_NAME}.icns"
fi

# 临时 Iconset 文件夹名称
ICONSET_DIR="${BASE_NAME}.iconset"

# 定义所有需要的尺寸及其对应的文件名（使用简单列表）
# 格式: 尺寸(px)
REQUIRED_SIZES=(16 32 64 128 256 512 1024)

# ----------------------------------------------------------------------
# 步骤 1: 创建 .iconset 目录
# ----------------------------------------------------------------------
echo "--- 步骤 1: 创建 iconset 目录: ${ICONSET_DIR} ---"
# 清理旧的 iconset (如果有的话)
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

# ----------------------------------------------------------------------
# 步骤 2: 转换 SVG 到所有 PNG 尺寸
# ----------------------------------------------------------------------
echo "--- 步骤 2: 转换 SVG 到 PNG ---"

for SIZE in "${REQUIRED_SIZES[@]}"; do
    PNG_FILES=()

    # 根据尺寸确定需要生成哪些文件名
    if [ "$SIZE" -eq 16 ]; then
        PNG_FILES=("icon_16x16.png")
    elif [ "$SIZE" -eq 32 ]; then
        PNG_FILES=("icon_16x16@2x.png" "icon_32x32.png")
    elif [ "$SIZE" -eq 64 ]; then
        PNG_FILES=("icon_32x32@2x.png")
    elif [ "$SIZE" -eq 128 ]; then
        PNG_FILES=("icon_128x128.png")
    elif [ "$SIZE" -eq 256 ]; then
        PNG_FILES=("icon_128x128@2x.png" "icon_256x256.png")
    elif [ "$SIZE" -eq 512 ]; then
        PNG_FILES=("icon_256x256@2x.png" "icon_512x512.png")
    elif [ "$SIZE" -eq 1024 ]; then
        PNG_FILES=("icon_512x512@2x.png")
    else
        continue
    fi
    
    # 使用 rsvg-convert 导出 PNG
    OUTPUT_PATH="${ICONSET_DIR}/${PNG_FILES[0]}"
    echo "导出 ${SIZE}x${SIZE} 到 ${PNG_FILES[*]} ..."
    
    rsvg-convert -w "$SIZE" -h "$SIZE" "$SVG_FILE" -o "$OUTPUT_PATH"

    # 如果存在多个文件需要相同尺寸 (例如 32x32), 则复制第一个文件
    # 注意：这里的数组操作 [] 在所有版本的 Bash 中都受支持
    for i in "${!PNG_FILES[@]}"; do
        if [ "$i" -ne 0 ]; then
            cp "$OUTPUT_PATH" "${ICONSET_DIR}/${PNG_FILES[$i]}"
        fi
    done
done

# ----------------------------------------------------------------------
# 步骤 3: 使用 iconutil 打包成 ICNS
# ----------------------------------------------------------------------
echo "--- 步骤 3: 使用 iconutil 打包成 ICNS: ${ICNS_FILE} ---"

# 清理旧的 ICNS 文件
rm -f "$ICNS_FILE"

# 运行 iconutil
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"

# 检查是否成功
if [ $? -eq 0 ]; then
    echo "✅ 成功: ${ICNS_FILE} 已生成。"
else
    echo "❌ 失败: iconutil 转换失败。" >&2
    exit 1
fi

# ----------------------------------------------------------------------
# 步骤 4: 清理
# ----------------------------------------------------------------------
echo "--- 步骤 4: 清理临时文件 ---"
rm -rf "$ICONSET_DIR"
echo "清理完成。"