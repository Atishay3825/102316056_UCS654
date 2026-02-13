import streamlit as st
import os
import shutil
import zipfile
import smtplib
import time
import gc
import librosa
import numpy as np
from email.message import EmailMessage
from yt_dlp import YoutubeDL
from pydub import AudioSegment

# --- CONFIGURATION & PATHS ---
# FFmpeg is handled by packages.txt on Streamlit Cloud
STORAGE_DIR = "permanent_storage"
TEMP_DIR = "work_dir"
os.makedirs(STORAGE_DIR, exist_ok=True)

# --- 1. SMART AUDIO ENGINE ---
def download_videos(singer, n):
    if os.path.exists(TEMP_DIR): 
        try: shutil.rmtree(TEMP_DIR)
        except: pass
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # COOKIES SETUP (Bypass 403)
    cookie_file = "cookies.txt"
    if "YOUTUBE_COOKIES" in st.secrets:
        with open(cookie_file, "w") as f:
            f.write(st.secrets["YOUTUBE_COOKIES"])
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'default_search': f'ytsearch{n}',
        'outtmpl': f'{TEMP_DIR}/%(id)s.%(ext)s',
        'ignoreerrors': True,
        'nopostprocessor': True,
        'socket_timeout': 30,
        'retries': 10,
        # Use cookies if available
        'cookiefile': cookie_file if os.path.exists(cookie_file) else None,
        # Fallback to Android client
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"{singer} official audio"])
    except Exception as e:
        raise Exception(f"Download Failed (YouTube blocked IP?): {str(e)}")

    # Wait for file release
    gc.collect()
    time.sleep(2)
    
    audio_extensions = ('.mp3', '.m4a', '.webm', '.wav', '.ogg', '.flac', '.aac')
    files = []
    for _ in range(3):
        files = [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) 
                 if f.endswith(audio_extensions) and not f.endswith('.info.json')]
        if files: break
        time.sleep(1)
        
    if not files:
        raise Exception("No audio tracks found after download.")
    return files

def process_audio_files(files, y, auto_mode=False, progress_bar=None):
    mashup = AudioSegment.empty()
    
    # PROCESSING LOOP
    for i, f in enumerate(files):
        try:
            # Librosa Load
            y_audio, sr = librosa.load(f, sr=None)
            
            # Logic: Auto or Manual
            start_ms = 0
            end_ms = 0
            
            if auto_mode:
                 # Detect Chorus
                rms = librosa.feature.rms(y=y_audio)[0]
                peak_frame = rms.argmax()
                threshold = rms[peak_frame] * 0.7
                start_f = next((idx for idx, val in enumerate(rms) if val > threshold), 0)
                end_f = len(rms) - next((idx for idx, val in enumerate(reversed(rms)) if val > threshold), 0)
                start_ms = int(librosa.frames_to_time(start_f, sr=sr)*1000)
                end_ms = int(librosa.frames_to_time(end_f, sr=sr)*1000)
                
                # Limit to 30s max for auto to avoid long clips
                if (end_ms - start_ms) > 40000: end_ms = start_ms + 40000
            else:
                # Peak-Centered Manual Cut
                rms = librosa.feature.rms(y=y_audio)[0]
                peak_time = librosa.frames_to_time(rms.argmax(), sr=sr)
                start_ms = max(0, int((peak_time - (y/3)) * 1000))
                end_ms = start_ms + (y * 1000)

            # CLIP & CROSSFADE (Pydub)
            clip = AudioSegment.from_file(f)[start_ms:end_ms].normalize()
            mashup = mashup.append(clip, crossfade=1000) if len(mashup) > 0 else clip
            
            if progress_bar: progress_bar.progress(int(10 + (i / len(files)) * 80))
            
            # Cleanup loops
            del y_audio, rms
            gc.collect()
            
        except Exception as e: 
            print(f"Skipping file {f}: {e}")
            continue

    if len(mashup) == 0:
        raise Exception("Could not process any audio files.")

    return mashup

