# Kylin V10 ARM64 图形完整版构建与测试记录

测试日期：2026-08-26（Asia/Shanghai）

## 环境

- 宿主：Apple Silicon Mac（arm64）
- 容器平台：Linux ARM64 / aarch64
- 基础镜像：`macrosan/kylin:v10-sp1`
- 目标 glibc：2.28
- Python：3.10.18（固定 SHA-256，容器内源码构建）
- Qt：5.15.2（固定 SHA-256，容器内源码构建）
- PySide2：5.15.2.1（固定 SHA-256，含 Python 3.10 兼容补丁）
- PyInstaller：6.18.0
- RapidOCR：3.9.1
- ONNX Runtime：1.23.2
- OCR：PP-OCRv6 Medium
- Office：Kylin ARM64 LibreOffice 6.0.6.1

## 产物

| 产物 | 文件大小 | SHA-256 |
| --- | ---: | --- |
| `document-ocr-assistant-0.2.0-kylin-v10-arm64-full.run` | 464,081,630 bytes | `ad116fd3eea6d9226339db00b605a7fc6f8ed1c36fe857acc8752e8ff7e2bf44` |

解压目录约 1.0 GiB。冻结主程序经 `file` 确认为原生 ARM aarch64 ELF，版本信息包含 `(full, kylin-v10, arm64)`。

## 自动化测试

- ARM64 构建容器单元测试：28 项通过，2 项跳过。跳过项为无显示服务器的 Qt5 offscreen 插件无法执行真实整屏抓取；macOS/Qt6 环境的对应截图生命周期测试正常执行。
- macOS 源码回归：30 项全部通过。
- PyInstaller 图形客户端冻结成功，Qt Core、Gui、Widgets、XCB 与 GL 运行组件随包。
- 图形界面在构建容器和全新 Kylin 基础容器中均以 offscreen 模式启动，并生成非空界面截图。
- PP-OCRv6 图片 OCR 成功生成 TXT 与 Markdown，识别到固定合成文字 `Kylin ARM64`。
- 0°、90°、180°、270° 四个合成页面均识别成功，报告中的实际旋正角度与预期一致。
- 随包 LibreOffice 输出 `LibreOffice 6.0.6.1 00(Build:1)`，合成 DOCX 转换成功。
- 最终 `.run` 在全新 Kylin ARM64 基础容器中自解压，`--cli --version` 验证成功。

干净容器未安装 Python、OpenCV、Qt 或 LibreOffice。上述 GUI、OCR 和 Office 测试使用的是成品随包运行时，不依赖 builder 镜像。

## 图形运行时说明

Kylin V10 SP1 的 glibc 版本为 2.28，不能直接使用要求更高 glibc 的 PySide6 ARM64 官方 wheel。ARM64 图形版因此固定使用 Qt 5.15.2 与 PySide2 5.15.2.1，并通过小范围源码补丁适配 Python 3.10；Qt 和 PySide2 均在 Kylin V10 ARM64 容器内原生编译。

程序同时包含：

- 图形入口：`启动文档OCR助手.sh`
- 命令行入口：`文档OCR助手命令行.sh`
- 自解压入口：直接运行 `.run` 启动 GUI，使用 `.run --cli ...` 调用命令行

容器的 offscreen 后端只能验证窗口创建与渲染，无法代替 Kylin 真机上的 XCB 窗口交互和真实屏幕框选；真机仍需补充鼠标、文件选择器、截图和桌面快捷方式验证。

## 发布内容审计

- OCR PNG、方向图片和 DOCX 均由项目脚本即时合成，只包含固定测试文字。
- 合成输入、识别结果、构建目录和缓存均被 `.gitignore` 排除，不进入源码或发布包。
- `.run` 只包含冻结客户端、固定模型、Qt 运行组件、LibreOffice、图标、启动脚本和使用说明。
- 发布候选包内不存在 `.env`、密钥、令牌、证书、日志、用户设置、测试 PDF/DOCX 或本机用户路径。
- README 截图由空白应用状态生成，不含用户文档；PNG 不含 ICC profile，且已人工检查画面内容。
