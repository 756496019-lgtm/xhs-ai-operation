/**
 * 动效视频用到的样本数据。
 * 真实跑的时候应该从 analytics/data/ 读取，这里硬编码方便预览。
 *
 * 与 analytics/examples/sample_export.csv 的 30 条样本数据对得上。
 */

export const BRAND = {
  name: '小红书运营',
  subtitle: 'AI 内容生产闭环',
  primaryColor: '#E8820C',
  primarySoft: '#F5B820',
  bg0: '#0A0F18',
  bg1: '#0F1722',
  bgCard: '#16202E',
  border: '#1F2D40',
  text1: '#F1F5FB',
  text2: '#9BAAC2',
  text3: '#6A7A92',
  green: '#4ADE80',
  cyan: '#22D3EE',
  red: '#E86060',
};

export const GROWTH_POINTS = [
  { week: 0,  followers: 0,    label: 'M0' },
  { week: 1,  followers: 32 },
  { week: 2,  followers: 78 },
  { week: 3,  followers: 210 },
  { week: 4,  followers: 412,  label: 'M1' },
  { week: 5,  followers: 580 },
  { week: 6,  followers: 720 },
  { week: 7,  followers: 990 },
  { week: 8,  followers: 1240, label: 'M2 · 破千' },
  { week: 9,  followers: 1480 },
  { week: 10, followers: 1730 },
  { week: 11, followers: 1980 },
  { week: 12, followers: 2210, label: 'M3' },
  { week: 13, followers: 2480 },
  { week: 14, followers: 2700 },
  { week: 15, followers: 2880 },
  { week: 16, followers: 2982, label: 'M4 · 当前' },
];

export const WEEKLY_OVERALL = {
  weekLabel: 'W27',
  totalNotes: 30,
  totalViews: 222860,
  likeRate: 7.93,
  saveRate: 9.9,
  commentRate: 1.76,
};

export const TOP_NOTES = [
  {
    rank: 1,
    title: '魂系新人怎么选|从血源到艾尔登法环',
    engagement: 23.02,
    views: 8740,
    likes: 712,
    saves: 1102,
  },
  {
    rank: 2,
    title: '2026目前最值得买的5款国产单机',
    engagement: 22.54,
    views: 13680,
    likes: 1190,
    saves: 1638,
  },
  {
    rank: 3,
    title: 'Switch 2评测出了|首发买不买',
    engagement: 22.17,
    views: 16520,
    likes: 1485,
    saves: 1890,
  },
];

export const HOUR_PERF = [
  { hour: 9,  count: 1, engagement: 5.86 },
  { hour: 10, count: 2, engagement: 11.7 },
  { hour: 11, count: 1, engagement: 10.12 },
  { hour: 14, count: 2, engagement: 14.02 },
  { hour: 18, count: 2, engagement: 11.79 },
  { hour: 19, count: 8, engagement: 19.62 },
  { hour: 20, count: 4, engagement: 19.77 },
  { hour: 21, count: 6, engagement: 19.85 },
  { hour: 22, count: 4, engagement: 20.10, best: true },
];

export const TITLE_LEN_PERF = [
  { length: '≤10字',   count: 0,  engagement: 0 },
  { length: '11-15字', count: 4,  engagement: 15.47 },
  { length: '16-20字', count: 15, engagement: 19.15, best: true },
  { length: '20+字',   count: 11, engagement: 16.12 },
];
