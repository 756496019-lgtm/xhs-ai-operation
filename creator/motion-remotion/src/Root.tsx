import React from 'react';
import { Composition } from 'remotion';
import { GrowthAnimation } from './compositions/GrowthAnimation';
import { WeeklyDashboard } from './compositions/WeeklyDashboard';

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="GrowthAnimation"
        component={GrowthAnimation}
        durationInFrames={28 * FPS}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
      <Composition
        id="WeeklyDashboard"
        component={WeeklyDashboard}
        durationInFrames={26 * FPS}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
