import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BRAND, GROWTH_POINTS } from '../data/sample';
import { BrandHeader } from '../components/BrandHeader';

/**
 * GrowthAnimation · 28 秒
 * 0:00-0:03  品牌渐入
 * 0:03-0:05  标题"4 个月"字卡 spring 弹入
 * 0:05-0:18  增长曲线沿 stroke-dashoffset 绘制 + 数字 count-up
 * 0:18-0:22  关键节点高亮（破千 / 当前 2982）
 * 0:22-0:28  收尾字卡："真实战绩 · 不是样板间"
 */
export const GrowthAnimation: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: 'clamp' });

  const titleSpring = spring({
    frame: frame - 60,
    fps,
    config: { damping: 12, stiffness: 100 },
  });

  // 曲线绘制进度（0:05 → 0:18 = frame 150 → 540）
  const drawProgress = interpolate(frame, [150, 540], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // 数字 count-up
  const totalFollowers = 2982;
  const countUp = Math.round(
    interpolate(frame, [150, 540], [0, totalFollowers], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    })
  );

  // 节点高亮（0:18-0:22）
  const milestoneOpacity = interpolate(frame, [540, 600], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // 收尾字卡（0:22-0:28）
  const outroSpring = spring({
    frame: frame - 660,
    fps,
    config: { damping: 14, stiffness: 90 },
  });
  const outroOpacity = interpolate(frame, [660, 720], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // 曲线：把 GROWTH_POINTS 映射到 SVG 坐标
  const chartLeft = 100;
  const chartRight = width - 100;
  const chartTop = 800;
  const chartBottom = 1380;
  const maxFollowers = 3000;
  const maxWeek = GROWTH_POINTS[GROWTH_POINTS.length - 1].week;
  const points = GROWTH_POINTS.map((p) => ({
    ...p,
    x: chartLeft + (p.week / maxWeek) * (chartRight - chartLeft),
    y: chartBottom - (p.followers / maxFollowers) * (chartBottom - chartTop),
  }));
  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ');

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${BRAND.bg0} 0%, ${BRAND.bg1} 50%, #1A1410 100%)`,
        fontFamily: 'PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif',
      }}
    >
      {/* 背景装饰光晕 */}
      <div
        style={{
          position: 'absolute',
          top: 200,
          right: -200,
          width: 700,
          height: 700,
          background: `radial-gradient(circle, ${BRAND.primaryColor}1F 0%, transparent 70%)`,
          borderRadius: '50%',
        }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: -100,
          left: -200,
          width: 600,
          height: 600,
          background: `radial-gradient(circle, ${BRAND.cyan}14 0%, transparent 70%)`,
          borderRadius: '50%',
        }}
      />

      <BrandHeader opacity={headerOpacity} />

      {/* 主标题 spring 弹入 */}
      <div
        style={{
          position: 'absolute',
          top: 280,
          left: 60,
          right: 60,
          textAlign: 'center',
          transform: `scale(${0.8 + titleSpring * 0.2})`,
          opacity: titleSpring,
        }}
      >
        <div
          style={{
            fontSize: 36,
            color: BRAND.primarySoft,
            letterSpacing: 8,
            fontWeight: 700,
            marginBottom: 20,
          }}
        >
          4 个月
        </div>
        <div
          style={{
            fontSize: 110,
            fontWeight: 900,
            color: BRAND.text1,
            letterSpacing: -2,
            lineHeight: 1,
          }}
        >
          0 →{' '}
          <span
            style={{
              background: `linear-gradient(135deg, ${BRAND.primaryColor} 0%, ${BRAND.primarySoft} 100%)`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            {countUp.toLocaleString()}
          </span>
        </div>
        <div
          style={{
            fontSize: 28,
            color: BRAND.text2,
            marginTop: 24,
            letterSpacing: 4,
          }}
        >
          XIAOHONGSHU FOLLOWERS
        </div>
      </div>

      {/* 增长曲线 SVG */}
      <svg
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      >
        <defs>
          <linearGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={BRAND.primaryColor} stopOpacity={0.4} />
            <stop offset="100%" stopColor={BRAND.primaryColor} stopOpacity={0} />
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 网格 */}
        {[1000, 2000, 3000].map((v) => {
          const y = chartBottom - (v / maxFollowers) * (chartBottom - chartTop);
          return (
            <g key={v}>
              <line
                x1={chartLeft}
                y1={y}
                x2={chartRight}
                y2={y}
                stroke={BRAND.border}
                strokeDasharray="4 8"
                opacity={drawProgress}
              />
              <text
                x={chartLeft - 12}
                y={y + 6}
                fill={BRAND.text3}
                fontSize={20}
                textAnchor="end"
                opacity={drawProgress}
                fontFamily="monospace"
              >
                {v}
              </text>
            </g>
          );
        })}

        {/* 填充面积（沿 drawProgress 拉伸） */}
        <clipPath id="growthClip">
          <rect
            x={chartLeft}
            y={chartTop - 20}
            width={(chartRight - chartLeft) * drawProgress}
            height={chartBottom - chartTop + 40}
          />
        </clipPath>
        <path
          d={`${pathD} L ${points[points.length - 1].x} ${chartBottom} L ${chartLeft} ${chartBottom} Z`}
          fill="url(#growthGrad)"
          clipPath="url(#growthClip)"
        />

        {/* 主线（stroke-dashoffset 动画） */}
        <path
          d={pathD}
          stroke={BRAND.primaryColor}
          strokeWidth={5}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - drawProgress}
          filter="url(#glow)"
        />

        {/* 节点圆点 */}
        {points.map((p, i) => {
          if (!p.label) return null;
          const reached = (i / (points.length - 1)) <= drawProgress;
          if (!reached) return null;
          const isLast = i === points.length - 1;
          return (
            <g key={i} opacity={milestoneOpacity}>
              <circle
                cx={p.x}
                cy={p.y}
                r={isLast ? 14 : 10}
                fill={isLast ? BRAND.primarySoft : BRAND.primaryColor}
                stroke={BRAND.bg0}
                strokeWidth={3}
              />
              <text
                x={p.x}
                y={p.y - 30}
                fill={isLast ? BRAND.primarySoft : BRAND.text2}
                fontSize={isLast ? 26 : 22}
                fontWeight={isLast ? 900 : 700}
                textAnchor="middle"
              >
                {p.label}
              </text>
              {isLast && (
                <text
                  x={p.x}
                  y={p.y - 60}
                  fill={BRAND.primarySoft}
                  fontSize={20}
                  fontWeight={700}
                  textAnchor="middle"
                  letterSpacing={2}
                >
                  {p.followers}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* 收尾字卡 */}
      <div
        style={{
          position: 'absolute',
          bottom: 200,
          left: 60,
          right: 60,
          textAlign: 'center',
          opacity: outroOpacity,
          transform: `translateY(${(1 - outroSpring) * 40}px)`,
        }}
      >
        <div
          style={{
            fontSize: 56,
            fontWeight: 900,
            color: BRAND.text1,
            letterSpacing: -1,
            lineHeight: 1.2,
          }}
        >
          真实战绩，
          <br />
          不是<span style={{ color: BRAND.primaryColor }}>样板间</span>。
        </div>
        <div
          style={{
            fontSize: 22,
            color: BRAND.text3,
            marginTop: 24,
            letterSpacing: 3,
          }}
        >
          AI 辅助 · 一个人 · 4 个月
        </div>
      </div>
    </AbsoluteFill>
  );
};
