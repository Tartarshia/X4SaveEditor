# 同类项目调研

查阅日期：2026-09-27。检查公开 README、仓库树与相关源文件；未安装或执行这些项目。下列判断用于设计参考，本项目未复制第三方代码。

作者 / 维护者、固定提交号及许可证据统一记录在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本文解释技术取舍，不将参考项目列为本工具的依赖。

| 项目 | 对本项目的帮助 | 采用边界 |
| --- | --- | --- |
| [X4Companion](https://github.com/dirlligafu/X4Companion) | 最接近完整修改器；Rust `quick_xml` 流式读取，后台汇总玩家、舰船、空间站等数据。批量变更统一写回。 | 可参考具体字段和上下文关系。README 写明测试的是 v8，尚未测试 v9；不能直接把支持范围等同于本机版本。仓库根目录未见明确许可文件，暂不移植源码。 |
| [x4-savegame-parser](https://github.com/Mistralys/x4-savegame-parser) | PHP XMLReader 流式抽取片段，再用 DOM 处理小片段，支持大型存档。组件、舰船、空间站分类值得参考。 | 它侧重选取信息及备份；我们需要所有节点的浏览与编辑，所以建立全量节点索引。MIT 许可，若将来移植代码需保留声明。 |
| [X4-Info-Miner](https://github.com/TuxInvader/X4-Info-Miner) | 从 CAT/DAT 与语言文件生成 macro → 名称映射，并处理星区坐标。可以帮助后续中文 ID 字典。 | 存档脚本使用 `read()` 后 `etree.fromstring()`，会保留全文和 XML 树；不采用这个内存模型。该脚本文件头有三条款 BSD 风格声明，具体范围见第三方来源说明。 |
| [x4-core](https://github.com/Mistralys/x4-core) | 游戏静态数据与对象访问层，适合查分类和资源关联。 | 静态字典和动态存档索引分离；需要对齐游戏版本和 DLC。 |
| [BeamerMiasma/X4-Foundations](https://github.com/BeamerMiasma/X4-Foundations) | R 脚本分析与可视化，可参考后续统计需求。 | 不是当前解析编辑核心；GPL-3.0，未移植代码。 |

核对过的源文件：

- [X4Companion parser.rs](https://github.com/dirlligafu/X4Companion/blob/df6901cbbc594bf91227b8bf2b0f6437d69807ca/src-tauri/src/parser.rs)
- [X4Companion writer.rs](https://github.com/dirlligafu/X4Companion/blob/df6901cbbc594bf91227b8bf2b0f6437d69807ca/src-tauri/src/writer.rs)
- [SaveParser.php](https://github.com/Mistralys/x4-savegame-parser/blob/d4379b1b65d117fc25b06a7b4d50b3f7abe0d023/src/X4/SaveViewer/SaveParser.php)
- [x4-save-miner.py](https://github.com/TuxInvader/X4-Info-Miner/blob/bcc98619a85f8e0cd50e53ea065149f09c506cfa/x4-save-miner.py)
- [x4-cat-miner.py](https://github.com/TuxInvader/X4-Info-Miner/blob/bcc98619a85f8e0cd50e53ea065149f09c506cfa/x4-cat-miner.py)

## 决定

1. 先保留每个 XML 元素的父节点、标签及字节偏移，XML 全文落盘。文本、注释、空白等保留在原文中，不为每个文本片段建立独立树节点。
2. 界面每页最多 200 行，属性和原文片段按需读取；所有查询和长任务放到独立后台进程。
3. 修改只替换已有属性值。未知节点无需重新序列化，避免重新格式化整个存档。
4. 第二阶段从用户实际安装的游戏、DLC 及中文语言资源建立静态字典，保留原始 ID。需要处理语言引用链与扩展覆盖顺序。
5. 再逐项建立钱、库存、船员等语义编辑功能，每项先确认真正的数据位置、重复摘要及关联约束。当前通用属性编辑不自动同步这些字段。

不同工具的“几秒加载”通常指抽取一部分业务对象，与本项目落盘索引所有元素的工作量不同，不能直接当作同口径性能比较。
