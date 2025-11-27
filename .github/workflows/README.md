# GitHub Actions 工作流说明

## 自动构建流程

本项目使用GitHub Actions自动为以下平台构建可执行文件：

- **Windows** (x64)
- **macOS Intel** (x86_64)
- **macOS Apple Silicon** (arm64, M1/M2/M3)

## 如何触发构建

### 方法1：推送版本标签（推荐）

```bash
# 创建并推送版本标签
git tag v1.0.0
git push origin v1.0.0
```

这将：
1. 自动构建所有平台版本
2. 创建GitHub Release
3. 将可执行文件上传到Release中

### 方法2：手动触发

1. 进入GitHub仓库
2. 点击 **Actions** 标签
3. 选择 **Build PKU-Get Release**
4. 点击 **Run workflow**
5. 选择分支并点击运行

### 方法3：Pull Request验证

每次创建Pull Request时会自动构建，用于验证代码的跨平台兼容性。

## 下载构建文件

### 从Release下载（推荐）

1. 进入仓库的 **Releases** 页面
2. 选择最新版本
3. 在 **Assets** 部分下载对应平台的文件

### 从Actions Artifacts下载

1. 进入 **Actions** 标签
2. 选择一个成功的构建
3. 在 **Artifacts** 部分下载对应平台的文件

## 构建时间

通常每个平台需要3-5分钟，总计约10-15分钟完成所有平台构建。

## 故障排除

如果构建失败，查看Actions日志：
1. 点击失败的workflow run
2. 查看具体失败的job
3. 展开步骤查看详细日志

常见问题：
- 前端构建失败：检查`gui/package.json`依赖
- Python依赖问题：检查`pyproject.toml`
- PyInstaller错误：检查`build.py`中的配置
