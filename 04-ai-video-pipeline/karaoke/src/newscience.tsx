import React from "react";
import {
  AbsoluteFill,
  Audio,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";

const newscience: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // Load JSON dynamically from public folder
  const backgroundTimestamps = require('../public/background_timestamps.json');
  const karaokeData = require('../public/science_karaoke.json');

  // Use the precise timestamp mapping
  const backgroundSwitches = backgroundTimestamps.background_switches;

  // Determine current background based on current time
  let currentBackground = backgroundSwitches[0];
  for (let i = 0; i < backgroundSwitches.length; i++) {
    const switch_data = backgroundSwitches[i];
    if (currentTime >= switch_data.start_time && currentTime <= switch_data.end_time) {
      currentBackground = switch_data;
      break;
    }
    if (currentTime > switch_data.end_time) {
      currentBackground = switch_data; // keep last passed as fallback
    }
  }

  // Active line: show words around current time
  const words = karaokeData.words;
  const visibleWords = words.filter((w: any) => currentTime >= w.start - 0.2 && currentTime <= w.end + 0.01);

  return (
    <AbsoluteFill style={{ backgroundColor: "black", justifyContent: "center", alignItems: "center" }}>
      {/* Background */}
      {currentBackground && (
        <img
          src={staticFile(currentBackground.image_filename)}
          style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}

      {/* Audio */}
      <Audio src={staticFile(karaokeData.audio_file || "Blackholes.mp3")} startFrom={0} />

      {/* Words */}
      <div style={{ color: "white", fontSize: 48, textAlign: "center", zIndex: 10, padding: 50 }}>
        {visibleWords.map((word: any, idx: number) => (
          <span key={idx} style={{ color: currentTime >= word.start && currentTime <= word.end ? "#ffff66" : "#cccccc" }}>{word.word}{" "}</span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export default newscience;
