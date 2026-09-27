# 第三方来源与许可说明

核对日期：2026-09-27。项目自身的代码和文档采用 [MIT License](LICENSE)，SPDX 标识为 `MIT`。版权行使用项目贡献者名称，不包含本机账户、真实姓名或邮箱。

## 来源范围

当前实现由本项目独立编写。以下仓库用于理解存档结构、比较解析策略和规划 ID 映射；当前源码发行范围未包含这些仓库的代码、模板、图片、游戏数据或名称字典，也未将它们作为运行依赖。

此清单是来源致谢及核对记录，不授予第三方内容的使用权。将来引入第三方代码或资源时，应在同一变更中记录具体文件、提交和修改范围，并纳入相应的许可及版权声明；不能仅凭此处的引用替代许可要求。

## 调研来源

下列链接固定到查阅时的提交，许可描述仅适用于所指向的材料。

| 项目与作者 / 维护者 | 核对版本 | 许可证据及当前采用情况 |
| --- | --- | --- |
| [X4Companion — dirlligafu](https://github.com/dirlligafu/X4Companion) | [`df6901c`](https://github.com/dirlligafu/X4Companion/tree/df6901cbbc594bf91227b8bf2b0f6437d69807ca) | 该提交未发现 LICENSE / COPYING 文件；[README 的 License 段](https://github.com/dirlligafu/X4Companion/blob/df6901cbbc594bf91227b8bf2b0f6437d69807ca/README.md#license) 仅有免责声明与商标说明，未见明确的开源授权条款。仅调研流式解析与字段关系，未复制代码或资源。 |
| [x4-savegame-parser — Mistralys](https://github.com/Mistralys/x4-savegame-parser) | [`d4379b1`](https://github.com/Mistralys/x4-savegame-parser/tree/d4379b1b65d117fc25b06a7b4d50b3f7abe0d023) | [MIT 许可证](https://github.com/Mistralys/x4-savegame-parser/blob/d4379b1b65d117fc25b06a7b4d50b3f7abe0d023/LICENSE)。仅参考流式抽取和分类思路，未引入代码。 |
| [X4-Info-Miner — TuxInvader / Mark Boddington](https://github.com/TuxInvader/X4-Info-Miner) | [`bcc9861`](https://github.com/TuxInvader/X4-Info-Miner/tree/bcc98619a85f8e0cd50e53ea065149f09c506cfa) | 仓库未见独立 LICENSE；[x4-save-miner.py 文件头](https://github.com/TuxInvader/X4-Info-Miner/blob/bcc98619a85f8e0cd50e53ea065149f09c506cfa/x4-save-miner.py#L1-L25) 含三条款 BSD 风格声明。此处不将单文件声明推定为仓库内全部材料的许可。仅调研查询及语言映射方法，未复制脚本或 JSON 字典。 |
| [x4-core — Mistralys](https://github.com/Mistralys/x4-core) | [`e70e71a`](https://github.com/Mistralys/x4-core/tree/e70e71a622fe572755166c8505e0dd896c304085) | [MIT 许可证](https://github.com/Mistralys/x4-core/blob/e70e71a622fe572755166c8505e0dd896c304085/LICENSE)。仅调研静态数据访问思路，未引入代码或数据库。 |
| [X4-Foundations — BeamerMiasma](https://github.com/BeamerMiasma/X4-Foundations) | [`6531738`](https://github.com/BeamerMiasma/X4-Foundations/tree/6531738c5fd74159a7e1fdafcf35457eb98fa136) | [GNU GPL 第 3 版许可文本](https://github.com/BeamerMiasma/X4-Foundations/blob/6531738c5fd74159a7e1fdafcf35457eb98fa136/LICENSE)。仅调研分析与可视化用途，未引入 R 脚本或发布包。 |

具体技术判断及源文件链接见 [RESEARCH.md](RESEARCH.md)。致谢不表示上述作者参与本项目或为本项目背书。

## 运行环境与可选开发工具

- 网页版使用 Python 标准库 HTTP 服务、SQLite、Expat 和 gzip；保留的桌面版使用 Tkinter。浏览器界面为本项目编写的 HTML、CSS 和 JavaScript，不含第三方前端框架、字体或 CDN 资源。源码仓库不随附 Python 解释器或上述组件的二进制文件。它们各自的许可不会被本项目的 MIT 许可证替代；参见 [Python 许可说明](https://docs.python.org/3/license.html)。
- `tests/gui_smoke.py --real` 的可选截图分支会尝试使用本机已安装的 Pillow；没有 Pillow 时跳过截图，应用和核心测试不依赖它。仓库不随附 Pillow；其许可见 [Pillow LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE)。
- `tests/web_smoke.cjs` 是可选开发检查，需要自行安装的 Playwright 和 Microsoft Edge。仓库未捆绑这些工具，应用不依赖它们；Playwright 的许可见 [Playwright LICENSE](https://github.com/microsoft/playwright/blob/main/LICENSE)。浏览器遵循其各自发行条款。
- 若后续制作包含解释器、GUI 库或其他依赖的可执行发行包，应依据实际打包版本补齐依赖清单和许可全文。本文件描述当前源码发行范围。

## 游戏名称与内容

X4: Foundations 是 Egosoft 的游戏。本项目是独立的非官方工具，与 Egosoft 无隶属、授权或背书关系。

本项目的 MIT 许可证不涵盖游戏程序、商标、图像、音频、语言资源、CAT/DAT 内容或用户存档。当前源码发行范围不包含这些材料；如后续提供中文名称解析，应优先读取用户本机已安装的游戏资源，并另行核对需要分发的内容。
