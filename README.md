# X4SaveEditor · X4 存档修改器

本地中文桌面工具，完整解析 X4: Foundations 大型 XML 存档，支持分页浏览、属性修改和校验后另存。

**v0.1.0 是桌面第一版。** 需要 Windows 和 Python 3.11 或更新版本（含 Tkinter）。应用只使用 Python 标准库，无需安装第三方 Python 包。

## 启动与使用

1. 下载源码并解压，双击 `启动X4存档修改器.cmd` 或 `start.cmd`。
2. 打开 `.xml.gz` 或 UTF-8 `.xml` 存档。首次后台建立完整索引，文件未变时复用缓存。
3. 双击节点进入子节点；支持标签、ID、节点编号及名称 / macro 摘要查询。每页最多 200 条。
4. 选中节点查看属性及原始 XML 片段，双击属性修改。修改先进入清单，可逐项撤销。
5. 选择“导出新存档”。新文件完整回读校验通过后才生成，已有文件拒绝覆盖，原存档保持不变。

也可运行 `python editor.py`。关闭窗口即可退出。

## 当前范围

- 解析并索引所有 XML 元素，不限于玩家资产。未知节点及原始 ID 保留，暂未翻译 ID。
- 通用编辑已有属性；暂不添加 / 删除节点，也不提供自动同步多个关联字段的业务按钮。
- XML 结构及属性回读校验不等于游戏逻辑校验。例如摘要 money 可能不是实际账户字段。
- 原始文本、注释、CDATA 和空白字节保留，导出只替换指定属性值。原文面板最多读取 16 KiB，可能包含后续节点。
- 尚未验证游戏内加载及修改效果。自定义导出名称不一定对应游戏槽位，请退出游戏并备份后再管理槽位文件。

## 大存档性能

后台流式解析，SQLite 保存父子关系及标签索引，界面按页读取；不把整个 XML 建成内存树。

一份实际测试存档展开后约 943 MiB、1,515 万个节点：首次打开约 52 秒，核心缓存重开约 5.5 毫秒，测试进程峰值工作集约 101 MiB。导出及完整校验约 15.4 秒。结果只代表所测电脑和存档，详见 [PERFORMANCE.md](PERFORMANCE.md)。

每份缓存包含解压 XML 和数据库；上述样本约占 2.15 GiB。名称包含查询比精确索引查询慢，在后台执行。底部进度条是忙碌指示，不代表完成比例；文字显示当前阶段和已处理量。

缓存保存在 `.cache/`，性能测试副本与报告保存在 `.local/`。程序关闭后可清理这些目录。低压缩级别优先速度，导出的 gzip 可能大于原文件。

## 测试

```powershell
python -m unittest discover -s tests -v
python tests/gui_smoke.py
python benchmark.py "你的存档.xml.gz" --fresh --export
```

自动测试使用代码生成的合成存档。性能脚本仅在 `.local` 创建测试副本，并验证原始文件哈希不变。

## 许可证与致谢

项目自身代码和文档采用 [MIT License](LICENSE)，版权署名为 `X4SaveEditor contributors`。

感谢 X4Companion、x4-savegame-parser、X4-Info-Miner、x4-core 与 BeamerMiasma/X4-Foundations 的公开资料。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 记录作者、固定提交及许可核对；技术取舍见 [RESEARCH.md](RESEARCH.md)。当前源码未包含这些项目的代码或数据。

本项目是非官方工具，与 Egosoft 无隶属或背书关系。MIT 许可不涵盖游戏程序、资源、商标及用户存档。

## 发布范围

仅发布源码、启动脚本、合成数据测试、文档及许可文件。不分发真实存档、缓存、日志、截图、个人配置或游戏资源。`.gitignore` 不会过滤手工压缩整个工作目录的内容；发布前检查实际跟踪文件和归档，保留 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。
