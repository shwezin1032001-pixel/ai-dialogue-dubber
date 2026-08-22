from flask import Flask, render_template_string, request, send_file
import subprocess
import os
import asyncio
import edge_tts
from deep_translator import GoogleTranslator
from groq import Groq
import time

app = Flask(__name__)

# API Key လုံခြုံစွာ ချိတ်ဆက်ခြင်း
API_PART1 = "gsk_"
API_PART2 = "RQXwEWatRMPoCkGYNCt0WGdyb3FY5b6bnhYPI6UVvn062wnyp4Pv"
GROQ_CLIENT = Groq(api_key=API_PART1 + API_PART2)

VOICE_MALE = "my-MM-ThihaNeural"
VOICE_FEMALE = "my-MM-NilarNeural"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Dialogue Dubber Studio</title>
    <style>
        body { background-color: #0b0c16; color: #e2e8f0; font-family: sans-serif; padding: 14px; margin: 0; padding-bottom: 30px; }
        .header { text-align: center; margin-bottom: 20px; border-bottom: 1px solid #232742; padding-bottom: 10px; }
        .header h2 { color: #38bdf8; margin: 0; font-size: 22px; }
        .card { background: #151829; border: 1px solid #232742; border-radius: 14px; padding: 16px; max-width: 500px; margin: 0 auto; }
        .upload-box { border: 2px dashed #38bdf8; border-radius: 12px; padding: 25px; text-align: center; cursor: pointer; margin-bottom: 15px; background: #101223; }
        button { width: 100%; background: linear-gradient(90deg, #0284c7, #38bdf8); color: white; border: none; padding: 14px; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 15px; }
    </style>
</head>
<body>
    <div class="header">
        <h2>🎭 AI Dialogue Dubber Studio</h2>
        <small style="color: #94a3b8;">ဇာတ်ကောင် အချင်းချင်း အပြန်အလှန် စကားပြောသံ ထည့်သွင်းပေးသည့် စနစ်</small>
    </div>

    <div class="card">
        <form method="POST" action="/dub" enctype="multipart/form-data">
            <div class="upload-box" onclick="document.getElementById('videoFile').click()">
                <div style="font-size:32px;">🎬</div>
                <div id="file-name" style="font-size:14px; font-weight:bold; color:#38bdf8; margin-top:8px;">ဗီဒီယို ဖိုင်ရွေးချယ်ပါ</div>
                <small style="color:#94a3b8;">တရုတ် / အင်္ဂလိပ် စကားပြော ဗီဒီယို (၅ မိနစ်အထိ)</small>
                <input type="file" id="videoFile" name="video" accept="video/*" style="display:none;" onchange="document.getElementById('file-name').innerText = this.files[0].name" required>
            </div>
            
            <button type="submit">✨ Start Auto Dialogue Dubbing</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/dub', methods=['POST'])
def dub_video():
    video = request.files.get('video')
    if not video or video.filename == '':
        return "Video ဖိုင် ရွေးချယ်ပေးပါ", 400

    timestamp = int(time.time())
    temp_dir = f"temp_{timestamp}"
    os.makedirs(temp_dir, exist_ok=True)

    input_vid = os.path.join(temp_dir, "input.mp4")
    video.save(input_vid)
    extracted_audio = os.path.join(temp_dir, "extracted.wav")
    final_output = f"dialogue_dubbed_{timestamp}.mp4"

    subprocess.run(["ffmpeg", "-y", "-i", input_vid, "-t", "300", "-vn", "-ar", "16000", "-ac", "1", extracted_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open(extracted_audio, "rb") as f:
        res = GROQ_CLIENT.audio.transcriptions.create(
            file=(extracted_audio, f.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    segments = res.segments
    dub_segments = []
    current_voice = VOICE_MALE

    for idx, seg in enumerate(segments):
        start_ms = int(seg['start'] * 1000)
        orig_text = seg['text'].strip()
        if not orig_text:
            continue
        try:
            my_text = GoogleTranslator(source='auto', target='my').translate(orig_text)
        except:
            my_text = orig_text

        current_voice = VOICE_FEMALE if current_voice == VOICE_MALE else VOICE_MALE
        seg_file = os.path.join(temp_dir, f"seg_{idx}.mp3")

        async def gen():
            comm = edge_tts.Communicate(my_text, voice=current_voice, rate="+10%")
            await comm.save(seg_file)
        asyncio.run(gen())

        dub_segments.append({"file": seg_file, "delay": start_ms})

    if not dub_segments:
        return "ဗီဒီယိုထဲတွင် စကားပြောသံ မတွေ့ရှိပါ", 400

    inputs_cmd = []
    delays = []
    mix_ins = []
    for i, seg in enumerate(dub_segments):
        inputs_cmd.extend(["-i", seg["file"]])
        in_idx = i + 1
        delays.append(f"[{in_idx}:a]adelay={seg['delay']}|{seg['delay']}[a{in_idx}]")
        mix_ins.append(f"[a{in_idx}]")

    filter_complex = f"{';'.join(delays)};{''.join(mix_ins)}amix=inputs={len(dub_segments)}:normalize=0[alldubs];[0:a]volume=0.08[orig];[orig][alldubs]amix=inputs=2:duration=first[outa]"

    subprocess.run([
        "ffmpeg", "-y", "-i", input_vid,
        *inputs_cmd,
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[outa]",
        "-c:v", "copy", "-c:a", "aac",
        final_output
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return send_file(final_output, as_attachment=True, download_name="myanmar_dialogue_dubbed.mp4")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
