import os, subprocess, tempfile, requests, json
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import textwrap

app = Flask(__name__)

# ── Font paths ────────────────────────────────────────────────────────────────
FONT_PATHS = {
    "header":   ["/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"],
    "sanskrit": [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf",
    ],
    "english":  [
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "telugu":   [
        "/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansTelugu-Regular.otf",
    ],
}

def find_font(key, size=40):
    for path in FONT_PATHS[key]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def get_audio_duration(path):
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', path
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for stream in data.get('streams', []):
        if 'duration' in stream:
            return float(stream['duration'])
    return 60.0


def wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_text_layer(size, text, font, color, max_width, line_height_extra=8):
    """
    Render wrapped text onto a transparent RGBA layer.
    Returns (layer_image, total_height).
    """
    W, H = size
    # Temp draw to measure
    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    lines = wrap_text(text, font, max_width, draw)

    # Measure line height
    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = sample_bbox[3] - sample_bbox[1] + line_height_extra

    total_h = line_h * len(lines)
    layer = Image.new("RGBA", (W, total_h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    y = 10
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        # Shadow for readability
        d.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        d.text((x, y), line, font=font, fill=color)
        y += line_h

    return layer, total_h + 20


# ── THREE FRAMES: one per language ───────────────────────────────────────────
def build_frames(img_path, out_dir, chapter, verse, sanskrit, english, telugu):
    """
    Build 3 JPEG frames — each has the background + header + one text block.
    Returns list of frame paths [sanskrit_frame, english_frame, telugu_frame].
    """
    W, H = 1280, 720

    def load_bg():
        img = Image.open(img_path).convert("RGBA")
        ratio = img.width / img.height
        if ratio > W / H:
            new_h, new_w = H, int(H * ratio)
        else:
            new_w, new_h = W, int(W / ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left, top = (new_w - W) // 2, (new_h - H) // 2
        img = img.crop((left, top, left + W, top + H))
        img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 80)))
        return img

    font_header  = find_font("header",   40)
    font_sanskrit = find_font("sanskrit", 46)
    font_english  = find_font("english",  34)
    font_telugu   = find_font("telugu",   44)  # Larger for Telugu clarity

    GOLD       = (255, 215,   0, 255)
    WHITE      = (255, 255, 255, 255)
    YELLOW     = (255, 230,   0, 255)
    LIGHT_GREEN = (144, 238, 144, 255)

    header_text = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    max_text_w  = W - 80  # 40px padding each side

    configs = [
        ("sanskrit_frame.jpg", sanskrit, font_sanskrit, YELLOW),
        ("english_frame.jpg",  english,  font_english,  WHITE),
        ("telugu_frame.jpg",   telugu,   font_telugu,   LIGHT_GREEN),
    ]

    frame_paths = []
    for filename, text, font, color in configs:
        bg = load_bg()
        draw = ImageDraw.Draw(bg)

        # Header bar
        draw.rectangle([0, 0, W, 72], fill=(0, 0, 0, 190))
        draw.rectangle([0, 68, W, 72], fill=GOLD)
        draw.text((W // 2, 36), header_text, fill=GOLD, font=font_header, anchor="mm")

        # Text block — rendered as a layer, then composited
        text_layer, text_h = render_text_layer(
            (W, H), text, font, color, max_text_w
        )

        # Dark backing strip behind text
        strip_y = H - text_h - 20
        strip = Image.new("RGBA", (W, text_h + 20), (0, 0, 0, 160))
        bg.alpha_composite(strip, (0, strip_y))

        # Composite text on top
        bg.alpha_composite(text_layer, (0, strip_y + 10))

        path = os.path.join(out_dir, filename)
        bg.convert("RGB").save(path, "JPEG", quality=95)
        frame_paths.append(path)

    return frame_paths  # [sanskrit, english, telugu]


# ── API ───────────────────────────────────────────────────────────────────────
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
        audio_path = os.path.join(tmpdir, 'voice.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        mixed      = os.path.join(tmpdir, 'mixed.mp3')
        concat_txt = os.path.join(tmpdir, 'concat.txt')
        output     = os.path.join(tmpdir, 'out.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        r = requests.get(music_url)
        with open(music_path, 'wb') as f:
            f.write(r.content)

        # Build 3 frames (one per language)
        frames = build_frames(
            img_path, tmpdir, chapter, verse, sanskrit, meaning, telugu
        )
        sanskrit_frame, english_frame, telugu_frame = frames

        # Get audio duration, split into 3 equal parts
        duration = get_audio_duration(audio_path)
        third = duration / 3

        # Mix audio
        subprocess.run([
            'ffmpeg', '-y',
            '-i', audio_path,
            '-i', music_path,
            '-filter_complex', '[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed
        ], check=True)

        # Build each segment as a separate video clip
        clips = []
        for i, (frame, dur) in enumerate([
            (sanskrit_frame, third),
            (english_frame,  third),
            (telugu_frame,   duration - 2 * third),  # remainder to avoid float drift
        ]):
            clip_path = os.path.join(tmpdir, f'clip_{i}.mp4')
            subprocess.run([
                'ffmpeg', '-y',
                '-loop', '1', '-i', frame,
                '-t', str(dur),
                '-vf', "zoompan=z='min(zoom+0.0004,1.08)':d=125:s=1280x720,scale=1280:720",
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-pix_fmt', 'yuv420p',
                '-r', '25',
                clip_path
            ], check=True)
            clips.append(clip_path)

        # Concatenate the 3 silent clips
        with open(concat_txt, 'w') as f:
            for clip in clips:
                f.write(f"file '{clip}'\n")

        silent_concat = os.path.join(tmpdir, 'silent.mp4')
        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0', '-i', concat_txt,
            '-c', 'copy',
            silent_concat
        ], check=True)

        # Add mixed audio to the concatenated video
        subprocess.run([
            'ffmpeg', '-y',
            '-i', silent_concat,
            '-i', mixed,
            '-c:v', 'copy',
            '-c:a', 'aac',
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
