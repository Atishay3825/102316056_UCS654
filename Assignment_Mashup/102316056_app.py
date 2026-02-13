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

# --- CONFIGURATIONs ---
STORAGE_DIR = "permanent_storage"
TEMP_DIR = "work_dir"
os.makedirs(STORAGE_DIR, exist_ok=True)

# --- 1. SMART AUDIO ENGINE ---
def download_videos(singer, n, status_text=None):
    if os.path.exists(TEMP_DIR): 
        try: shutil.rmtree(TEMP_DIR)
        except: pass
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # COOKIE SETUP
    cookie_file = "cookies.txt"
    if "YOUTUBE_COOKIES" in st.secrets:
        with open(cookie_file, "w") as f:
            f.write(st.secrets["YOUTUBE_COOKIES"])

    ydl_opts = {
        'format': 'bestaudio/best', # High-fidelity fallback
        'quiet': False, 
        'default_search': f'ytsearch{n}',
        'outtmpl': f'{TEMP_DIR}/%(id)s.%(ext)s',
        'ignoreerrors': True,
        'nopostprocessor': True,
        'cookiefile': cookie_file if os.path.exists(cookie_file) else None,
        # Bypasses 403 Forbidden using iOS client
        'extractor_args': {'youtube': {'player_client': ['ios']}},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"{singer} official audio"])
    except Exception as e:
        raise Exception(f"Download Engine Failed: {str(e)}")

    gc.collect()
    time.sleep(2)
    
    files_in_dir = os.listdir(TEMP_DIR)
    audio_exts = ('.mp3', '.m4a', '.webm', '.wav', '.ogg', '.flac', '.aac')
    files = [os.path.join(TEMP_DIR, f) for f in files_in_dir 
             if f.lower().endswith(audio_exts) and not f.endswith('.info.json')]
        
    if not files:
        raise Exception("YouTube download failed (403 or no files). Verify Cookies in Secrets.")
        
    return files

def process_audio_files(files, y, auto_mode=False, progress_bar=None, status_text=None):
    mashup = AudioSegment.empty()
    total = len(files)
    
    for i, f in enumerate(files):
        try:
            if status_text: status_text.text(f"🎹 Processing {i+1}/{total}")
            
            # Load and Analyze
            y_audio, sr = librosa.load(f, sr=None)
            rms = librosa.feature.rms(y=y_audio)[0]
            peak_frame = rms.argmax()
            
            if auto_mode:
                # Smart Chorus Detection
                threshold = rms[peak_frame] * 0.7
                start_f = next((idx for idx, val in enumerate(rms) if val > threshold), 0)
                end_f = len(rms) - next((idx for idx, val in enumerate(reversed(rms)) if val > threshold), 0)
                start_ms = int(librosa.frames_to_time(start_f, sr=sr)*1000)
                end_ms = int(librosa.frames_to_time(end_f, sr=sr)*1000)
                if (end_ms - start_ms) > 40000: end_ms = start_ms + 40000
            else:
                # Manual Peak-Centered Cut
                peak_time = librosa.frames_to_time(peak_frame, sr=sr)
                start_ms = max(0, int((peak_time - (y/3)) * 1000))
                end_ms = start_ms + (y * 1000)

            clip = AudioSegment.from_file(f)[start_ms:end_ms].normalize()
            mashup = mashup.append(clip, crossfade=1000) if len(mashup) > 0 else clip
            
            if progress_bar: progress_bar.progress(int(10 + (i / total) * 80))
            gc.collect()
            
        except Exception as e:
            continue

    return mashup

# --- 2. PACKAGING & CACHING ---
def package_and_mail(email_id, mp3_path):
    zip_name = "mashup_result.zip"
    with zipfile.ZipFile(zip_name, 'w') as z:
        z.write(mp3_path, arcname="custom_mashup.mp3")
    
    sender = st.secrets.get("EMAIL_USER")
    pwd = st.secrets.get("EMAIL_PASS")
    
    if sender and pwd:
        try:
            msg = EmailMessage()
            msg['Subject'] = "Your Custom Music Mashup! 🎵"
            msg['From'] = sender
            msg['To'] = email_id
            msg.set_content("Success! Your high-fidelity mashup is attached.")
            with open(zip_name, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_name)
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(sender, pwd)
                smtp.send_message(msg)
            st.success(f"✅ Email sent to {email_id}!")
        except Exception as e:
            st.warning(f"⚠️ Email failed: {str(e)}")
    return zip_name

# --- 3. FRONTEND ---
st.set_page_config(page_title="Studio Mashup", page_icon="🎧")
st.markdown("<style>.stButton>button { width: 100%; border-radius: 25px; height: 3.5em; background: linear-gradient(45deg, #FF4B4B, #FF8E8E); color: white; font-weight: bold; }</style>", unsafe_allow_html=True)

c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/3293/3293810.png", width=100)
with c2: 
    st.title("Pro Mashup Studio")
    st.caption("AI-Powered Energy Analysis")

st.divider()

col_a, col_b = st.columns(2)
with col_a: singer = st.text_input("Singer Name", placeholder="e.g. Sharry Mann")
with col_b: email_id = st.text_input("Your Email", placeholder="yourname@gmail.com")

n_vids = st.slider("Number of Tracks", 10, 40, 20)
use_auto = st.toggle("Smart Auto-Cut (Detect Chorus)", value=True)
y_secs = 0 if use_auto else st.number_input("Seconds per track", 10, 60, 30)

if st.button("🚀 CREATE MASHUP"):
    if not singer or not email_id or "@" not in email_id:
        st.warning("Please provide valid details.")
    else:
        # Caching logic
        cache_name = f"{singer.replace(' ', '_').lower()}_{n_vids}_{'auto' if use_auto else y_secs}.mp3"
        cache_path = os.path.join(STORAGE_DIR, cache_name)
        
        prog = st.progress(0)
        status = st.empty()
        
        try:
            if os.path.exists(cache_path):
                status.text("🎯 Found in storage! Preparing email...")
                output_mp3 = cache_path
            else:
                status.text("⬇️ Downloading tracks...")
                files = download_videos(singer, n_vids, status)
                status.text("🎹 Analyzing audio peaks...")
                mashup = process_audio_files(files, y_secs, use_auto, prog, status)
                output_mp3 = "current_session.mp3"
                mashup.export(output_mp3, format="mp3", bitrate="320k")
                shutil.copy(output_mp3, cache_path)

            zip_res = package_and_mail(email_id, output_mp3)
            prog.progress(100)
            st.balloons()
            with open(zip_res, "rb") as f:
                 st.download_button("📥 Download ZIP", f, file_name="mashup.zip")
        except Exception as e:
            st.error(f"❌ Error: {e}")
