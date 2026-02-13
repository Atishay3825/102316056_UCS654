import sys
import os
import time
import shutil
import logging
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import librosa
import numpy as np

# Setup basic logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_mashup_process(singer, n, y, output_filename):
    # --- CONFIGURATION ---
    TEMP_DIR = "temp_work_dir_" + str(int(time.time()))
    
    # Clean/Create Temp Dir
    if os.path.exists(TEMP_DIR): 
        try: shutil.rmtree(TEMP_DIR)
        except: pass
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    try:
        logging.info(f"🎵 Starting Mashup ID: {singer} | Videos: {n} | Cut: {y}s")
        
        # 1. DOWNLOAD
        ydl_opts = {
            'format': 'bestaudio',
            'quiet': True,
            'default_search': f'ytsearch{n}',
            'outtmpl': f'{TEMP_DIR}/%(id)s.%(ext)s',
            'ignoreerrors': True,
            'nopostprocessor': True, # Avoid FFmpeg locks initially
            'socket_timeout': 30,
            'retries': 5,
        }

        logging.info("⬇️ Downloading audio streams...")
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"{singer} official audio"])
        
        # 2. PROCESS FILES
        audio_extensions = ('.mp3', '.m4a', '.webm', '.wav', '.ogg', '.flac', '.aac')
        files = []
        
        # Retry logic to find files
        for _ in range(3):
            files = [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) 
                     if f.endswith(audio_extensions) and not f.endswith('.info.json')]
            if files: break
            time.sleep(1)
            
        if not files:
            logging.error("❌ No audio files found downloaded.")
            raise Exception("Download failed or returned no valid files.")

        logging.info(f"✅ Found {len(files)} tracks. Processing...")
        
        mashup = AudioSegment.empty()
        
        # 3. CUT & MERGE
        processed_count = 0
        for i, f in enumerate(files):
            try:
                # Librosa load (robust)
                y_audio, sr = librosa.load(f, sr=None)
                
                # Trim silence
                y_audio, _ = librosa.effects.trim(y_audio)
                
                # Calculate start/end (Standard cut)
                # Since CLI arguments specify specific duration Y, we use that strictly or logic?
                # Assignment says: "Cut first Y sec audios"
                # So we take 0 to Y.
                start_ms = 0
                end_ms = int(y * 1000)
                
                # Pydub load
                clip = AudioSegment.from_file(f)
                
                # Validation
                if len(clip) < end_ms:
                    logging.warning(f"⚠️ Track {i+1} shorter than {y}s, skipping.")
                    continue
                    
                # Cut
                clip = clip[start_ms:end_ms]
                
                # Normalize
                clip = clip.normalize()
                
                # Append with Crossfade
                if len(mashup) > 0:
                    mashup = mashup.append(clip, crossfade=1000)
                else:
                    mashup = clip
                
                processed_count += 1
                logging.info(f"✂️ Processed track {i+1}/{len(files)}")
                
            except Exception as e:
                logging.warning(f"⚠️ Error processing file {f}: {e}")
                continue

        if processed_count == 0:
            raise Exception("Could not process any audio tracks successfully.")

        # 4. EXPORT
        logging.info(f"💾 Exporting mashup to {output_filename}...")
        mashup.export(output_filename, format="mp3", bitrate="320k")
        
        logging.info("✨ Mashup Created Successfully!")

    finally:
        # Cleanup
        logging.info("🧹 Cleaning up temp files...")
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception as e:
            logging.warning(f"Cleanup warning: {e}")

def main():
    if len(sys.argv) != 5:
        print("Usage: python <program.py> <SingerName> <NumberOfVideos> <AudioDuration> <OutputFileName>")
        sys.exit(1)

    singer = sys.argv[1]
    try:
        n = int(sys.argv[2])
        y = int(sys.argv[3])
    except:
        print("Error: N and Y must be integers")
        sys.exit(1)
    output = sys.argv[4]
    
    if not output.endswith('.mp3'):
        output += ".mp3"

    try:
        run_mashup_process(singer, n, y, output)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
