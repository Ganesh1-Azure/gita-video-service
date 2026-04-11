import os, subprocess, tempfile, requests
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

app = Flask(__name__)

# ---------------- IMAGE RENDER ---------------- #
def draw_text_on_image(img_path, output_path, chapter, verse):
    W, H = 1280, 720

    img = Image.open(img_path).convert("RGBA")

    img_ratio = img.width / img.height
    target_ratio = W / H

    if img_ratio > target_ratio:
        new_h = H
        new_w = int(H * img_ratio)
    else:
        new_w = W
        new_h = int(W / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - W) // 2
    top  = (new_h - H) // 2
    img  = img.crop((left, top, left + W, top + H))

    darkener = Image.new("RGBA", (W, H), (0, 0, 0, 70))
    img = Image.alpha_composite(img, darkener)

    draw = ImageDraw.Draw(img)

    try:
        font_header = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 40)
    except:
        font_header = ImageFont.load_default()

    GOLD = (255,215,0,255)

    draw.rectangle([0,0,W,70], fill=(0,0,0,180))
    draw.rectangle([0,66,W,70], fill=GOLD)

    header = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    draw.text((W//2,35), header, fill=GOLD, font=font_header, anchor="mm")

    img.convert("RGB").save(output_path, "JPEG", quality=95)


def get_audio_duration(path):
    """Get duration of audio file in seconds using ffprobe"""
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', path
    ], capture_output=True, text=True)
    import json
    data = json.loads(result.stdout)
    for stream in data.get('streams', []):
        if 'duration' in stream:
            return float(stream['duration'])
    return 60.0  # fallback


def escape_ffmpeg_text(text):
    """Properly escape text for ffmpeg drawtext filter"""
    # Escape special characters for ffmpeg drawtext
    text = text.replace('\\', '\\\\')
    text = text.replace(':', '\\:')
    text = text.replace("'", "\u2019")  # Replace apostrophe with right single quote
    text = text.replace('%', '\\%')
    text = text.replace('[', '\\[')
    text = text.replace(']', '\\]')
    return text


def find_font(preferred_list):
    """Find first available font from list"""
    for font_path in preferred_list:
        if os.path.exists(font_path):
            return font_path
    return None


# ---------------- API ---------------- #
@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image') or request.files.get('data')
        music_url  = request.form.get('music_url')

        sanskrit = request.form.get('sanskrit', '')
        meaning  = request.form.get('meaning', '')
        telugu   = request.form.get('telugu_translation', '')
        chapter  = request.form.get('chapter', '')
        verse    = request.form.get('verse', '')

        if not audio_file or not image_file or not music_url:
            return jsonify({'error': 'Missing inputs'}), 400

        tmpdir = tempfile.mkdtemp()

        img_path   = os.path.join(tmpdir, 'img.jpg')
        text_img   = os.path.join(tmpdir, 'text.jpg')
        audio_path = os.path.join(tmpdir, 'voice.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        mixed      = os.path.join(tmpdir, 'mixed.mp3')
        output     = os.path.join(tmpdir, 'out.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        # Download music
        r = requests.get(music_url)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        # Draw base image
        draw_text_on_image(img_path, text_img, chapter, verse)

        # Get actual audio duration and split into 3 equal parts
        duration = get_audio_duration(audio_path)
        third = duration / 3
        t1_start, t1_end = 0, third
        t2_start, t2_end = third, third * 2
        t3_start, t3_end = third * 2, duration

        # Mix audio
        subprocess.run([
            'ffmpeg','-y',
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex','[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed
        ], check=True)

        # ── Font selection ──────────────────────────────────────────────
        # Sanskrit (Devanagari) font
        sanskrit_font = find_font([
            '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf',
            '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf',
            '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
        ])

        # English font
        english_font = find_font([
            '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        ])

        # Telugu font
        telugu_font = find_font([
            '/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf',
            '/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansTelugu-Regular.otf',
            '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
        ])

        # Fallback if fonts not found
        fallback = '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'
        sanskrit_font = sanskrit_font or fallback
        english_font  = english_font  or fallback
        telugu_font   = telugu_font   or fallback

        # Escape text safely
        sanskrit_esc = escape_ffmpeg_text(sanskrit)
        meaning_esc  = escape_ffmpeg_text(meaning)
        telugu_esc   = escape_ffmpeg_text(telugu)

        # ── Build drawtext filters with correct fonts ───────────────────
        # Sanskrit text — shown during first third of audio
        sanskrit_filter = (
            f"drawtext=text='{sanskrit_esc}'"
            f":fontfile='{sanskrit_font}'"
            f":fontcolor=yellow:fontsize=44"
            f":x=(w-text_w)/2:y=h-220"
            f":box=1:boxcolor=black@0.5:boxborderw=10"
            f":enable='between(t,{t1_start:.2f},{t1_end:.2f})'"
        )

        # English meaning — shown during second third
        meaning_filter = (
            f"drawtext=text='{meaning_esc}'"
            f":fontfile='{english_font}'"
            f":fontcolor=white:fontsize=32"
            f":x=(w-text_w)/2:y=h-160"
            f":box=1:boxcolor=black@0.5:boxborderw=8"
            f":enable='between(t,{t2_start:.2f},{t2_end:.2f})'"
        )

        # Telugu translation — shown during last third
        telugu_filter = (
            f"drawtext=text='{telugu_esc}'"
            f":fontfile='{telugu_font}'"
            f":fontcolor=#90EE90:fontsize=38"
            f":x=(w-text_w)/2:y=h-100"
            f":box=1:boxcolor=black@0.5:boxborderw=8"
            f":enable='between(t,{t3_start:.2f},{t3_end:.2f})'"
        )

        vf_text = (
            "zoompan=z='min(zoom+0.0005,1.1)':d=300,"
            "scale=1280:720,"
            f"{sanskrit_filter},"
            f"{meaning_filter},"
            f"{telugu_filter}"
        )

        subprocess.run([
            'ffmpeg','-y',
            '-loop','1','-i', text_img,
            '-i', mixed,
            '-vf', vf_text,
            '-c:v','libx264',
            '-preset','ultrafast',
            '-tune','stillimage',
            '-c:a','aac',
            '-pix_fmt','yuv420p',
            '-shortest',
            output
        ], check=True)

        return send_file(output, mimetype='video/mp4', as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
