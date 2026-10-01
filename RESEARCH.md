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

## 空间站资源数据边界

[Egosoft 的空间站建造与管理指南](https://wiki.egosoft.com/X4%20Foundations%20Wiki/Manual%20and%20Guides/X4%3A%20Foundations%20Manual/Station%20Building%20And%20Management/?language=en)区分生产模块、按物资分配的仓储空间，以及经理管理的自动仓储配额。修改器从存档的 `station` 与独立 `buildstorage` 组件分别读取实体 `storage/cargo/ware` 库存；交易预留及资源缺口是另外的状态记录，不计入库存。单件体积、运输类型和实体货仓容量只从用户本机游戏资源读取。总量修改会保留无关 XML 字节并校验合并后的货仓容量，但不会重算经理配额、交易订单或生产流程。

## 外交与特工数据边界

[Egosoft 8.00 更新说明](https://www.egosoft.com/news/archive/2025September_en.php)将 Diplomacy 列为免费基础游戏更新，Envoy Pack 是同期推出的 DLC；[开发说明](https://m.egosoft.com/news/archive/2025July_en.php)提到势力外交及谈判、谍报特工。实现依据本机 9.00 游戏脚本与存档核对字段，不复制或分发游戏资源。玩家的 `diplomacy` 节点保存 `influence` 与已登记特工的组件引用；对应 NPC 的黑板分别保存 `$diplomacy_exp_negotiation` 和 `$diplomacy_exp_espionage`。本机脚本按经验 0、10、20、50、100、200 的门槛计算 0–5 级，存档没有独立等级字段；经验在 200 后仍可累积，未查到硬上限。影响力的最高显示档位从 33 起，本机脚本存在单次授予 300 的调试操作，但没有找到余额的绝对上限。因此编辑器人为限制影响力写入 300、单项经验写入 200，防止无意义的巨大值；这些不是游戏数据类型的硬上限。势力对的基础值保存在双方各自的 `faction/relations/relation`；本工具设置两向相同值并清除这对势力的 `booster`，不修改玩家声望或外交事件状态。缺失的基础值仍按“游戏默认”显示，锁定及歧义记录不写入。游戏中的动态事件可再次改变这些值。
