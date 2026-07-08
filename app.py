import streamlit as st
import os
import re
import shutil
import tempfile
import asyncio
import requests
import google.generativeai as genai
import edge_tts  # Moved to top so cloud platforms know to install it
import moviepy.video.fx.all as vfx  # Added to fix the broken loop bug
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

# --- 1. SECURE CREDENTIAL CONFIGURATION ---
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

MAX_WORDS = 1400

st.set_page_config(page_title="AI B-Roll Creator Pro", layout="wide")
st.title("🎬 High-Volume AI B-Roll Web Workspace")
st.write("Professional widescreen workflow designed for laptop video production.")

# --- 2. UNDER-THE-HOOD UTILITIES ---
def segment_text_by_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = []
    for i in range(0, len(sentences), 3):
        chunk = " ".join(sentences[i:i+3])
        if chunk:
            paragraphs.append(chunk)
    return paragraphs

def query_gemini_for_tags(text):
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"Analyze this script segment and provide exactly two simple, descriptive keywords separated by a comma for locating realistic B-roll stock video footage. Return ONLY the keywords, no numbers, no explanation: '{text}'"
        response = model.generate_content(prompt)
        return response.text.strip().split(',')
    except Exception:
        return ["cinematic", "scenery"]

def extract_broll_download_url(tags):
    headers = {"Authorization": PEXELS_KEY}
    for tag in tags:
        try:
            url = f"https://api.pexels.com/v1/videos/search?query={tag.strip()}&per_page=1"
            res = requests.get(url, headers=headers, timeout=10).json()
            if res.get('videos'):
                video_files = res['videos'][0]['video_files']
                hd_streams = [f['link'] for f in video_files if f['quality'] == 'hd' and f['width'] > f['height']]
                return hd_streams[0] if hd_streams else video_files[0]['link']
        except:
            continue
            
    for tag in tags:
        try:
            url = f"https://pixabay.com/api/videos/?key={PIXABAY_KEY}&q={tag.strip()}&per_page=3&orientation=horizontal"
            res = requests.get(url, timeout=10).json()
            if res.get('hits'):
                videos = res['hits'][0]['videos']
                best_fit = videos.get('medium') or videos.get('small')
                return best_fit['url']
        except:
            continue
            
    return "https://player.vimeo.com/external/371433846.sd.mp4?s=236da2f3c0227ee0e980562e6e1694f4b16757d5&profile_id=139&oauth2_token_id=57447761"

async def generate_narration(text, save_path):
    communication_channel = edge_tts.Communicate(text, "en-US-JennyNeural", rate="+0%")
    await communication_channel.save(save_path)

# --- 3. LAPTOP WEB PANEL WORKSPACE UI ---
col1, col2 = st.columns([2, 1])
with col1:
    user_script = st.text_area("📋 Paste Production Script Here:", height=400, placeholder="Type or paste up to 1,400 words...")
    word_count = len(user_script.split())

with col2:
    st.subheader("⚙️ Video Properties")
    bg_music = st.checkbox("Include Looping Ambient Background Music", value=False)
    enable_captions = st.checkbox("Generate High-Contrast Subtitles", value=True)
    
    if word_count > 0:
        runtime_estimate = word_count / 145
        st.metric(label="Current Script Volume", value=f"{word_count} words")
        st.metric(label="Estimated Video Duration", value=f"{runtime_estimate:.1f} mins")
    
    if word_count > MAX_WORDS:
        st.error(f"🚨 Target boundary overflow! Remove {word_count - MAX_WORDS} words to run safely on free resources.")
        trigger_render = st.button("🚀 Render Master Video File", disabled=True)
    else:
        trigger_render = st.button("🚀 Render Master Video File", disabled=False)

# --- 4. DATA TIMELINE PIPELINE ASSEMBLY ---
if trigger_render and word_count > 0:
    session_workspace = tempfile.mkdtemp()
    final_output_path = os.path.join(session_workspace, "compiled_master.mp4")
    render_status = st.progress(0)
    system_log = st.empty()
    
    try:
        script_blocks = segment_text_by_sentences(user_script)
        timeline_segments = []
        
        for index, block in enumerate(script_blocks):
            system_log.text(f"Processing Clip Sequence {index + 1} of {len(script_blocks)}...")
            audio_segment_path = os.path.join(session_workspace, f"audio_{index}.mp3")
            asyncio.run(generate_narration(block, audio_segment_path))
            audio_layer = AudioFileClip(audio_segment_path)
            audio_duration = audio_layer.duration
            search_tags = query_gemini_for_tags(block)
            raw_video_url = extract_broll_download_url(search_tags)
            
            local_clip_path = os.path.join(session_workspace, f"raw_clip_{index}.mp4")
            with requests.get(raw_video_url, stream=True) as network_stream:
                with open(local_clip_path, 'wb') as local_file:
                    shutil.copyfileobj(network_stream.raw, local_file)
            
            video_layer = VideoFileClip(local_clip_path).resize((1280, 720))
            if video_layer.duration < audio_duration:
                # FIXED: Using the bulletproof vfx.loop method instead of video_layer.loop
                video_layer = vfx.loop(video_layer, duration=audio_duration)
            else:
                video_layer = video_layer.subclip(0, audio_duration)
                
            video_layer = video_layer.set_audio(audio_layer)
            timeline_segments.append(video_layer)
            render_status.progress(int(((index + 1) / len(script_blocks)) * 85))
            
        system_log.text("🎬 Stitching final master video track together...")
        stitched_master = concatenate_videoclips(timeline_segments, method="compose")
        if stitched_master.duration > 600:
            stitched_master = stitched_master.subclip(0, 600)
            
        stitched_master.write_videofile(final_output_path, fps=24, codec="libx264", audio_codec="aac", bitrate="1500k")
        render_status.progress(100)
        system_log.text("🎉 Render Complete! Your timeline file is packaged and ready.")
        
        with open(final_output_path, "rb") as final_file:
            download_payload = final_file.read()
        st.download_button(label="📥 Save Finished .MP4 to Laptop/PC Storage", data=download_payload, file_name="ai_generated_broll.mp4", mime="video/mp4")
        
    except Exception as server_error:
        st.error(f"Pipeline anomaly encountered: {str(server_error)}")
    finally:
        shutil.rmtree(session_workspace, ignore_errors=True)
        st.toast("🧹 Memory cleared! Server storage footprint reset to 0%.")
