# motion-remotion｜代码驱动的动效视频

> 用 React 写视频。`creator/xhs_console_agent/04-video-editor` 的 PV 拼接路线之外，另一条互补的"数据可视化 + 字卡动画"路线。
>
> 基于 [Remotion 4.x](https://remotion.dev)，TypeScript + React 18。

---

## 它解决什么问题

`creator/xhs_console_agent/04-video-editor`（MoviePy 路线）擅长"PV 拼接 + 配音对齐"——题材有官方 PV / 实拍素材时最快。

但还有大量场景**没有 PV**：

- 周复盘：纯数据 + 文字
- 增长复盘：粉丝曲线 / 互动率柱状图
- 选题预告：标题 + 关键词的字卡动画
- 行业资讯快报：信息密度大、视觉变化快

这些场景靠 PV 拼接做不出来。靠剪映手撸 keyframe 又慢又不可复用。

Remotion 把这一类视频变成**纯代码**——React 组件 + 时间轴 + spring 动画。改一个数字，重新 render 就出新视频。

## 已实测跑通

```
out/growth_120.png   ← GrowthAnimation @ frame 120（标题 spring 入场）
out/growth_400.png   ← GrowthAnimation @ frame 400（曲线绘制中）
out/growth_700.png   ← GrowthAnimation @ frame 700（收尾字卡）
out/weekly_300.png   ← WeeklyDashboard @ frame 300（Top 3 笔记飞入）
out/weekly_550.png   ← WeeklyDashboard @ frame 550（时段柱状图 + 标题长度）
```

每张都是 1080×1920 竖屏（小红书视频规格），从 React 组件直接渲染出来。

## 两个示例 Composition

### GrowthAnimation · 28 秒

讲"4 个月 0 → 2982 粉"的真实增长故事，节奏：

| 时间段 | 内容 | 动画手法 |
|---|---|---|
| 0:00 – 0:03 | 品牌 logo 渐入 | opacity interpolate |
| 0:03 – 0:05 | 标题"4 个月 0→2982" | spring 弹入 |
| 0:05 – 0:18 | 增长曲线沿路径绘制 | `stroke-dashoffset` 沿 1 → 0 |
| 0:18 – 0:22 | 关键节点高亮（M2 破千 / M4 当前） | clipPath + 圆点缩放 |
| 0:22 – 0:28 | 收尾字卡："真实战绩，不是样板间" | spring + translateY |

### WeeklyDashboard · 26 秒

讲"W27 数据复盘"的可视化，节奏：

| 时间段 | 内容 |
|---|---|
| 0:00 – 0:03 | "W27 · 本周数据复盘"标题 spring |
| 0:03 – 0:08 | 整体面板：30 笔记 / 222,860 阅读 / 7.93% 点赞率（3 个数字 count-up） |
| 0:08 – 0:16 | 互动率 Top 3 笔记卡片依次飞入（每张延迟 1 秒） |
| 0:16 – 0:22 | 时段柱状图（22:00 高亮发光）+ 标题长度甜点区 |
| 0:22 – 0:26 | 收尾："数据反哺选题，闭环成立" |

## 怎么跑

### 1. 装依赖（首次）

```powershell
cd D:\project\xhs-yunying\creator\motion-remotion
npm install
```

约 18 秒装 189 个包。会下载一次 113MB headless chrome（首次 render 时下载，后续缓存）。

### 2. 实时预览（推荐开发用）

```powershell
npm run dev
```

打开 `http://localhost:3000`，左侧 sidebar 选 composition，右侧实时预览，可以拖时间轴看每一帧、改代码 hot-reload。

### 3. 渲染单帧（最快验证）

```powershell
npx remotion still GrowthAnimation out/preview.png --frame=400
```

frame 0-839 任选（28 秒 × 30 fps）。

### 4. 渲染完整视频

```powershell
npm run build:growth     # → out/growth.mp4 (28 秒)
npm run build:weekly     # → out/weekly.mp4 (26 秒)
npm run build:all        # 两个都跑
```

完整 render ~5-7 分钟（CPU 编码 H.264）。GPU 编码可加 `--codec h264-mkv --concurrency=1 --gl=angle` 等参数提速。

## 文件结构

```
motion-remotion/
├── package.json
├── tsconfig.json
├── remotion.config.ts
├── src/
│   ├── index.ts                    # registerRoot 入口
│   ├── Root.tsx                    # 注册所有 Composition
│   ├── compositions/
│   │   ├── GrowthAnimation.tsx     # 增长动画
│   │   └── WeeklyDashboard.tsx     # 周复盘动画
│   ├── components/
│   │   └── BrandHeader.tsx         # 顶部 logo + 品牌（两 composition 共用）
│   └── data/
│       └── sample.ts               # 样本数据（与 analytics/examples 对得上）
└── out/                            # 渲染产物
```

## 怎么换数据

不要改 composition 代码。直接改 `src/data/sample.ts`：

```typescript
export const WEEKLY_OVERALL = {
  weekLabel: 'W28',           // ← 改这里
  totalNotes: 32,             // ← 真实数据
  totalViews: 285000,
  likeRate: 8.4,
  // ...
};

export const TOP_NOTES = [
  { rank: 1, title: '...', engagement: 24.5, views: 12000, likes: 980, saves: 1500 },
  // ...
];
```

`sample.ts` 字段命名与 `analytics/data/analytics.db` 的 schema 对齐，将来可加一个 export 脚本自动从 SQLite 生成 `data/{week}.ts`。

## 与 analytics 的连接（路线图）

当前是手动同步数据。后续可以加：

```python
# analytics/cli.py 增加 --motion 选项
# 把 analyzer.analyze() 的 dict → motion-remotion/src/data/W{N}.ts
# 然后调 npm run build:weekly 自动出视频
```

这样 `python cli.py --import xxx.csv --motion` 一条命令出周复盘视频。

## 视觉规范

沿用本仓的小红书周报双色板：

| 角色 | 颜色 |
|---|---|
| 主色 | `#E8820C` |
| 强调 | `#F5B820` |
| 背景 | `#0A0F18` → `#0F1722`（渐变） |
| 卡片 | `#16202E` |
| 边框 | `#1F2D40` |
| 正文 | `#F1F5FB` |
| 次要 | `#9BAAC2` |
| 提示 | `#6A7A92` |
| 成功（互动率） | `#4ADE80` |

字体：`PingFang SC, Hiragino Sans GB, Microsoft YaHei`（macOS / Windows 都覆盖）。

## 已知边界

- 第一次 render 会下载 113MB headless chrome，需联网
- 完整 28 秒视频在 4 核 CPU 上 ~5 分钟。短视频影响小，做长内容（>2 分钟）建议加 GPU 加速
- 中文字体在 headless chrome 里靠系统字体降级解析，不同机器可能有微小差异；要 100% 一致可在 `public/` 放 .woff2 字体显式 `@font-face`
- `useCurrentFrame()` 是同步的，不能在异步函数里用——所有动画状态必须基于 frame 计算

## 不要做的事

- 不要在 composition 里发起网络请求或读文件——render 时是 headless chrome，没有 Node 环境的 fs/fetch
- 不要在动画里堆太多 SVG 元素（>500 个）——浏览器布局阶段会拖慢 render
- 不要用 `setTimeout` / `setInterval`——视频是 frame-deterministic 的，时间靠 `useCurrentFrame()` 推

## 设计选择

**为什么不沿用 04-video-editor 的 MoviePy**：MoviePy 写动效视频要堆 keyframe + 大量 ImageClip / TextClip 组合，可读性差且不能 hot-reload。Remotion 用 React 写一遍，所见即所得。

**为什么不用 After Effects + Lottie**：AE 不是程序员栈，团队同步 .aep 文件、版本管理都麻烦。Remotion 是纯文本（TS），git diff 友好。

**为什么不用 Chart.js / D3 + 录屏**：数据动画要求精确 frame 对齐，浏览器录屏会丢帧。Remotion 是 frame-deterministic 的，每一帧都精确控制。
