# 常用节点快捷入口

快捷入口显示在网页版的“常用节点”区域，可折叠。加载存档后自动识别并显示节点数量；找不到的入口显示 0 并禁用。点击只切换浏览结果，不修改任何字段。结果支持每页 200 行、下一页与返回，仍可继续进入子节点。

## 定位规则

这里的路径是规则说明，不是用户需要输入的 XPath。节点编号和对象 ID 均从当前存档读取，没有硬编码示例存档的位置。

| 入口 | 实际定位范围 |
| --- | --- |
| 玩家资金 | `info/player@money`、`faction[@id='player']/account`、与主账户 ID 相同的其他 `account`、顶层 `stats/stat[@id='money_player']`。不会因为金额相等就纳入其他账户。 |
| 玩家角色 | `component[@class='player']`。 |
| 个人背包 | 玩家角色直接子节点 `inventory` 内的条目，不是全存档所有 inventory。 |
| 已有蓝图 | 玩家角色 `blueprints` 下的条目。 |
| 科研记录 | 玩家角色 `research` 下的条目，可能只包含已开始或完成的研究。 |
| 玩家相关声望 | 顶层阵营定义中：玩家对其他阵营，以及其他阵营对玩家的 `relation` 和 `booster`，显示关系方向和临时加成类型。 |
| 玩家许可证 | 玩家阵营 `licences` 下的条目。 |
| 玩家舰船 | `component` 的 class 以 `ship_` 开头且实际 `owner` 属性严格等于 `player`。 |
| 玩家空间站 | `component[@class='station'][@owner='player']`。 |
| 建造仓储 | `component[@class='buildstorage'][@owner='player']`。 |
| 船员 / 人员技能 | `skills` 节点向上寻找最近带 owner 属性的 component，仅保留 owner=player 的节点。包含具名 NPC 与匿名船员；显式属于其他阵营的人员不因身处玩家船上而纳入。 |
| 货仓 / 弹药 | 同样按最近显式归属定位的 `cargo`、`ammunition` 容器。双击进入条目。 |
| 舰船 / 装备改装 | 同样按最近显式归属定位的 `modification` 容器。 |
| 地图 / 百科记录 | 玩家角色下的 `known`、`discovered`、`unlocks` 容器。 |
| 任务记录 | 顶层 `missions` 的直接子节点。 |

摘要列补充账户用途、关系方向或归属对象，原始 ID / macro 保留。以上是可解释的导航规则；新的游戏版本或模组可能采用不同结构，此时可退回完整结构浏览。

## 与游戏内 Cheat Menu 的区别

Cheat Menu 可以调用运行中的游戏脚本处理依赖、生成实体或触发事件。本工具目前只把常见需求对应到存档中的现有节点，不提供一键加钱、全解锁、生成舰船、传送或无敌操作。

例如资金在多个位置存在记录，但入口不会自动同步修改；声望有双向关系及临时 booster；科研可能涉及前置条件；任务还依赖 MD 状态。浏览入口找到节点不代表任意改值都能在游戏中生效。

## 性能

在现有完整节点索引上额外建立 `shortcuts-v1.db`，位于相应的私有 `.cache` 目录内。无需重新解压或建立全量 XML 索引，不修改原存档或其原文快照。后台读取少量目标标签及归属链，界面保持可响应。

对约 943 MiB、1,515 万节点的实际存档：首次识别约 4.0 秒；快捷索引约 588 KiB；缓存目录统计约 2.0 毫秒，玩家舰船一页查询约 4.3 毫秒。这是本机核心函数测量，非跨机器的性能保证。

## 参考来源

查阅日期：2026-09-27。仅参考公开功能分类及字段说明，未复制第三方脚本、资产或字典。

- [X4 CHEAT MENU — slan / fsnlan](https://www.nexusmods.com/x4foundations/mods/73)：功能涵盖玩家、舰船、空间站、船员、货物和地图，作为常用需求分类的参考。未下载或再分发其受限资源。
- [Safe Cheat Panel](https://www.nexusmods.com/x4foundations/mods/1971)：玩家、背包、科研、蓝图、声望、探索及人员等功能分组；参考界面分组，不声称本工具具有相同能力。
- [StarnsBetterCheats README](https://github.com/Starnsworth/StarnsBetterCheats/blob/6d27a4f1235caf5599f17947a645a8afdb74e85a/README.md)：参考常见作弊需求，未把该项目的路线图视为已实现功能。
- [Mistralys 存档编辑笔记](https://github.com/Mistralys/x4-game-notes/blob/2fc21da58c77a89a78a1781eaf2895dace60181d/cheats-savegame-editing.md)：参考背包与玩家组件、蓝图和资金相关字段；账户匹配采用实际 ID 与上下文，没有使用全文替换相同金额的办法。
- [X4Companion writer.rs](https://github.com/dirlligafu/X4Companion/blob/df6901cbbc594bf91227b8bf2b0f6437d69807ca/src-tauri/src/writer.rs)：对照资金、库存、研究及人员技能等上下文，未移植其实现。

最终定位规则已与本机实际存档结构核对，并由合成存档测试覆盖玩家 / NPC 分离、账户 ID 匹配、关系方向、缺失节点及分页行为。许可范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 与功能面板的关系

常用节点现位于“高级结构浏览”，依然只负责定位。金钱、势力关系、货仓、未拥有蓝图和船员技能的实际修改使用独立功能面板；已有蓝图快捷入口只展示当前快照，解锁新蓝图请使用“解锁蓝图”面板。
