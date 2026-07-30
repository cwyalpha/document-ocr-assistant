# Windows x86_64 验证记录

## 环境与成品

- 系统：Windows 11 x86_64
- Python 构建环境：3.12.4
- 客户端：PySide6 + PyInstaller 6.18.0 onedir
- 推理：PP-OCRv6 Medium 与 SLANet-plus，均为 ONNX Runtime 1.23.2 CPU
- Office 转换：Microsoft Word COM / WPS Office COM；Windows 包不含 LibreOffice
- 成品：`dist/文档OCR助手-windows-x86_64/` 与同名 ZIP

## 已验证

| 场景 | 结果 |
|---|---|
| 冻结客户端启动与界面截图 | 通过，深色主题、缩放与中文显示正常 |
| Windows UI Automation / Computer Use | 通过，识别 54 个控件并完成设置、文件选择、PDF 识别、结果查看、历史页导航 |
| PP-OCRv6 Medium 图片 OCR | 通过，冻结 EXE 检出 11 个文字块 |
| SLANet-plus 表格结构识别 | 通过，冻结 EXE 检出 1 个表格 |
| 合并单元格 Markdown | 通过，输出 HTML 表格并保留 `colspan="3"` |
| 原生文本 PDF 自动提取 | 通过，冻结 EXE 直接提取两段文本并输出 TXT + MD |
| 两页扫描 PDF OCR | 通过，冻结 EXE 检出 22 个文字块和 2 个表格，保留第 1/2 页结构 |
| 强制 OCR 与可搜索 PDF | 通过，生成两页可搜索 PDF，PyMuPDF 回读 345 个文本字符 |
| Microsoft Word DOCX 转换 | 通过，中文正文与 HTML 表格均回读成功 |
| WPS Office DOCX 转换 | 通过，中文正文与 HTML 表格均回读成功 |
| TXT + Markdown 文件输出 | 通过，UTF-8 中文内容正确且表格正文不重复 |
| 离线模型随包分发 | 通过，冻结 EXE 直接读取包内 PP-OCRv6 Medium 与 SLANet-plus |
| Windows 离线 RAR 工具 | 通过，LocalKB `unrar.exe` 已复制到 `bin/archive/` |
| LibreOffice 排除检查 | 通过，Windows 包中匹配文件数为 0 |
| Python 自动化测试 | 19 passed |
| 中文 Windows ZIP 文件名 | 通过，未标记编码的 GBK/CP936 文件名在 Windows/Kylin 一致恢复 |
| 未转换文件原样复制 | 通过，目录与压缩包中的 TXT/JSON/XLSX 等保留原层级；默认关闭且仅新批次模式生效 |
| 连续截图生命周期 | 通过 Qt offscreen 回归测试，第一次确认识别后第二次覆盖层仍可正常打开 |
| 关闭窗口行为 | 设置持久化通过；默认每次询问，记住选择复选框默认不勾选，可在设置页改为询问/托盘/退出 |

## Office 选择规则

- DOC/DOCX 自动模式：优先 Microsoft Word，失败时尝试 WPS Office；
- WPS 自动模式：优先 WPS Office，失败时尝试 Microsoft Word；
- `DOCUMENT_OCR_WINDOWS_OFFICE=word` 或 `wps` 可固定引擎；
- COM 实例以隐藏、只读、禁用提示和禁用宏的方式打开临时副本，转换完成后关闭应用实例。

## 构建自检

`scripts/build_windows.ps1` 会在复制模型及工具后执行两项冻结包测试：

1. 启动 `app/文档OCR助手.exe` 并保存实际窗口截图；
2. 让同一个冻结 EXE 处理带合并单元格的图片，要求 OCR 文字块、表格数和 `colspan` 同时通过。

本机未安装 Inno Setup 6，因此本次生成的是可直接使用的目录包和 ZIP，未生成图形化安装器 EXE；安装器脚本已提供，可在安装 Inno Setup 6 的构建机上直接生成。

## Computer Use 界面验收

使用 `scripts/test_windows_computer_use.py` 从应用外部操作最终冻结 EXE，未调用应用内部流水线：

1. 打开设置页，确认显示 Microsoft Word / WPS Office 自动选择；
2. 返回批量识别，通过 Windows 系统文件对话框添加两页扫描 PDF；
3. 在界面中写入输出目录，启用自动表格和可搜索 PDF；
4. 点击开始识别，等待任务显示“已完成 / 100% / 3 个文件”；
5. 确认识别结果面板自动显示 346 个字符；
6. 确认生成 TXT、Markdown、可搜索 PDF，并能进入截图历史页。

首次 Computer Use 验收发现任务完成后结果面板未自动选中首行，现已修复为首个完成任务自动选中并展示文本。测试报告及五张步骤截图位于 `build/windows/computer-use-evidence/`。
