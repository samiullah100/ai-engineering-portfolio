#!/usr/bin/env python3
"""
🎵 Universal Karaoke Video Generator Workflow
============================================

Simple workflow that takes JSON with text timestamps and audio pair to generate karaoke videos.

Usage:
    python3 karaoke_workflow.py config.json

JSON Format:
{
  "audio": "path/to/audio.mp3",
  "words": [
    {"word": " Hello", "start": 0.0, "end": 0.5},
    {"word": " world", "start": 0.5, "end": 1.0}
  ],
  "output": "output_name",
  "words_per_line": 6
}
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any

class KaraokeWorkflow:
    def __init__(self):
        self.project_dir = Path.cwd()
        
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        required_fields = ['audio', 'words']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
        
        return config
    
    def create_remotion_composition(self, words: List[Dict[str, Any]], audio_file: str, output_name: str, words_per_line: int = 6, background_image: str = None):
        """Create Remotion composition with word timestamps."""
        
        # Create the words array string
        words_js = "[\n"
        for word in words:
            words_js += f'            {{"word": "{word["word"]}", "start": {word["start"]}, "end": {word["end"]}}},\n'
        words_js = words_js.rstrip(",\n") + "\n          ]"
        
        # Calculate duration from last word
        duration = max(word["end"] for word in words)
        fps = 30  # Reduced from 60fps for faster rendering (still smooth for karaoke)
        duration_frames = int(duration * fps)
        
        # Read template and replace placeholders
        with open("src/Root_template.tsx", "r") as f:
            root_content = f.read()
        
        # Replace placeholders
        root_content = root_content.replace("DURATION_FRAMES", str(duration_frames))
        root_content = root_content.replace("FPS", str(fps))
        root_content = root_content.replace("WORDS_JS", words_js)
        root_content = root_content.replace("AUDIO_FILE", Path(audio_file).name)
        root_content = root_content.replace("WORDS_PER_LINE", str(words_per_line))
        if background_image:
            root_content = root_content.replace("BACKGROUND_IMAGE", f'"{Path(background_image).name}"')
        else:
            root_content = root_content.replace("BACKGROUND_IMAGE", "null")
        
        # Write Root.tsx
        with open("src/Root.tsx", "w") as f:
            f.write(root_content)
        
        print("✅ Updated Remotion composition with new timestamps")
    
    def copy_audio_file(self, audio_file: str):
        """Copy audio file to public directory."""
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        
        public_dir = Path("public")
        public_dir.mkdir(exist_ok=True)
        
        destination = public_dir / audio_path.name
        import shutil
        shutil.copy2(audio_file, destination)
        print(f"✅ Copied audio file to {destination}")
    
    def copy_background_image(self, background_image: str):
        """Copy background image to public directory."""
        if not background_image:
            return
            
        image_path = Path(background_image)
        if not image_path.exists():
            raise FileNotFoundError(f"Background image not found: {background_image}")
        
        public_dir = Path("public")
        public_dir.mkdir(exist_ok=True)
        
        destination = public_dir / image_path.name
        import shutil
        shutil.copy2(background_image, destination)
        print(f"✅ Copied background image to {destination}")
    
    def render_video(self, output_name: str) -> bool:
        """Render the karaoke video."""
        print("🎬 Rendering karaoke video...")
        try:
            result = subprocess.run(
                ["npx", "remotion", "render", "KaraokeVideo", f"{output_name}.mp4"],
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ Video rendered successfully!")
            print(f"📁 Output: {output_name}.mp4")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error rendering video: {e}")
            print(f"Error output: {e.stderr}")
            return False
    
    def process_config(self, config_file: str):
        """Process a single configuration file."""
        print(f"🎵 Loading configuration from {config_file}")
        config = self.load_config(config_file)
        
        audio_file = config['audio']
        words = config['words']
        output_name = config.get('output', 'karaoke_output')
        words_per_line = config.get('words_per_line', 6)
        background_image = config.get('background_image')
        
        print(f"📄 Found {len(words)} words")
        print(f"🎵 Audio: {audio_file}")
        print(f"📝 Output: {output_name}")
        print(f"📏 Words per line: {words_per_line}")
        if background_image:
            print(f"🖼️ Background image: {background_image}")
        else:
            print("🖼️ Background: Default gradient")
        
        # Copy audio file
        self.copy_audio_file(audio_file)
        
        # Copy background image if provided
        self.copy_background_image(background_image)
        
        # Create composition
        self.create_remotion_composition(words, audio_file, output_name, words_per_line, background_image)
        
        # Render video
        return self.render_video(output_name)

def main():
    if len(sys.argv) != 2:
        print("🎵 Universal Karaoke Video Generator")
        print("=" * 40)
        print("Usage: python3 karaoke_workflow.py <config.json>")
        print("\nExample config.json:")
        print("""
{
  "audio": "path/to/audio.mp3",
  "words": [
    {"word": " Hello", "start": 0.0, "end": 0.5},
    {"word": " world", "start": 0.5, "end": 1.0}
  ],
  "output": "my_karaoke",
  "words_per_line": 6
}
        """)
        sys.exit(1)
    
    config_file = sys.argv[1]
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file not found: {config_file}")
        sys.exit(1)
    
    # Initialize workflow
    workflow = KaraokeWorkflow()
    
    # Process configuration
    success = workflow.process_config(config_file)
    
    if success:
        print("\n🎉 Karaoke video generated successfully!")
    else:
        print("\n❌ Failed to generate karaoke video")
        sys.exit(1)

if __name__ == "__main__":
    main()
