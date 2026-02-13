import streamlit as st
import os
import time
import shutil
import logging
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import librosa
import numpy as np
import zipfile

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_mashup_process(singer, n, y, output_filename, status_text=None):
    # --- CONFIGURATION ---
    TEMP_DIR = "temp_work_dir_" + str(int(time.time()))
    
    # Clean/Create Temp Dir
    if os.path.exists(TEMP_DIR): 
        try: shutil.rmtree(TEMP_DIR)
        except: pass
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    try:
        if status_text: status_text.text(f"🎵 Starting Mashup for: {singer}")
        
        # 1. DOWNLOAD
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': False,
            'default_search': f'ytsearch{n}',
            'outtmpl': f'{TEMP_DIR}/%(id)s.%(ext)s',
            'ignoreerrors': True,
            'nopostprocessor': True,
            'socket_timeout': 30,
            'retries': 10,
            'source_address': '0.0.0.0',
            # Use 'android' client for better success rate
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }

        if status_text: status_text.text("⬇️ Downloading audio streams from YouTube...")
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
            raise Exception("Download failed. No audio files found (IP might be blocked).")

        if status_text: status_text.text(f"✅ Found {len(files)} tracks. Processing...")
        
        mashup = AudioSegment.empty()
        
        # 3. CUT & MERGE
        processed_count = 0
        progress_bar = st.progress(0)
        
        for i, f in enumerate(files):
            try:
                # Librosa load (robust)
                y_audio, sr = librosa.load(f, sr=None)
                
                # Calculate start/end
                start_ms = 0
                end_ms = int(y * 1000)
                
                # Pydub load
                clip = AudioSegment.from_file(f)
                
                # Validation
                if len(clip) < end_ms:
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
                progress_bar.progress(int((i / len(files)) * 100))
                
            except Exception as e:
                logging.warning(f"⚠️ Error processing file {f}: {e}")
                continue

        if processed_count == 0:
            raise Exception("Could not process any audio tracks successfully.")

        # 4. EXPORT
        if status_text: status_text.text(f"💾 Exporting mashup to {output_filename}...")
        mashup.export(output_filename, format="mp3", bitrate="320k")
        progress_bar.progress(100)
        
        return output_filename

    finally:
        # Cleanup
        try:
            shutil.rmtree(TEMP_DIR)
        except: pass

# --- STREAMLIT UI ---
st.set_page_config(page_title="Mashup Generator", page_icon="�")

st.title("🎵 MP3 Mashup Generator")
st.markdown("Convert your CLI script into a Web App instantly.")

with st.form("mashup_form"):
    singer = st.text_input("Singer Name", "Sharry Mann")
    n_vids = st.number_input("Number of Videos", min_value=1, max_value=50, value=10)
    y_duration = st.number_input("Duration (seconds)", min_value=5, max_value=60, value=20)
    output_file = st.text_input("Output Filename", "mashup.mp3")
    
    submitted = st.form_submit_button("Generate Mashup")

if submitted:
    if not singer:
        st.error("Please enter a singer name.")
    else:
        status = st.empty()
        try:
            if not output_file.endswith('.mp3'): output_file += ".mp3"
            
            result_path = run_mashup_process(singer, n_vids, y_duration, output_file, status)
            
            status.success(f"🎉 Mashup Created: {result_path}")
            
            with open(result_path, "rb") as f:
                st.download_button(
                    label="📥 Download Mashup",
                    data=f,
                    file_name=output_file,
                    mime="audio/mpeg"
                )
        except Exception as e:
            st.error(f"Error: {e}")