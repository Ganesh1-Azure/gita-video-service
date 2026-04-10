import os, subprocess, tempfile, requests
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

app = Flask(__name__)

def draw_text_on_image(img_path, output_path, sanskrit, transliteration, meaning, telugu_translation, chapter, verse):
    # ── Canvas: 1280 * 720 (9:16 YouTube Video) ──
    W, H = 1280, 720

    # Open and fill the full canvas with the image (zoom/crop to fill)
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

    # Center crop
    left = (new_w - W) // 2
    top  = (new_h - H) // 2
    img  = img.crop((left, top, left + W, top + H))

    # Slightly darken image for text readability
    darkener = Image.new("RGBA", (W, H), (0, 0, 0, 80))
    img = Image.alpha_composite(img, darkener)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # ── Font paths ──
    devanagari_font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
    telugu_font_path     = "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf"
    latin_font_path      = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    bold_font_path       = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"

    try:
        font_header   = ImageFont.truetype(bold_font_path,       32)
        font_sanskrit = ImageFont.truetype(devanagari_font_path, 30)
        font_meaning  = ImageFont.truetype(latin_font_path,      22)
        font_telugu   = ImageFont.truetype(telugu_font_path,     26)
        font_label    = ImageFont.truetype(bold_font_path,       18)
    except:
        font_header = font_sanskrit = font_meaning = font_telugu = font_label = ImageFont.load_default()

    GOLD      = (255, 215,   0, 255)
    WHITE     = (255, 255, 255, 230)
    GREEN     = (144, 238, 144, 230)
    LABEL_COL = (200, 200, 200, 180)

    # ── TOP HEADER BAR ──
    draw.rectangle([0, 0, W, 70], fill=(0, 0, 0, 210))
    draw.rectangle([0, 66, W, 70], fill=GOLD)  # gold accent line
    header_text = f"Bhagavad Gita  |  Chapter {chapter}  Verse {verse}"
    draw.text((W // 2, 35), header_text, font=font_header, fill=GOLD, anchor="mm")

    # ── BOTTOM TEXT PANEL ──
    panel_top = H - 480
    draw.rectangle([0, panel_top, W, H], fill=(0, 0, 0, 200))
    draw.rectangle([0, panel_top, W, panel_top + 4], fill=GOLD)  # gold top border

    pad_x = 28
    y = panel_top + 22

    # Sanskrit
    draw.text((pad_x, y), "॥ Sanskrit ॥", font=font_label, fill=LABEL_COL)
    y += 26
    for line in textwrap.wrap(sanskrit, width=36):
        draw.text((pad_x, y), line, font=font_sanskrit, fill=GOLD)
        y += 38
    y += 10

    # Divider
    draw.line([pad_x, y, W - pad_x, y], fill=(255, 255, 255, 60), width=1)
    y += 14

    # English Meaning
    draw.text((pad_x, y), "Meaning", font=font_label, fill=LABEL_COL)
    y += 26
    for line in textwrap.wrap(meaning, width=52):
        draw.text((pad_x, y), line, font=font_meaning, fill=WHITE)
        y += 30
    y += 10

    # Divider
    draw.line([pad_x, y, W - pad_x, y], fill=(255, 255, 255, 60), width=1)
    y += 14

    # Telugu
    draw.text((pad_x, y), "తెలుగు అనువాదం", font=font_label, fill=LABEL_COL)
    y += 26
    for line in textwrap.wrap(telugu_translation, width=38):
        draw.text((pad_x, y), line, font=font_telugu, fill=GREEN)
        y += 36

    # ── Merge and save ──
    combined = Image.alpha_composite(img, overlay)
    combined.convert("RGB").save(output_path, "JPEG", quality=95)


@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file         = request.files.get('audio')
        image_file         = request.files.get('image') or request.files.get('data')
        music_url          = request.form.get('music_url')
        sanskrit           = request.form.get('sanskrit', '')
        meaning            = request.form.get('meaning', '')
        telugu_translation = request.form.get('telugu_translation', '')
        chapter            = request.form.get('chapter', '')
        verse              = request.form.get('verse', '')
        transliteration    = request.form.get('transliteration', '')

        if not audio_file:
            return jsonify({'error': 'Missing audio file'}), 400
        if not image_file:
            return jsonify({'error': 'Missing image file'}), 400
        if not music_url:
            return jsonify({'error': 'Missing music_url'}), 400

        tmpdir             = tempfile.mkdtemp()
        img_path           = os.path.join(tmpdir, 'image.jpg')
        img_with_text_path = os.path.join(tmpdir, 'image_text.jpg')
        audio_path         = os.path.join(tmpdir, 'narration.mp3')
        music_path         = os.path.join(tmpdir, 'music.mp3')
        mixed_path         = os.path.join(tmpdir, 'mixed.mp3')
        output_path        = os.path.join(tmpdir, 'output.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        r = requests.get(music_url, timeout=60)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        draw_text_on_image(img_path, img_with_text_path, sanskrit, transliteration, meaning, telugu_translation, chapter, verse)

        # Step 1: Mix audio
        mix_result = subprocess.run([
            'ffmpeg', '-y',
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex', '[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed_path
        ], capture_output=True, text=True, timeout=120)

        if mix_result.returncode != 0:
            return jsonify({'error': 'Audio mix failed', 'stderr': mix_result.stderr}), 500

        # Step 2: Render video — 720x1280 (9:16 Shorts format)
        render_result = subprocess.run([
            'ffmpeg', '-y',
            '-loop', '1', '-i', img_with_text_path,
            '-i', mixed_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-pix_fmt', 'yuv420p',
            '-vf', 'scale=1280:720',
            '-threads', '1',
            '-shortest',
            output_path
        ], capture_output=True, text=True, timeout=240)

        if render_result.returncode != 0:
            return jsonify({'error': 'Video render failed', 'stderr': render_result.stderr}), 500

        return send_file(output_path, mimetype='video/mp4',
                         as_attachment=True, download_name='output.mp4')

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'FFmpeg timed out'}), 500
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
