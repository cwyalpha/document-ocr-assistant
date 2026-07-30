# macOS arm64 构建与测试记录

测试日期：2026-07-30（Asia/Shanghai）

## 构建环境

- 主机：Apple Silicon Mac（arm64）
- macOS：26.5.2（Build 25F84）
- Python：3.12.13
- PyInstaller：6.18.0
- PySide6：6.8.3
- 应用版本：0.1.1
- Bundle ID：`com.documentocr.assistant`
- 最低系统版本：macOS 12.0

## 产物

| 产物 | 大小 | SHA-256 |
| --- | ---: | --- |
| `文档OCR助手-macos-arm64.zip` | 240 MiB（`du`） | `d52cf4b20a4d9f0d534766ae4d08970c40e0b14159dde4ca092747514ca39a89` |
| `文档OCR助手-macos-arm64.dmg` | 252 MiB（`du`） | `8184e8406c945beeec30635bf5693748b767a37d81fd2e72ee6dfee8481b0fa9` |

目录 App 未压缩大小约 482 MiB。

## 测试结果

### 源码与平台集成

- `pytest -q`：24 项全部通过。
- `compileall`：`src`、`scripts`、`tests` 全部通过。
- Carbon 全局快捷键：注册和注销测试通过。
- macOS Application Support 路径及 App Bundle `Contents/Resources` 资源定位测试通过。
- macOS 系统 LibreOffice 路径探测测试通过。
- 截图连续两次生命周期测试通过。
- macOS 录屏权限拒绝测试通过：主窗口保持可见，不创建黑屏遮罩。
- macOS 返回纯黑截屏的检测测试通过。

### App Bundle

- 主程序格式：Mach-O 64-bit arm64。
- App 内所有 Mach-O 文件均包含 arm64 slice；未发现 x86_64-only 文件。
- `Info.plist`：`plutil -lint` 通过。
- ad-hoc 深度签名：`codesign --verify --deep --strict` 通过。
- PP-OCRv6 Medium 的检测、识别、方向分类模型及 SLANet-plus 表格模型均按固定 SHA-256 复核通过。
- macOS 原生 Cocoa 后端和 Qt offscreen 后端均成功启动冻结 App、渲染主窗口并自动退出。

UI 证据：

- `build/macos/tests/macos-ui-cocoa.png`
- `build/macos/tests/macos-ui-smoke.png`

### macOS 截图权限回归

在“系统设置 → 隐私与安全性 → 录屏与系统录音”中保持“文档OCR助手”为关闭状态，使用最终冻结 App 进行实机测试：

- v0.1.0 可复现全屏黑色遮罩，框选内容为黑图，无法返回文字。
- v0.1.1 在隐藏主窗口前通过 Core Graphics 检查录屏权限。
- 权限关闭时不再打开截图遮罩，主窗口保持可见。
- 应用明确说明黑屏原因，并提供“打开系统设置”和“稍后”两个操作。
- 即使权限状态与实际取图结果不一致，纯黑截屏保护也会阻止黑图进入 PP-OCRv6。
- 将 QImage 截图编码为 PNG 后走与截图线程相同的 PP-OCRv6 输入路径，识别出 18 个文字块及关键文字 `macOS`、`OCR`。

### 冻结 OCR / 表格流水线

测试输入为 1500 × 980 的中英混排表格图片，包含一个跨 4 列的合并单元格。分别从以下三个位置运行：

1. 构建后的目录 App；
2. ZIP 解包后的 App；
3. 只读挂载 DMG 内的 App。

三次结果一致：

- OCR 文字块：18
- 表格：1
- 输出文件：TXT + Markdown，共 2 个
- 合并单元格：Markdown 中保留 `<td colspan="4">`
- 警告：业务流水线报告中无警告

结果文件：

- `build/macos/tests/pipeline-result.json`
- `build/macos/tests/zip-pipeline-result.json`
- `build/macos/tests/dmg-pipeline-result.json`

### 无文本层扫描 PDF / PP-OCRv6

另用最终冻结 App 测试了 1 页扫描 PDF，而不是只测试图片或源码环境；并从只读挂载的最终 DMG 中重复运行。该 PDF 将整页内容作为单张图片嵌入，未写入任何隐藏 OCR 文本：

- PDF 页数：1
- PDF 内嵌图片：1
- PyMuPDF 原生文本提取字符数：0，无法通过 PDF 文本层复制内容
- 冻结 App 运行日志确认加载随包的 `PP-OCRv6_det_medium.onnx` 与 `PP-OCRv6_rec_medium.onnx`
- 识别文字块：18
- 表格：1
- 输出文件：TXT + Markdown，共 2 个
- 关键文字成功识别：`文档 OCR 助手 macOS ONNX 验证`
- 业务流水线警告：0

输入与结果：

- `build/macos/tests/scanned-no-text-layer.pdf`
- `build/macos/tests/scanned-pdf-result.json`
- `build/macos/tests/dmg-scanned-pdf-result.json`
- `build/macos/tests/pipeline-output/批次-20260730-183051/`

该项验证已加入 `scripts/build_macos.sh`，后续构建会在生成 ZIP/DMG 前自动创建无文本层扫描 PDF，并强制由冻结 App 完成识别；识别为空、关键文字缺失或未生成 TXT/Markdown 都会使构建失败。

### 安装介质

- SHA-256 清单复核通过。
- `hdiutil verify`：DMG CRC 校验通过。
- DMG 中存在 `文档OCR助手.app`、`Applications` 软链接和使用说明。
- ZIP 解包后签名保持有效，arm64 主程序可直接运行。
- DMG 只读挂载后签名保持有效，冻结 OCR/表格流水线可直接运行。

### RAR

使用 rarfile 官方 `rar5-subdirs.rar` 测试样例验证 macOS 自带 `/usr/bin/tar`（libarchive）后端，成功解出 4 个文件，并保留空格及 Unicode 目录名。多卷、加密或特殊压缩 RAR 仍建议安装 `unrar` 或 `unar`。

## 已知分发限制

- 本机没有 Apple Developer ID 证书，当前 App 使用 ad-hoc 签名；签名结构有效，但 Gatekeeper 的 `spctl` 评估会拒绝，这是未公证 App 的预期结果。
- 对外公开分发前，需用 Developer ID Application 证书重新签名并提交 Apple 公证；当前 DMG 不能被描述为“已公证”。
- 当前产物仅适用于 Apple Silicon（arm64），不适用于 Intel Mac。
- DOC/DOCX/WPS 转换依赖用户另行安装 macOS 版 LibreOffice。图片、PDF OCR 与表格识别不受影响。
- 首次使用截图识别时，需要用户在 macOS“隐私与安全性”中授予录屏权限；应用会主动请求权限并在拒绝时提供系统设置入口。开启后需完全退出并重新打开应用。
- ad-hoc 签名的代码标识会随重新构建变化，升级版本后 macOS 可能要求用户重新授予录屏权限；稳定保留授权需要 Developer ID 签名。
- RapidOCR 的未使用下载辅助模块在终端模式下会打印一条 `RequestsDependencyWarning`；正式 GUI 无控制台，不显示此提示，且三组冻结流水线均确认未影响离线 OCR、表格和输出。
