# analytics｜数据回收闭环模块

> 赛题 6 环节里的「环节 6：数据回收 → 反哺选题」。
>
> 阶段 B / C / D 全部跑通，端到端命令：
> `python cli.py --import examples/sample_export.csv --analyze --suggest --render`

---

## 它做什么

把小红书创作中心导出的 CSV 数据吃进来，自动算这些东西：

- 整体面板：笔记数 / 总阅读 / 整体点赞率 / 收藏率 / 评论率
- 互动率 Top 5（点赞+收藏+评论 / 阅读）
- 阅读量 Top 5
- 收藏率 Top（小红书长尾搜索的关键指标）
- 发布时段分布（找你账号的"最佳发文时段"）
- 标题长度 vs 表现
- 互动率最低 3 条（反面教材）

输出可读的中文终端报告 + JSON（`--json`）。

## 5 分钟跑通

```powershell
cd D:/project/xhs-yunying/analytics
python cli.py --import examples/sample_export.csv --analyze
```

第一次跑会建 `data/analytics.db`（SQLite）。

## 用真实数据跑

1. 登录小红书创作中心 / 创作中心 PRO
2. 进 数据中心 → 笔记数据 → 导出 CSV
3. 把 CSV 放在 `data/exports/your_export.csv`
4. ```powershell
   python cli.py --import data/exports/your_export.csv --analyze
   ```

CSV 列名 autodetect，支持的别名见 `csv_importer.py:COLUMN_ALIASES`，不在表里的可以加。

## 命令行

```
python cli.py --import CSV          # 导入 CSV 到 SQLite
python cli.py --analyze             # 跑分析（终端打印）
python cli.py --analyze --json      # 输出 JSON，给下游程序读
python cli.py --suggest             # 调 qwen-max 出下期选题 + WorkBuddy 触发话术
python cli.py --render              # 双风格卡片报告（暗黑+奶油）
python cli.py --db custom.db ...    # 自定义 DB 路径
python cli.py --snapshot-date 2026-06-22 ...  # 指定本次导入对应的快照日期
```

可以串起来一次性跑通：

```powershell
python cli.py --import data/exports/2026-06-22.csv --analyze --suggest --render
```

输出（在 `data/reports/`）：
- `next_week_prompt_W{N}.md` — 下期选题建议（人读 + WorkBuddy 触发话术）
- `next_week_prompt_W{N}_raw.json` — 原始 JSON（给下游程序读）
- `W{N}_dashboard.html` — 双风格卡片报告，浏览器打开下载 JPG

## 跨周追踪同一笔记

每次导入 CSV 都创建一份"快照"。同一 `note_id` 不同 `snapshot_date` 各占一行，自动支持"这条笔记上周 vs 这周阅读涨了多少"的对比（阶段 C 用得上）。

## SQLite 库长这样

```sql
notes        (note_id, title, publish_time, category, topic_keywords, first_seen)
snapshots    (id, note_id, snapshot_date, views, likes, saves, comments, shares)
followers    (date, count, net_increase)            -- 暂时手动填
```

DDL 在 `schema.py`，可以直接打开 `data/analytics.db` 用任何 SQLite 客户端看。

## 文件清单

| 文件 | 角色 |
|---|---|
| `cli.py` | 一键入口，argparse 总控 |
| `csv_importer.py` | CSV 解析 + 列名 autodetect + 容错（万/k/逗号/空值都吃得下） |
| `schema.py` | SQLite schema + 简单 upsert helper |
| `analyzer.py` | 互动率/时段/标题分析 + 终端 pretty print |
| `qwen_bridge.py` | 阶段 C：桥接 `crawler/content-monitor/qwen_client.py` 复用 19 个 AI 函数 |
| `topic_recommender.py` | 阶段 C：调 qwen 出 `next_week_prompt_W{N}.md` |
| `report_renderer.py` | 阶段 D：把分析结果转成 `render_xhs_cards.py` 的 cards JSON |
| `data/analytics.db` | SQLite 库（跑过 import 后自动出现） |
| `data/exports/` | 用户 CSV 原始文件放这里 |
| `data/reports/` | 渲染后的报告输出 |
| `examples/sample_export.csv` | 30 行脱敏样本，dry-run 用 |

## 设计选择

**为什么选 SQLite 而不是 pandas + CSV**：跨周追踪同一笔记的累计涨幅最自然的表达就是关系型。SQLite 是 Python 标准库，零额外依赖。

**为什么不复用 `content-monitor/trending_scorer.py`**：那是新闻向打分（折扣百分比、Weibo 指数、Metacritic 分），跟笔记自身表现完全是两个评估维度。新写一个简单的"互动率三件套"就够了。

**为什么 publish_time 当字符串存**：跨平台的 CSV 时间格式参差，统一成字符串后用切片取 hour 比 `datetime` 反复 parse 稳。

## 已知边界

- 不抓粉丝增长曲线（小红书后台 CSV 不带），需要手动维护 `followers` 表（阶段 C 会出辅助脚本）
- 不抓评论内容（CSV 只有评论数），所以做不了"用户在评论里关心什么"的语义分析
- `category` 字段当前默认空，阶段 C 会用 qwen 给每条笔记自动打类目

## 阶段 C / D 衔接说明（已完成）

阶段 C：`qwen_bridge.py` 通过 `sys.path.insert` 直接复用 `crawler/content-monitor/qwen_client.py` 已有的 19 个 AI 函数（含 `get_qwen_client`、`fact_check_content`），不重新封装客户端。

`topic_recommender.recommend_topics(analysis, benchmark_notes=None)` 输出：

```
data/reports/next_week_prompt_W{N}.md       # 给人读
data/reports/next_week_prompt_W{N}_raw.json # 给下游程序读
```

文件最后一段是给 `creator/xhs_console_agent/` 里 WorkBuddy 直接复制粘贴的"触发话术"。
qwen 输出会自动跑 `fact_check_content` 一遍，发现编造数字 / 未发生事件会在报告里加警告。

阶段 D：`report_renderer.py` 通过 vendored 的 `_vendor/render_xhs_cards.py`（来源 `D:/project/xhs-weeklyreport/`）调用 `render_dual_html()`，输出：

```
data/reports/W{N}_dashboard.html
```

包含 5 张卡片：
1. 封面卡（笔记数 / 整体互动率 / 本周爆款）
2. 互动率 Top 3
3. 最佳发布时段
4. 标题长度黄金区间
5. 反面案例（互动率最低 3 条）
+ 可选：下期选题反哺卡（如果上次跑过 `--suggest`）

浏览器打开后点"下载全部 JPG"按钮可导出双风格小红书卡片（暗黑 + 奶油）。
