import os, subprocess, tempfile, requests
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import textwrap

app = Flask(__name__)

def draw_text_on_image(img_path, output_path, sanskrit, transliteration, meaning, telugu_translation, chapter, verse):
    img = Image.open(img_path).convert("RGBA")
    img = img.resize((720, 720))
    
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Font paths (Noto fonts installed in Docker)
    devanagari_font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
    telugu_font_path = "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf"
    latin_font_path = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    bold_font_path = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"

    # Load fonts
    try:
        font_sanskrit = ImageFont.truetype(devanagari_font_path, 26)
        font_telugu = ImageFont.truetype(telugu_font_path, 24)
        font_meaning = ImageFont.truetype(latin_font_path, 20)
        font_header = ImageFont.truetype(bold_font_path, 28)
    except:
        font_sanskrit = ImageFont.load_default()
        font_telugu = font_sanskrit
        font_meaning = font_sanskrit
        font_header = font_sanskrit

    W = 720

    # --- Top bar: Chapter/Verse label ---
    header_text = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    draw.rectangle([0, 0, W, 55], fill=(0, 0, 0, 180))
    draw.text((20, 12), header_text, font=font_header, fill=(255, 215, 0, 255))  # gold

    # --- Wrap all text sections ---
    sanskrit_lines = textwrap.wrap(sanskrit, width=38)
    meaning_lines = textwrap.wrap(f"Meaning: {meaning}", width=55)
    telugu_lines = textwrap.wrap(f"తెలుగు: {telugu_translation}", width=40)

    # Combine all lines with separators
    all_lines = sanskrit_lines + [""] + meaning_lines + [""] + telugu_lines

    line_height = 34
    box_height = len(all_lines) * line_height + 40
    box_y = 720 - box_height

    # Semi-transparent dark box at bottom
    draw.rectangle([0, box_y, W, 720], fill=(0, 0, 0, 200))

    # Draw divider line
    draw.line([20, box_y + 8, W - 20, box_y + 8], fill=(255, 215, 0, 200), width=2)

    y = box_y + 20

    sanskrit_end = len(sanskrit_lines)
    meaning_start = sanskrit_end + 1
    meaning_end = meaning_start + len(meaning_lines)
    telugu_start = meaning_end + 1

    for i, line in enumerate(all_lines):
        if not line:
            y += 10
            continue

        if i < sanskrit_end:
            # Sanskrit - gold color
            color = (255, 215, 0, 255)
            font = font_sanskrit
        elif i >= meaning_start and i < meaning_end:
            # English meaning - white color
            color = (255, 255, 255, 220)
            font = font_meaning
        elif i >= telugu_start:
            # Telugu - light green color
            color = (144, 238, 144, 220)
            font = font_telugu
        else:
            color = (255, 255, 255, 220)
            font = font_meaning

        draw.text((20, y), line, font=font, fill=color)
        y += line_height

    # Merge overlay onto image
    combined = Image.alpha_composite(img, overlay)
    combined.convert("RGB").save(output_path, "JPEG", quality=95)


@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image') or request.files.get('data')
        music_url = request.form.get('music_url')
        sanskrit = request.form.get('sanskrit', '')
        meaning = request.form.get('meaning', '')
        telugu_translation = request.form.get('telugu_translation', '')
        chapter = request.form.get('chapter', '')
        verse = request.form.get('verse', '')
        transliteration = request.form.get('transliteration', '')

        if not audio_file:
            return jsonify({'error': 'Missing audio file'}), 400
        if not image_file:
            return jsonify({'error': 'Missing image file'}), 400
        if not music_url:
            return jsonify({'error': 'Missing music_url'}), 400

        tmpdir = tempfile.mkdtemp()
        img_path = os.path.join(tmpdir, 'image.jpg')
        img_with_text_path = os.path.join(tmpdir, 'image_text.jpg')
        audio_path = os.path.join(tmpdir, 'narration.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        mixed_path = os.path.join(tmpdir, 'mixed.mp3')
        output_path = os.path.join(tmpdir, 'output.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        r = requests.get(music_url, timeout=60)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        # Draw text on image
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

        # Step 2: Render video using image WITH text
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
            '-vf', 'scale=720:720',
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
