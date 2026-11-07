import { Composition } from 'remotion';
import { KaraokeVideo } from './KaraokeVideo';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="KaraokeVideo"
        component={KaraokeVideo}
        durationInFrames={DURATION_FRAMES}
        fps={FPS}
        width={1280}
        height={720}
        defaultProps={{
          words: WORDS_JS,
          audioFile: "AUDIO_FILE",
          wordsPerLine: WORDS_PER_LINE,
          backgroundImage: BACKGROUND_IMAGE
        }}
      />
    </>
  );
};
