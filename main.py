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

    # Cinematic overlay
    darkener = Image.new("RGBA", (W, H), (0, 0, 0, 70))
    img = Image.alpha_composite(img, darkener)

    draw = ImageDraw.Draw(img)

    try:
        font_header = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 40)
    except:
        font_header = ImageFont.load_default()

    GOLD = (255,215,0,255)

    # Header
    draw.rectangle([0,0,W,70], fill=(0,0,0,180))
    draw.rectangle([0,66,W,70], fill=GOLD)

    header = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    draw.text((W//2,35), header, fill=GOLD, font=font_header, anchor="mm")

    img.convert("RGB").save(output_path, "JPEG", quality=95)


# ---------------- API ---------------- #
@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image') or request.files.get('data')
        music_url  = request.form.get('music_url')

        sanskrit = request.form.get('sanskrit', '').replace(":", "\\:").replace("'", "\\'")
        meaning  = request.form.get('meaning', '').replace(":", "\\:").replace("'", "\\'")
        telugu   = request.form.get('telugu_translation', '').replace(":", "\\:").replace("'", "\\'")
        chapter  = request.form.get('chapter', '')
        verse    = request.form.get('verse', '')

        if not audio_file or not image_file or not music_url:
            return jsonify({'error': 'Missing inputs'}), 400

        tmpdir = tempfile.mkdtemp()

        img_path = os.path.join(tmpdir, 'img.jpg')
        text_img = os.path.join(tmpdir, 'text.jpg')
        audio_path = os.path.join(tmpdir, 'voice.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        mixed = os.path.join(tmpdir, 'mixed.mp3')
        output = os.path.join(tmpdir, 'out.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        # Download music
        r = requests.get(music_url)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        # Draw base image
        draw_text_on_image(img_path, text_img, chapter, verse)

        # Mix audio
        subprocess.run([
            'ffmpeg','-y',
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex','[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed
        ], check=True)

        # 🔥 ANIMATED TEXT + SLOW ZOOM
        vf_text = f"""
        zoompan=z='min(zoom+0.0005,1.1)':d=300,
        scale=1280:720,

        drawtext=text='{sanskrit}':
        fontcolor=yellow:fontsize=42:
        x=(w-text_w)/2:y=h-260:
        enable='between(t,0,12)',

        drawtext=text='{meaning}':
        fontcolor=white:fontsize=30:
        x=(w-text_w)/2:y=h-170:
        enable='between(t,12,28)',

        drawtext=text='{telugu}':
        fontcolor=green:fontsize=36:
        x=(w-text_w)/2:y=h-90:
        enable='between(t,28,50)'
        """

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
