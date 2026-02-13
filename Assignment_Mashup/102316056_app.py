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
def run_mashup_process(singer, n, y, auto_mode=False, progress_bar=None):
    clean_name = singer.replace(" ", "_").lower()
    cache_filename = f"{clean_name}_{n}_{'auto' if auto_mode else y}.mp3"
    cache_path = os.path.join(STORAGE_DIR, cache_filename)

    # CHECK CACHE
    if os.path.exists(cache_path):
        st.toast("🎯 Serving from permanent storage...", icon="🚀")
        return cache_path

    # CLEANUP & PREP
    if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': f'ytsearch{n}',
        'outtmpl': f'{TEMP_DIR}/%(id)s.%(ext)s',
        'ignoreerrors': True,
        'nopostprocessor': True,
        'socket_timeout': 30,
        'retries': 10,
        'source_address': '0.0.0.0', # Force IPv4
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    # DOWNLOAD
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"{singer} official audio"])
    
    # Wait for FFmpeg to fully release files
    gc.collect()
    time.sleep(5)

    # Find audio files with retry logic (supports all formats)
    audio_extensions = ('.mp3', '.m4a', '.webm', '.wav', '.ogg', '.flac', '.aac')
    files = []
    for attempt in range(3):
        files = [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) 
                 if f.endswith(audio_extensions) and not f.endswith('.info.json')]
        if files:
            break
        gc.collect()
        time.sleep(2)
    
    if not files: 
        raise Exception("No audio tracks found. Try another artist.")

    mashup = AudioSegment.empty()
    
    # PROCESSING LOOP
    for i, f in enumerate(files):
        audio_clip = None
        try:
            # Wait before accessing file to ensure it's released
            time.sleep(2)
            
            # Retry logic for file access
            y_audio = None
            for retry in range(3):
                try:
                    y_audio, sr = librosa.load(f, sr=None)
                    break
                except Exception:
                    gc.collect()
                    time.sleep(1)
            
            if y_audio is None:
                continue
                
            rms = librosa.feature.rms(y=y_audio)[0]
            
            if auto_mode:
                # Detect Chorus: Frames > 70% of peak energy
                peak_frame = rms.argmax()
                threshold = rms[peak_frame] * 0.7
                start_f = next(idx for idx, val in enumerate(rms) if val > threshold)
                end_f = len(rms) - next(idx for idx, val in enumerate(reversed(rms)) if val > threshold)
                start_ms, end_ms = int(librosa.frames_to_time(start_f, sr=sr)*1000), int(librosa.frames_to_time(end_f, sr=sr)*1000)
            else:
                # Peak-Centered Manual Cut
                peak_time = librosa.frames_to_time(rms.argmax(), sr=sr)
                start_ms = max(0, int((peak_time - (y/3)) * 1000))
                end_ms = start_ms + (y * 1000)

            # CLIP & CROSSFADE (Pydub)
            clip = AudioSegment.from_file(f)[start_ms:end_ms].normalize()
            mashup = mashup.append(clip, crossfade=1500) if len(mashup) > 0 else clip
            
            if progress_bar: progress_bar.progress(int(10 + (i / len(files)) * 80))
            
            audio_clip = None
            y_audio = None
            gc.collect()
        except Exception as e: 
            audio_clip = None
            y_audio = None
            gc.collect()
            continue

    if len(mashup) == 0:
        raise Exception("Could not process any audio files. Please try again.")

    # EXPORT & CACHE
    output_mp3 = "current_session_mashup.mp3"
    mashup.export(output_mp3, format="mp3", bitrate="320k")
    
    # Wait and ensure file is written
    time.sleep(2)
    gc.collect()
    
    # Copy to cache
    if os.path.exists(output_mp3):
        shutil.copy(output_mp3, cache_path)
    
    # Clean up temp directory
    time.sleep(1)
    try:
        shutil.rmtree(TEMP_DIR)
    except:
        pass
    
    return output_mp3

# --- 2. ANONYMIZED PACKAGING & EMAIL ---
def package_and_mail(email_id, mp3_path):
    zip_name = "mashup_result.zip"
    
    # Check file size before creating zip
    file_size = os.path.getsize(mp3_path) / (1024 * 1024)  # Size in MB
    
    # If file is too large (>20MB), compress it
    if file_size > 20:
        st.warning(f"⚠️ Mashup is {file_size:.1f}MB - compressing for email...")
        # Re-export at lower bitrate
        audio = AudioSegment.from_file(mp3_path)
        compressed_path = "mashup_compressed.mp3"
        audio.export(compressed_path, format="mp3", bitrate="192k")
        mp3_path = compressed_path
        file_size = os.path.getsize(mp3_path) / (1024 * 1024)
    
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
            msg.set_content("Success! Your high-fidelity music mashup has been generated. Enjoy!")
            
            with open(zip_name, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_name)
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(sender, pwd)
                smtp.send_message(msg)
            st.success(f"✅ Email sent to {email_id}!")
            
        except smtplib.SMTPException as e:
            if "size" in str(e).lower():
                st.warning("📦 File is too large for email. Saved locally as 'mashup_result.zip'")
            else:
                st.warning(f"⚠️ Could not send email: {str(e)}. File saved as 'mashup_result.zip'")
        except Exception as e:
            st.warning(f"⚠️ Email delivery failed: {str(e)}. Your mashup is saved as 'mashup_result.zip'")
    else:
        st.info("📧 Email not configured - File saved as 'mashup_result.zip'")
    
    return zip_name

# --- 3. EYE-CATCHY FRONTEND ---
st.set_page_config(page_title="Studio Mashup", page_icon="🎧")

# Custom UI Styling
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 25px; height: 3.5em; background: linear-gradient(45deg, #FF4B4B, #FF8E8E); color: white; border: none; font-weight: bold; }
    .stProgress > div > div > div > div { background-color: #FF4B4B; }
    </style>
    """, unsafe_allow_html=True)

# Header
c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/3293/3293810.png", width=100)
with c2: 
    st.title("Pro Mashup Studio")
    st.caption("AI-Powered Energy Analysis • High Fidelity 320kbps • Instant Delivery")

st.divider()

# Input Form
with st.container():
    st.subheader("🎨 Step 1: Artist Selection")
    col_a, col_b = st.columns(2)
    with col_a: singer = st.text_input("Singer Name", placeholder="e.g. Sharry Mann")
    with col_b: email_id = st.text_input("Your Email", placeholder="yourname@gmail.com")

    st.subheader("⚙️ Step 2: Engine Configuration")
    n_vids = st.slider("How many tracks to blend?", 10, 40, 20)
    
    use_auto = st.toggle("Smart Auto-Cut (Detect Full Chorus)", value=True)
    if not use_auto:
        y_secs = st.number_input("Seconds per track", 10, 60, 30)
    else:
        y_secs = 0
        st.info("✨ AI will naturally find the drop and chorus of each track.")

st.divider()

if st.button("🚀 CREATE MASHUP"):
    if not singer or not email_id or "@" not in email_id:
        st.warning("Please fill in all details correctly.")
    else:
        prog = st.progress(0)
        status = st.empty()
        try:
            status.text("📂 Initializing Audio Engine...")
            final_mp3 = run_mashup_process(singer, n_vids, y_secs, use_auto, prog)
            
            status.text("📧 Packaging and Mailing...")
            zip_res = package_and_mail(email_id, final_mp3)
            
            prog.progress(100)
            st.success(f"Successfully sent to {email_id}!")
            st.balloons()
        except Exception as e:
            st.error(f"Error: {e}")
