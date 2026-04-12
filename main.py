import os, subprocess, tempfile, requests, json
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ── FONT SETUP ─────────────────────────────────────────
FONT_PATHS = {
    "header": ["/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"],
    "sanskrit": ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"],
    "english": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "telugu": ["/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf"],
}

def find_font(key, size=40):
    for path in FONT_PATHS[key]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# ── METADATA GENERATOR ─────────────────────────────────
def generate_youtube_metadata(chapter, verse, sanskrit, meaning, telugu, channel_name="FactShastra"):
    title = f"Bhagavad Gita Chapter {chapter} Verse {verse} | గీత సారం | {channel_name}"

    hashtags = (
        f"#BhagavadGita #Gita #GitaChapter{chapter} #GitaVerse{chapter}{verse} "
        "#KrishnaQuotes #GitaDaily #SanatanDharma #TeluguBhakti #SpiritualIndia"
    )

    description = f"""{hashtags}

🙏 Bhagavad Gita | Chapter {chapter} Verse {verse} 🙏

{sanskrit}

🌍 Meaning:
{meaning}

🌸 Telugu:
{telugu}

🔔 Subscribe for daily Gita wisdom!

🌺 Jai Shri Krishna 🌺"""

    return {
        "title": title,
        "description": description,
        "tags": [
            "Bhagavad Gita", "Krishna", "Gita Telugu",
            "Spiritual", "Sanatan Dharma", channel_name
        ]
    }

# ── API ───────────────────────────────────────────────
@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image')
        music_url  = request.form.get('music_url')

        sanskrit = request.form.get('sanskrit', '')
        meaning  = request.form.get('meaning', '')
        telugu   = request.form.get('telugu_translation', '')
        chapter  = request.form.get('chapter', '')
        verse    = request.form.get('verse', '')
        channel_name = request.form.get('channel_name', 'FactShastra')

        if not audio_file or not image_file or not music_url:
            return jsonify({'error': 'Missing inputs'}), 400

        tmpdir = tempfile.mkdtemp()

        img_path   = os.path.join(tmpdir, 'img.jpg')
        audio_path = os.path.join(tmpdir, 'voice.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        output     = os.path.join(tmpdir, 'out.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        r = requests.get(music_url)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        # 🔥 SIMPLE VIDEO CREATION
        subprocess.run([
            'ffmpeg', '-y',
            '-loop', '1', '-i', img_path,
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex', '[2:a]volume=0.1[bg];[1:a][bg]amix=inputs=2',
            '-shortest',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            output
        ], check=True)

        # 🔥 GENERATE METADATA
        metadata = generate_youtube_metadata(
            chapter, verse, sanskrit, meaning, telugu, channel_name
        )

        # ✅ IMPORTANT FIX (THIS IS WHAT YOU NEEDED)
        return jsonify({
            "video_path": output,
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
