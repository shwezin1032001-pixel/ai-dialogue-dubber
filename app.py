from flask import Flask, render_template_string, request, send_file
import subprocess
import os
import asyncio
import edge_tts
from deep_translator import GoogleTranslator
from groq import Groq
import time

app = Flask(__name__)

API_PART1 = "gsk_"
API_PART2 = "RQXwEWatRMPoCkGYNCt0WGdyb3FY5b6bnhYPI6UVvn062wnyp4Pv"
GROQ_CLIENT = Groq(api_key=API_PART1 + API_PART2)

VOICE_MALE = "my-MM-ThihaNeural"
VOICE_FEMALE = "my-MM-NilarNeural"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="my">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Myanmar Studio</title>
    <style>
        body { background-color: #0b0c16; color: #e2e8f0; font-family: sans-serif; padding: 14px; margin: 0; }
        .card { background: #151829; border: 1px solid #232742; border-radius: 14px; padding: 20px; max-width: 480px; margin: 20px auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .header h2 { color: #38bdf8; margin: 0 0 6px 0; font-size: 22px; }
        .mode-box { display: flex; gap: 10px; margin-bottom: 20px; }
        .mode-option { flex: 1; border: 1px solid #232742; padding: 12px 8px; border-radius: 10px; text-align: center; background: #0c0e17; cursor: pointer; }
        .mode-option input { margin-bottom: 6px; }
        .upload-box { border: 2px dashed #38bdf8; border-radius: 12px; padding: 25px; text-align: center; cursor: pointer; margin-bottom: 20px; background: #101223; }
        button { width: 100%; background: linear-gradient(90deg, #0284c7, #38bdf8); color: white; border: none; padding: 14px; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 16px; }
        .loading { display: none; text-align: center; color: #38bdf8; margin-top: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h2>✨ AI Myanmar Video Studio</h2>
            <small style="color: #94a3b8;">ဇာတ်လမ်းတို၊ TikTok နှင့် 3D ကာတွန်းများကို မြန်မာအသံပြောင်းပေးသည့် စနစ်</small>
        </div>

        <form method="POST" action="/process" enctype="multipart/form-data" onsubmit="document.getElementById('loading').style.display='block'; document.getElementById('submitBtn').style.display='none';">
            <div class="mode-box">
                <label class="mode-option">
                    <input type="radio" name="mode" value="dialogue" checked>
                    <div style="font-weight: bold; font-size: 13px; color: #38bdf8;">🎭 Dialogue Mode</div>
                    <small style="color: #94a3b8; font-size: 11px;">အပြန်အလှန် စကားပြောသံ</small>
                </label>
                <label class="mode-option">
                    <input type="radio" name="mode" value="recap">
                    <div style="font-weight: bold; font-size: 13px; color: #38bdf8;">🎙️ Recap Mode</div>
                    <small style="color: #94a3b8; font-size: 11px;">ဇာတ်ကြောင်းပြန် အသံ</small>
                </label>
            </div>

            <div class="upload-box" onclick="document.getElementById('videoFile').click()">
                <div style="font-size:36px;">🎬</div>
                <div id="file-name" style="font-size:15px; font-weight:bold; color:#38bdf8; margin-top:8px;">ဗီဒီယို ဖိုင်ရွေးချယ်ပါ</div>
                <small style="color:#94a3b8;">(တရုတ်၊ အင်္ဂလိပ်၊ 3D ကာတွန်း စသည့် မည်သည့် ဗီဒီယိုမဆို)</small>
                <input type="file" id="videoFile" name="video" accept="video/*" style="display:none;" onchange="document.getElementById('file-name').innerText = this.files[0].name" required>
            </div>
            
            <button type="submit" id="submitBtn">⚡ Start Myanmar AI Dubbing</button>
            <div id="loading" class="loading">⏳ AI စနစ်မှ မြန်မာလို အသံသွင်းပေးနေပါသည်...</div>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/process', methods=['POST'])
def process():
    video = request.files.get('video')
    mode = request.form.get('mode', 'dialogue')
    if not video or video.filename == '':
        return "Video ဖိုင် ရွေးချယ်ပေးပါ", 400

    timestamp = int(time.time())
    temp_dir = f"temp_{timestamp}"
    os.makedirs(temp_dir, exist_ok=True)

    input_vid = os.path.join(temp_dir, "input.mp4")
    video.save(input_vid)
    extracted_audio = os.path.join(temp_dir, "extracted.wav")
    final_output = f"output_{timestamp}.mp4"

    subprocess.run(["ffmpeg", "-y", "-i", input_vid, "-t", "300", "-vn", "-ar", "16000", "-ac", "1", extracted_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open(extracted_audio, "rb") as f:
        res = GROQ_CLIENT.audio.transcriptions.create(
            file=(extracted_audio, f.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    segments = res.segments

    if mode == "dialogue":
        dub_segments = []
        current_voice = VOICE_MALE
        for idx, seg in enumerate(segments):
            orig_text = seg['text'].strip()
            if not orig_text:
                continue
            try:
                my_text = GoogleTranslator(source='auto', target='my').translate(orig_text)
            except Exception:
                my_text = orig_text

            current_voice = VOICE_FEMALE if current_voice == VOICE_MALE else VOICE_MALE
            seg_file = os.path.join(temp_dir, f"seg_{idx}.mp3")

            async def gen(t=my_text, v=current_voice, o=seg_file):
                comm = edge_tts.Communicate(t, voice=v, rate="+10%")
                await comm.save(o)
            asyncio.run(gen())

            dub_segments.append({"file": seg_file, "delay": int(seg['start'] * 1000)})

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
    else:
        full_text = " ".join([s['text'] for s in segments])
        try:
            my_full_text = GoogleTranslator(source='auto', target='my').translate(full_text[:1500])
        except Exception:
            my_full_text = full_text[:1500]

        recap_audio = os.path.join(temp_dir, "recap.mp3")
        async def gen_recap():
            comm = edge_tts.Communicate(my_full_text, voice=VOICE_MALE)
            await comm.save(recap_audio)
        asyncio.run(gen_recap())

        subprocess.run([
            "ffmpeg", "-y", "-i", input_vid, "-i", recap_audio,
            "-filter_complex", "[0:a]volume=0.1[orig];[orig][1:a]amix=inputs=2:duration=first[outa]",
            "-map", "0:v:0", "-map", "[outa]",
            "-c:v", "copy", "-c:a", "aac",
            final_output
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return send_file(final_output, as_attachment=True, download_name="myanmar_ai_video.mp4")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