# --- 2. ANONYMIZED PACKAGING & EMAIL ---
def package_and_mail(email_id, mp3_path):
    zip_name = "mashup_result.zip"
    
    # Check file size
    file_size = os.path.getsize(mp3_path) / (1024 * 1024) 
    
    # Compress if needed
    if file_size > 20:
        st.warning(f"⚠️ Mashup is {file_size:.1f}MB - compressing...")
        audio = AudioSegment.from_file(mp3_path)
        compressed_path = "mashup_compressed.mp3"
        audio.export(compressed_path, format="mp3", bitrate="192k")
        mp3_path = compressed_path
    
    with zipfile.ZipFile(zip_name, 'w') as z:
        z.write(mp3_path, arcname="custom_mashup.mp3")
    
    sender = st.secrets.get("EMAIL_USER")
    pwd = st.secrets.get("EMAIL_PASS")
    
    if sender and pwd:
        try:
            msg = EmailMessage()
            msg['Subject'] = "Your Custom Music Mashup is Ready! 🎵"
            msg['From'] = sender
            msg['To'] = email_id
            msg.set_content("Here is your generated mashup. Enjoy!")
            
            with open(zip_name, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_name)
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(sender, pwd)
                smtp.send_message(msg)
            st.success(f"✅ Email sent to {email_id}!")
            
        except Exception as e:
            st.warning(f"⚠️ Email failed: {str(e)}. File saved locally.")
    else:
        st.info("📧 Email not configured - File saved locally.")
    
    return zip_name

# --- 3. EYE-CATCHY FRONTEND ---
st.set_page_config(page_title="Studio Mashup", page_icon="🎧")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 25px; height: 3.5em; background: linear-gradient(45deg, #FF4B4B, #FF8E8E); color: white; border: none; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/3293/3293810.png", width=100)
with c2: 
    st.title("Pro Mashup Studio")
    st.caption("AI-Powered Energy Analysis • High Fidelity • Instant Delivery")

st.divider()

# TABS FOR SOURCE
tab1, tab2 = st.tabs(["🎥 YouTube Source", "📂 Upload Audio"])

singer = None
n_vids = 10
uploaded_files = None

with tab1:
    singer = st.text_input("Singer Name", placeholder="e.g. Sharry Mann")
    n_vids = st.slider("Number of Tracks", 10, 40, 20)
    st.info("ℹ️ If YouTube download fails (403 Error), use the 'Upload Audio' tab!")

with tab2:
    uploaded_files = st.file_uploader("Upload MP3/WAV files", accept_multiple_files=True)

st.subheader("⚙️ Configuration")
email_id = st.text_input("Your Email", placeholder="yourname@gmail.com")
use_auto = st.toggle("Smart Auto-Cut (Detect Chorus)", value=True)
y_secs = 0 if use_auto else st.number_input("Seconds per track", 10, 60, 30)

st.divider()

if st.button("🚀 CREATE MASHUP"):
    if not email_id or "@" not in email_id:
        st.warning("Please enter a valid email.")
    else:
        prog = st.progress(0)
        status = st.empty()
        try:
            final_files = []
            
            # 1. GET FILES
            if uploaded_files:
                status.text("📂 Processing Uploaded Files...")
                if os.path.exists(TEMP_DIR): 
                    try: shutil.rmtree(TEMP_DIR)
                    except: pass
                os.makedirs(TEMP_DIR, exist_ok=True)
                
                for uf in uploaded_files:
                    path = os.path.join(TEMP_DIR, uf.name)
                    with open(path, "wb") as f:
                        f.write(uf.getbuffer())
                    final_files.append(path)
            elif singer:
                status.text("⬇️ Downloading from YouTube (This may take time)...")
                final_files = download_videos(singer, n_vids)
            else:
                st.error("Please provide a Singer Name OR Upload files.")
                st.stop()
                
            # 2. PROCESS
            status.text("🎹 Mixing and Mastering...")
            mashup = process_audio_files(final_files, y_secs, use_auto, prog)
            
            # 3. EXPORT
            output_mp3 = "current_session_mashup.mp3"
            mashup.export(output_mp3, format="mp3", bitrate="320k")
            
            # 4. PACKAGE
            status.text("📧 Sending...")
            zip_res = package_and_mail(email_id, output_mp3)
            
            prog.progress(100)
            st.success("Success! Check your email or download below.")
            st.balloons()
            
            # Download Button
            with open(zip_res, "rb") as f:
                 st.download_button("📥 Download ZIP", f, file_name="mashup.zip")
                 
        except Exception as e:
            st.error(f"Error: {e}")
