import streamlit as st
import os
import shutil
import zipfile
import smtplib
from email.message import EmailMessage
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import librosa

# --- 1. Audio Processing Engine ---
def get_musical_boundaries(file_path):
    """Finds actual music start/end using RMS Energy Analysis."""
    try:
        y, sr = librosa.load(file_path, sr=None)
        intervals = librosa.effects.split(y, top_db=25)
        return int((intervals[0][0]/sr)*1000), int((intervals[-1][1]/sr)*1000)
    except:
        return 0, -1

def run_mashup_process(singer, n, y):
    temp_dir = "work_dir"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': f'ytsearch{n}',
        'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"{singer} official audio"])
    
    files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith(".mp3")]
    mashup = AudioSegment.empty()
    
    for f in files:
        start, end = get_musical_boundaries(f)
        # Apply No-Middle-Cut logic
        clip = AudioSegment.from_file(f).normalize()[start:end]
        clip = clip[:y*1000] # Limit to user's duration
        mashup = mashup.append(clip, crossfade=1500) if len(mashup) > 0 else clip
    
    output_mp3 = f"mashup_102316056.mp3"
    mashup.export(output_mp3, format="mp3", bitrate="320k")
    shutil.rmtree(temp_dir)
    return output_mp3

# --- 2. Email & Packaging Logic ---
def package_and_mail(email_id, mp3_path):
    zip_name = "mashup_result.zip"
    with zipfile.ZipFile(zip_name, 'w') as z:
        z.write(mp3_path)
    
    # Securely retrieve credentials from Streamlit Secrets
    SENDER_EMAIL = st.secrets["EMAIL_USER"]
    SENDER_PASS = st.secrets["EMAIL_PASS"]
    
    msg = EmailMessage()
    msg['Subject'] = "Your AI Mashup is Ready! 🎵"
    msg['From'] = SENDER_EMAIL
    msg['To'] = email_id
    msg.set_content(f"Success! Find your high-fidelity mashup (Roll No: 102316056) attached.")
    
    with open(zip_name, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_name)
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_PASS)
        smtp.send_message(msg)
    return zip_name

# --- 3. Streamlit UI (Frontend) ---
st.set_page_config(page_title="Mashup Web Service", page_icon="🎧")
st.title("Program 2: Mashup Web Service")
st.markdown("---")

with st.container():
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("https://cdn-icons-png.flaticon.com/512/3293/3293810.png", width=100)
    with col2:
        st.info("Input the details below to receive your customized ZIP mashup via email.")

# Form Implementation based on requirement image
with st.form("mashup_form"):
    singer = st.text_input("Singer Name", placeholder="Enter Artist")
    n_vids = st.number_input("# of videos", min_value=10, step=1, value=20)
    duration = st.number_input("duration of each video (sec)", min_value=20, step=1, value=30)
    email_id = st.text_input("Email Id", placeholder="psrana@gmail.com")
    
    submitted = st.form_submit_button("Submit")

if submitted:
    if not singer or not email_id or "@" not in email_id:
        st.error("Please provide all valid inputs and a correct Email Id.")
    else:
        try:
            with st.spinner(f"Creating mashup for {singer}... Please wait."):
                # Execution
                result_mp3 = run_mashup_process(singer, n_vids, duration)
                result_zip = package_and_mail(email_id, result_mp3)
                
                st.success(f"Success! The result has been zipped and emailed to {email_id}.")
                st.balloons()
                
                # Cleanup server-side files
                os.remove(result_mp3)
                os.remove(result_zip)
        except Exception as e:
            st.error(f"Error during execution: {e}")