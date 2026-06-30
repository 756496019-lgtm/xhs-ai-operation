# Snapshot 说明

此目录是 `D:/project/content-monitor/` 在 2026-06-29 的代码快照，仅用于本项目展示和复现。

## 与原仓的关系

- 原仓位置：`D:/project/content-monitor/`，继续日常迭代
- 本快照：**只复制代码，不双向同步**，不修改文件内容
- 已排除：`video_outputs/`（1.4GB 运行时视频产物）、`__pycache__/`、`xhs_uploads/`、`weekly_cache/`、`fan_tag_output/`、`playwright_chrome_profile/`、`*.pyc`、`*.log`
- 复制大小：约 9 MB（代码 + 模板 + 静态资源）

## 在本仓的角色

承担赛题 6 环节里的「环节 1：素材库构建」和「环节 4：内容改写」：
- 14 个 scrapers 多源素材采集（Reddit/微博超话/B站/TapTap/触乐/17173/游民/Epic/Steam/eShop/...）
- `qwen_client.py` 的 19 个 AI 函数被 `analytics/qwen_bridge.py` 复用
- 双路径改写 + `fact_check_content` 事实核查链路

## 重要：日常运营请走原仓

本快照是展示快照。日常更新、新功能开发、Bug 修复都在 `D:/project/content-monitor/` 完成，不要在本目录里改。
