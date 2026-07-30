# Kylin V10 SP1 Docker 验证记录

## 环境

- 镜像：`macrosan/kylin:v10-sp1`
- 系统：Kylin Linux Advanced Server V10 SP1 (Tercel)
- 架构：x86_64
- glibc：2.28
- Python：3.12.13（独立运行环境；镜像系统 Python 3.7.9 不进入应用包）
- 推理：ONNX Runtime 1.23.2，CPU

该镜像为服务器版，不包含 UKUI/X11 桌面。本记录覆盖命令行、离线组件和 Qt offscreen 构造测试，不替代真实 Kylin 桌面视觉与全局快捷键验收。

## 已验证

| 场景 | 结果 |
|---|---|
| PP-OCRv6 Medium 图片 OCR | 通过 |
| SLANet-plus ONNX 表格结构识别 | 通过，表格输出 GFM Markdown |
| 扫描 PDF OCR | 通过 |
| 原生文本 PDF 自动提取 | 通过 |
| 可搜索 PDF 隐形文本层 | 通过，并用 PyMuPDF 回读确认 |
| DOCX 转 TXT/MD | 通过 |
| 二进制 DOC 转 TXT/MD | 通过 |
| WPS 扩展名文档转 TXT/MD | 通过 |
| ZIP 内图片 + DOCX | 通过 |
| RAR 内图片 + DOCX | 通过，使用 LocalKB 离线 unrar 7.23 |
| 密码保护 7Z | 通过，密码仅在内存中传递 |
| TAR.GZ 内图片 + DOCX | 通过 |
| LibreOffice 离线解包与自检 | 通过，版本 7.6.7.2 |
| PyInstaller onedir 构建 | 通过 |
| PyInstaller 冻结客户端 Qt offscreen 启动 | 通过 |
| 自动化测试 | 19 passed |
| 中文 Windows ZIP 文件名 | 通过，GBK/CP936 与未标记 UTF-8 文件名自动恢复 |
| 未转换文件原样复制 | 通过，目录与压缩包中的 TXT/JSON/XLSX 等保留原层级；默认关闭且仅新批次模式生效 |
| 连续截图生命周期 | 通过 Qt offscreen 回归测试，第二次截图覆盖层可再次建立并恢复主窗口 |
| 关闭窗口行为 | 设置持久化通过；默认每次询问，记住选择复选框默认不勾选，可在设置页改为询问/托盘/退出 |

## 离线组件来源

LibreOffice、PP-OCRv6 Medium 模型、7-Zip 和 unrar 均从预先准备的 `offline_components/` 目录读取。LibreOffice DEB 由项目脚本直接解析到普通用户目录，没有调用 apt、dpkg、dnf 或 rpm。

SLANet-plus 在构建阶段固定为 RapidTable v2.0.0 模型，SHA-256 为：

```text
d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b
```

## 仍需真实桌面验收

- UKUI 下浅色/深色主题观感和系统缩放；
- X11 全局快捷键 `Ctrl+Alt+O` 的冲突与锁屏行为；
- 多显示器截图坐标；
- UKUI 系统托盘与桌面快捷方式；
- KYSEC 开启后的执行权限策略。
