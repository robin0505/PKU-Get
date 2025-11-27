# PKU-Get 打包指南

## 快速打包

使用一键构建脚本（推荐）：

```bash
uv run build.py
```

这将自动：
1. 构建 React 前端
2. 安装 PyInstaller
3. 打包成独立可执行文件

构建完成后，可执行文件位于 `dist/PKU-Get.exe`

## 手动打包步骤

如果需要手动控制每个步骤：

### 1. 安装开发依赖

```bash
uv sync --dev
```

### 2. 构建前端

```bash
cd gui
npm install
npm run build
cd ..
```

### 3. 打包应用

使用 spec 文件（推荐，配置更完整）：

```bash
uv run pyinstaller PKU-Get.spec
```

或使用命令行参数：

```bash
uv run pyinstaller --name=PKU-Get --windowed --onefile --add-data="gui/dist;gui/dist" --clean gui.py
```

## 构建选项说明

- `--windowed`: 不显示控制台窗口（GUI应用）
- `--onefile`: 打包成单个可执行文件
- `--add-data`: 包含前端构建文件
- `--clean`: 清理之前的构建缓存

## 平台特定说明

### Windows
- 输出文件: `dist/PKU-Get.exe`
- 需要安装 Node.js (用于构建前端)

### macOS
- 输出文件: `dist/PKU-Get`  
- 可能需要签名才能分发: `codesign -s "Developer ID" dist/PKU-Get`

### Linux
- 输出文件: `dist/PKU-Get`
- 确保安装了 `python3-tk` 包

## 故障排除

### 问题：找不到 gui/dist 文件夹
**解决**：先运行 `cd gui && npm run build`

### 问题：PyInstaller 导入错误
**解决**：运行 `uv pip install pyinstaller`

### 问题：可执行文件过大
**解决**：在 spec 文件中启用 UPX 压缩（已默认启用）

## 分发建议

打包完成后，分发前请测试：
1. 在干净的环境中运行可执行文件
2. 检查所有功能是否正常（登录、同步、下载等）
3. 确认浏览器驱动自动下载功能正常

## 持续集成

如果需要在CI/CD中构建，可以添加到 GitHub Actions：

```yaml
- name: Build application
  run: uv run build.py
  
- name: Upload artifact
  uses: actions/upload-artifact@v3
  with:
    name: PKU-Get-${{ runner.os }}
    path: dist/PKU-Get*
```
