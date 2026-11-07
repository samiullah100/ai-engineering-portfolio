import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
  Easing,
} from 'remotion';

interface Word {
  word: string;
  start: number;
  end: number;
}

interface KaraokeVideoProps {
  words: Word[];
  audioFile: string;
  wordsPerLine?: number;
  backgroundImage?: string;
}

export const KaraokeVideo: React.FC<KaraokeVideoProps> = ({ words, audioFile, wordsPerLine = 6, backgroundImage }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const timeInSeconds = frame / fps;
  const totalDuration = durationInFrames / fps;

  // Group words into lines for better karaoke effect
  const lines: { words: Word[]; start: number; end: number }[] = [];
  let currentLine: Word[] = [];

  for (let i = 0; i < words.length; i++) {
    currentLine.push(words[i]);
    
    if (currentLine.length >= wordsPerLine || i === words.length - 1) {
      const lineStart = currentLine[0].start;
      const lineEnd = currentLine[currentLine.length - 1].end;
      lines.push({
        words: [...currentLine],
        start: lineStart,
        end: lineEnd
      });
      currentLine = [];
    }
  }

  // Fade in/out effects
  const fadeInDuration = 1; // 1 second fade in
  const fadeOutDuration = 2; // 2 second fade out
  
  const fadeInOpacity = interpolate(
    timeInSeconds,
    [0, fadeInDuration],
    [0, 1],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.cubic),
    }
  );
  
  const fadeOutOpacity = interpolate(
    timeInSeconds,
    [totalDuration - fadeOutDuration, totalDuration],
    [1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.in(Easing.cubic),
    }
  );
  
  const overallOpacity = Math.min(fadeInOpacity, fadeOutOpacity);

  return (
    <AbsoluteFill>
      {/* Background - image or gradient (no fade effects) */}
      {backgroundImage ? (
        <AbsoluteFill>
          <img
            src={staticFile(backgroundImage)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill
          style={{
            background: 'linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
          }}
        />
      )}
      
      {/* Content with fade effects */}
      <AbsoluteFill style={{ opacity: overallOpacity }}>
      
      {/* Audio */}
      <Audio src={staticFile(audioFile)} />
      
      {/* Karaoke text - one line at a time */}
      {lines.map((line, lineIndex) => {
        const isLineActive = timeInSeconds >= line.start && timeInSeconds <= line.end;
        const isLineEntering = timeInSeconds >= line.start && timeInSeconds <= line.start + 0.5;
        const isLineExiting = timeInSeconds >= line.end - 0.5 && timeInSeconds <= line.end;
        
        if (!isLineActive) return null;

        // Line fade in/out effects
        const lineFadeIn = interpolate(
          timeInSeconds,
          [line.start, line.start + 0.5],
          [0, 1],
          {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.out(Easing.cubic),
          }
        );
        
        const lineFadeOut = interpolate(
          timeInSeconds,
          [line.end - 0.5, line.end],
          [1, 0],
          {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.in(Easing.cubic),
          }
        );
        
        const lineOpacity = isLineEntering ? lineFadeIn : isLineExiting ? lineFadeOut : 1;

        return (
          <div
            key={lineIndex}
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: '100%',
              textAlign: 'center',
              fontSize: '56px',
              fontFamily: 'Arial, sans-serif',
              fontWeight: 'bold',
              color: '#666',
              lineHeight: '1.2',
              textShadow: '2px 2px 4px rgba(0,0,0,0.5)',
              opacity: lineOpacity,
            }}
          >
            {line.words.map((word, wordIndex) => {
              const isWordActive = timeInSeconds >= word.start && timeInSeconds <= word.end;
              const isWordHighlighted = timeInSeconds >= word.start && timeInSeconds < word.end;
              
              // Only show text up to the current active word
              if (timeInSeconds < word.start) {
                return null;
              }
              
              // Word fade in effect
              const wordFadeIn = interpolate(
                timeInSeconds,
                [word.start, word.start + 0.1],
                [0, 1],
                {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.out(Easing.cubic),
                }
              );
              
              // Word highlight intensity
              const highlightIntensity = interpolate(
                timeInSeconds,
                [word.start, word.start + (word.end - word.start) * 0.3, word.end],
                [0, 1, 0.7],
                {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.inOut(Easing.cubic),
                }
              );
              
              const wordOpacity = timeInSeconds < word.start ? 0 : wordFadeIn;
              
              return (
                <span
                  key={wordIndex}
                  style={{
                    color: isWordHighlighted ? '#ffffff' : '#cccccc',
                    textShadow: isWordHighlighted 
                      ? `0 0 ${10 + highlightIntensity * 20}px #ffff00, 0 0 ${20 + highlightIntensity * 30}px #ffff00, 0 0 ${30 + highlightIntensity * 40}px #ffff00` 
                      : '2px 2px 4px rgba(0,0,0,0.5)',
                    opacity: wordOpacity,
                    transform: isWordHighlighted ? `scale(${1 + highlightIntensity * 0.1})` : 'scale(1)',
                    transition: 'all 0.1s ease-in-out',
                  }}
                >
                  {word.word}
                </span>
              );
            })}
          </div>
        );
      })}
      
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
