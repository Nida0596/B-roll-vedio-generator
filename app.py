import gradio as gr
import os
import re
import shutil
import tempfile
import requests
import google.generativeai as genai
from gtts import gTTS
import ffmpeg

# --- 1. SECURE CREDENTIAL CONFIGURATION ---
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

MAX_WORDS = 1400

# --- 2. UTILITIES ---
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
        model = genai.GenerativeModel('gemini-1.5-flash') # gemini-pro کی جگہ flash free ہے
        prompt = f"Analyze this script segment and provide exactly two simple keywords separated by a comma: '{text}'"
        response = model.generate_content(prompt)
        return response.text.strip().split(',')
    except Exception:
        return ["cinematic", "scenery"]

def extract_broll_download_url(tags):
    headers = {"Authorization": PEXELS_KEY}
    for tag in tags:
        try:
            url = f"https://api.pexels.com/videos/search?query={tag.strip()}&per_page=1"
            res = requests.get(url, headers=headers, timeout=10).json()
            if res.get('videos'):
                return res['videos'][0]['video_files'][0]['link']
        except:
            continue
    return "https://cdn.pixabay.com/vimeo/123456.mp4" # fallback

def generate_narration(text, save_path):
    tts = gTTS(text=text, lang='en') # edge-tts کی جگہ gTTS
    tts.save(save_path)

def merge_with_ffmpeg(video_path, audio_path, output_path):
    video = ffmpeg.input(video_path)
    audio = ffmpeg.input(audio_path)
    ffmpeg.output(video, audio, output_path, vcodec='libx264', acodec='aac', shortest=None).run(overwrite_output=True)

# --- 3. MAIN FUNCTION ---
def generate_video(script, language):
    if len(script.split()) > MAX_WORDS:
        return "Error: Max 1400 words", None

    session_workspace = tempfile.mkdtemp()
    final_output_path = os.path.join(session_workspace, "compiled_master.mp4")
    timeline_segments = []

    script_blocks = segment_text_by_sentences(script)

    for index, block in enumerate(script_blocks):
        audio_path = os.path.join(session_workspace, f"audio_{index}.mp3")
        video_path = os.path.join(session_workspace, f"video_{index}.mp4")
        segment_path = os.path.join(session_workspace, f"segment_{index}.mp4")

        generate_narration(block, audio_path)
        search_tags = query_gemini_for_tags(block)
        video_url = extract_broll_download_url(search_tags)

        with requests.get(video_url, stream=True) as r:
            with open(video_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        merge_with_ffmpeg(video_path, audio_path, segment_path)
        timeline_segments.append(segment_path)

    # Final merge
    with open(os.path.join(session_workspace, 'list.txt'), 'w') as f:
        for item in timeline_segments:
            f.write(f"file '{item}'\n")
    ffmpeg.input(os.path.join(session_workspace, 'list.txt'), format='concat', safe=0).output(final_output_path, c='copy').run()

    return "Video Ready!", final_output_path

# --- 4. GRADIO UI ---
with gr.Blocks() as demo:
    gr.Markdown("# 🎬 AI B-Roll Creator Pro")
    script = gr.Textbox(label="Paste Script - Max 1400 words", lines=10)
    word_count = gr.Textbox(label="Word Count")
    lang = gr.Dropdown(["English US", "Urdu"], label="Language")
    btn = gr.Button("🚀 Generate Video")
    status = gr.Textbox(label="Status")
    video_out = gr.Video(label="Your Video")

    script.change(lambda x: f"{len(x.split())} / 1400", script, word_count)
    btn.click(generate_video, inputs=[script, lang], outputs=[status, video_out])

demo.launch(server_name="0.0.0.0", server_port=7860)
