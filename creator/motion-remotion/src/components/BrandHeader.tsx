import React from 'react';
import { BRAND } from '../data/sample';

export const BrandHeader: React.FC<{ opacity?: number }> = ({ opacity = 1 }) => {
  return (
    <div
      style={{
        position: 'absolute',
        top: 60,
        left: 60,
        right: 60,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        opacity,
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          background: `linear-gradient(135deg, ${BRAND.primaryColor} 0%, ${BRAND.primarySoft} 100%)`,
          display: 'grid',
          placeItems: 'center',
          fontSize: 28,
          fontWeight: 900,
          color: BRAND.bg1,
          boxShadow: `0 8px 24px ${BRAND.primaryColor}66`,
        }}
      >
        小
      </div>
      <div>
        <div
          style={{
            fontSize: 28,
            fontWeight: 900,
            color: BRAND.text1,
            letterSpacing: -0.5,
            lineHeight: 1.1,
          }}
        >
          {BRAND.name}
        </div>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: BRAND.text3,
            letterSpacing: 2,
            marginTop: 4,
          }}
        >
          {BRAND.subtitle}
        </div>
      </div>
    </div>
  );
};
