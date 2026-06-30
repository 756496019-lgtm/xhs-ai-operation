import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BRAND, WEEKLY_OVERALL, TOP_NOTES, HOUR_PERF, TITLE_LEN_PERF } from '../data/sample';
import { BrandHeader } from '../components/BrandHeader';

/**
 * WeeklyDashboard · 26 秒
 * 0:00-0:03  品牌渐入 + "W27 数据复盘"标题
 * 0:03-0:08  整体面板：3 个数字 count-up
 * 0:08-0:16  互动率 Top 3 笔记卡片依次飞入
 * 0:16-0:22  时段柱状图 + 标题长度甜点区
 * 0:22-0:26  收尾字卡：「数据反哺选题 · 闭环成立」
 */
export const WeeklyDashboard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: 'clamp' });
  const titleSpring = spring({ frame: frame - 30, fps, config: { damping: 12, stiffness: 100 } });

  const overallStart = 90;
  const overallEnd = 240;
  const totalNotes = Math.round(
    interpolate(frame, [overallStart, overallEnd], [0, WEEKLY_OVERALL.totalNotes], {
      extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
    })
  );
  const totalViews = Math.round(
    interpolate(frame, [overallStart, overallEnd], [0, WEEKLY_OVERALL.totalViews], {
      extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
    })
  );
  const likeRate = interpolate(
    frame,
    [overallStart, overallEnd],
    [0, WEEKLY_OVERALL.likeRate],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const overallOpacity = interpolate(frame, [60, 90], [0, 1], { extrapolateRight: 'clamp' });
  const noteCardEnter = (idx: number) =>
    spring({
      frame: frame - (240 + idx * 30),
      fps,
      config: { damping: 14, stiffness: 90 },
    });

  const hourBarOpacity = interpolate(frame, [480, 540], [0, 1], { extrapolateRight: 'clamp' });
  const hourBarProgress = interpolate(frame, [480, 600], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const titleLenOpacity = interpolate(frame, [600, 660], [0, 1], { extrapolateRight: 'clamp' });

  const outroSpring = spring({ frame: frame - 660, fps, config: { damping: 14, stiffness: 90 } });
  const outroOpacity = interpolate(frame, [660, 720], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const overallCardsHidden = frame > 360;

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${BRAND.bg0} 0%, ${BRAND.bg1} 100%)`,
        fontFamily: 'PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif',
      }}
    >
      <BrandHeader opacity={headerOpacity} />

      {/* 大标题 */}
      <div
        style={{
          position: 'absolute',
          top: 220,
          left: 60,
          right: 60,
          opacity: titleSpring,
          transform: `translateY(${(1 - titleSpring) * 30}px)`,
        }}
      >
        <div
          style={{
            fontSize: 22,
            color: BRAND.primarySoft,
            letterSpacing: 4,
            fontWeight: 700,
            marginBottom: 12,
          }}
        >
          {WEEKLY_OVERALL.weekLabel} · WEEKLY REVIEW
        </div>
        <div
          style={{
            fontSize: 80,
            fontWeight: 900,
            color: BRAND.text1,
            letterSpacing: -2,
            lineHeight: 1.05,
          }}
        >
          本周<span style={{ color: BRAND.primaryColor }}>数据复盘</span>
        </div>
      </div>

      {/* 整体面板：3 个数字 */}
      {!overallCardsHidden && (
        <div
          style={{
            position: 'absolute',
            top: 460,
            left: 60,
            right: 60,
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 18,
            opacity: overallOpacity,
          }}
        >
          {[
            { label: '本周笔记', value: totalNotes, suffix: '' },
            { label: '总阅读', value: totalViews.toLocaleString(), suffix: '' },
            { label: '点赞率', value: likeRate.toFixed(2), suffix: '%' },
          ].map((s, i) => (
            <div
              key={i}
              style={{
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.border}`,
                borderRadius: 18,
                padding: '24px 18px',
              }}
            >
              <div style={{ fontSize: 16, color: BRAND.text3, letterSpacing: 1, marginBottom: 8 }}>
                {s.label}
              </div>
              <div
                style={{
                  fontSize: 48,
                  fontWeight: 900,
                  background: `linear-gradient(135deg, ${BRAND.primaryColor} 0%, ${BRAND.primarySoft} 100%)`,
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                  lineHeight: 1,
                }}
              >
                {s.value}
                <span style={{ fontSize: 24, marginLeft: 4 }}>{s.suffix}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Top 3 笔记 */}
      {frame >= 240 && frame < 540 && (
        <div
          style={{
            position: 'absolute',
            top: 700,
            left: 60,
            right: 60,
          }}
        >
          <div
            style={{
              fontSize: 20,
              color: BRAND.primarySoft,
              letterSpacing: 3,
              fontWeight: 700,
              marginBottom: 24,
            }}
          >
            互动率 TOP 3
          </div>
          {TOP_NOTES.map((note, i) => {
            const enter = noteCardEnter(i);
            return (
              <div
                key={note.rank}
                style={{
                  marginBottom: 16,
                  background: BRAND.bgCard,
                  border: `1px solid ${BRAND.border}`,
                  borderRadius: 16,
                  padding: '22px 26px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 22,
                  opacity: enter,
                  transform: `translateX(${(1 - enter) * 60}px)`,
                }}
              >
                <div
                  style={{
                    fontSize: 64,
                    fontWeight: 900,
                    color: BRAND.primaryColor,
                    fontFamily: 'monospace',
                    minWidth: 80,
                    textAlign: 'center',
                  }}
                >
                  0{note.rank}
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      color: BRAND.text1,
                      lineHeight: 1.2,
                      marginBottom: 8,
                    }}
                  >
                    {note.title}
                  </div>
                  <div style={{ fontSize: 16, color: BRAND.text3 }}>
                    {note.views.toLocaleString()} 阅读 · {note.likes} 赞 · {note.saves} 收
                  </div>
                </div>
                <div
                  style={{
                    fontSize: 32,
                    fontWeight: 900,
                    color: BRAND.green,
                  }}
                >
                  {note.engagement}%
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 时段柱状图 + 标题长度 */}
      {frame >= 480 && frame < 720 && (
        <div
          style={{
            position: 'absolute',
            top: 460,
            left: 60,
            right: 60,
            opacity: hourBarOpacity,
          }}
        >
          <div
            style={{
              fontSize: 20,
              color: BRAND.primarySoft,
              letterSpacing: 3,
              fontWeight: 700,
              marginBottom: 24,
            }}
          >
            发布时段 · 最佳 22:00
          </div>
          <div
            style={{
              background: BRAND.bgCard,
              border: `1px solid ${BRAND.border}`,
              borderRadius: 18,
              padding: 28,
              display: 'flex',
              alignItems: 'flex-end',
              gap: 12,
              height: 280,
            }}
          >
            {HOUR_PERF.map((h) => {
              const maxEng = 22;
              const fullH = (h.engagement / maxEng) * 220;
              const animH = fullH * hourBarProgress;
              return (
                <div
                  key={h.hour}
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    height: '100%',
                  }}
                >
                  <div
                    style={{
                      fontSize: 14,
                      color: h.best ? BRAND.primarySoft : BRAND.text3,
                      fontWeight: h.best ? 800 : 500,
                      marginBottom: 6,
                    }}
                  >
                    {h.engagement}%
                  </div>
                  <div
                    style={{
                      width: '100%',
                      height: animH,
                      background: h.best
                        ? `linear-gradient(180deg, ${BRAND.primarySoft} 0%, ${BRAND.primaryColor} 100%)`
                        : BRAND.border,
                      borderRadius: 8,
                      boxShadow: h.best ? `0 0 24px ${BRAND.primaryColor}88` : 'none',
                    }}
                  />
                  <div
                    style={{
                      fontSize: 14,
                      color: h.best ? BRAND.primarySoft : BRAND.text3,
                      marginTop: 8,
                      fontFamily: 'monospace',
                      fontWeight: h.best ? 700 : 400,
                    }}
                  >
                    {h.hour}:00
                  </div>
                </div>
              );
            })}
          </div>

          {/* 标题长度甜点区 */}
          <div style={{ marginTop: 32, opacity: titleLenOpacity }}>
            <div
              style={{
                fontSize: 20,
                color: BRAND.primarySoft,
                letterSpacing: 3,
                fontWeight: 700,
                marginBottom: 16,
              }}
            >
              标题长度甜点区
            </div>
            <div
              style={{
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.border}`,
                borderRadius: 18,
                padding: '20px 28px',
                display: 'flex',
                gap: 12,
              }}
            >
              {TITLE_LEN_PERF.filter((t) => t.count > 0).map((t) => (
                <div
                  key={t.length}
                  style={{
                    flex: 1,
                    padding: '16px 12px',
                    border: t.best
                      ? `2px solid ${BRAND.primaryColor}`
                      : `1px solid ${BRAND.border}`,
                    borderRadius: 12,
                    textAlign: 'center',
                    background: t.best ? `${BRAND.primaryColor}1A` : 'transparent',
                  }}
                >
                  <div
                    style={{
                      fontSize: 18,
                      fontWeight: 700,
                      color: t.best ? BRAND.primarySoft : BRAND.text2,
                      marginBottom: 8,
                    }}
                  >
                    {t.length}
                  </div>
                  <div
                    style={{
                      fontSize: 30,
                      fontWeight: 900,
                      color: t.best ? BRAND.primarySoft : BRAND.text1,
                    }}
                  >
                    {t.engagement.toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

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
            fontSize: 50,
            fontWeight: 900,
            color: BRAND.text1,
            letterSpacing: -1,
            lineHeight: 1.2,
          }}
        >
          数据反哺选题，
          <br />
          <span style={{ color: BRAND.primaryColor }}>闭环成立</span>。
        </div>
        <div
          style={{
            fontSize: 20,
            color: BRAND.text3,
            marginTop: 20,
            letterSpacing: 2,
          }}
        >
          analytics → next_week_prompt → WorkBuddy
        </div>
      </div>
    </AbsoluteFill>
  );
};
