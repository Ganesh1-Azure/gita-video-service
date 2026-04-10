import os, subprocess, tempfile, requests
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

app = Flask(__name__)

# ---------------- IMAGE + TEXT RENDER ---------------- #
def draw_text_on_image(img_path, output_path, sanskrit, transliteration, meaning, telugu_translation, chapter, verse):
    W, H = 1280, 720

    img = Image.open(img_path).convert("RGBA")

    # Resize + crop
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

    # Light cinematic dark overlay
    darkener = Image.new("RGBA", (W, H), (0, 0, 0, 50))
    img = Image.alpha_composite(img, darkener)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Fonts
    try:
        font_header   = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 34)
        font_sanskrit = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", 32)
        font_meaning  = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 24)
        font_telugu   = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf", 28)
        font_label    = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 18)
    except:
        font_header = font_sanskrit = font_meaning = font_telugu = font_label = ImageFont.load_default()

    GOLD  = (255, 215, 0, 255)
    WHITE = (255, 255, 255, 230)
    GREEN = (120, 255, 180, 230)
    LABEL = (200, 200, 200, 180)

    # HEADER
    draw.rectangle([0, 0, W, 60], fill=(0, 0, 0, 160))
    draw.rectangle([0, 56, W, 60], fill=GOLD)

    header = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    draw.text((W//2, 30), header, font=font_header, fill=GOLD, anchor="mm")

    # BLUR PANEL
    panel_top = H - 360

    blurred = img.crop((0, panel_top, W, H)).filter(ImageFilter.GaussianBlur(12))
    img.paste(blurred, (0, panel_top))

    draw.rectangle([0, panel_top, W, H], fill=(0, 0, 0, 110))
    draw.rectangle([0, panel_top, W, panel_top+4], fill=GOLD)

    x = 30
    y = panel_top + 20

    # Sanskrit
    draw.text((x, y), "॥ Sanskrit ॥", font=font_label, fill=LABEL)
    y += 28
    for line in textwrap.wrap(sanskrit, width=36):
        draw.text((x, y), line, font=font_sanskrit, fill=GOLD)
        y += 42

    y += 10
    draw.line([x, y, W-x, y], fill=(255,255,255,60), width=1)
    y += 14

    # Meaning
    draw.text((x, y), "Meaning", font=font_label, fill=LABEL)
    y += 28
    for line in textwrap.wrap(meaning, width=52):
        draw.text((x, y), line, font=font_meaning, fill=WHITE)
        y += 34

    y += 10
    draw.line([x, y, W-x, y], fill=(255,255,255,60), width=1)
    y += 14

    # Telugu
    draw.text((x, y), "తెలుగు అనువాదం", font=font_label, fill=LABEL)
    y += 28
    for line in textwrap.wrap(telugu_translation, width=38):
        draw.text((x, y), line, font=font_telugu, fill=GREEN)
        y += 40

    final = Image.alpha_composite(img, overlay)
    final.convert("RGB").save(output_path, "JPEG", quality=95)


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

        # Draw UI
        draw_text_on_image(img_path, text_img, sanskrit, "", meaning, telugu, chapter, verse)

        # Mix audio
        subprocess.run([
            'ffmpeg','-y',
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex','[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed
        ], check=True)

        # Render video (LANDSCAPE + ZOOM EFFECT)
        subprocess.run([
            'ffmpeg','-y',
            '-loop','1','-i', text_img,
            '-i', mixed,
            '-vf',"zoompan=z='min(zoom+0.0015,1.2)':d=125,scale=1280:720",
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
