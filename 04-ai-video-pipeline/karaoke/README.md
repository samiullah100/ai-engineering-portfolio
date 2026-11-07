# 🎵 Universal Karaoke Video Generator

A simple workflow that takes JSON with text timestamps and audio pair to generate karaoke videos using Remotion.

## 🚀 Quick Start

### 1. Create JSON Configuration
```json
{
  "audio": "your_audio.mp3",
  "words": [
    {"word": " Hello", "start": 0.0, "end": 0.5},
    {"word": " world", "start": 0.5, "end": 1.0}
  ],
  "output": "my_karaoke",
  "words_per_line": 6,
  "background_image": "your_background.png"
}
```

### 2. Run Workflow
```bash
python3 karaoke_workflow.py config.json
```

### 3. Get Your Video
Output: `my_karaoke.mp4` with word-by-word highlighting!

## 📋 Configuration

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `audio` | ✅ | Path to audio file | `"speech.mp3"` |
| `words` | ✅ | Array of word objects | `[{"word": " Hello", "start": 0.0, "end": 0.5}]` |
| `output` | ❌ | Output video name | `"my_karaoke"` |
| `words_per_line` | ❌ | Words per line (default: 6) | `6` |
| `background_image` | ❌ | Background image file | `"background.png"` |

## 🎬 Features

- **Word-by-word highlighting** synchronized with audio
- **Single line display** (one line at a time)
- **Customizable words per line**
- **Background images** or beautiful gradient background
- **Progress indicator**
- **High quality** (60fps, H.264)

## 🎯 Perfect For

- Educational content
- Religious texts
- Marketing videos
- Language learning
- Any audio with word timestamps

## 📁 Project Structure

```
remotion-karaoke/
├── karaoke_workflow.py      # Main workflow script
├── src/
│   ├── Root.tsx            # Generated dynamically
│   └── KaraokeVideo.tsx    # Karaoke component
├── public/                 # Audio files
└── output.mp4             # Generated video
```

## 🔧 Requirements

- Python 3.7+
- Node.js and npm
- Remotion dependencies (installed via `npm install`)

## 🚨 Setup

```bash
npm install
```

That's it! The workflow is ready to use. 🎉