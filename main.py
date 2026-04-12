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
    W, H = size
    tmp  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    lines = wrap_text(text, font, max_width, draw)
    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = sample_bbox[3] - sample_bbox[1] + line_height_extra
    total_h = line_h * len(lines)
    layer = Image.new("RGBA", (W, total_h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = 10
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x  = (W - tw) // 2
        d.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        d.text((x, y),         line, font=font, fill=color)
        y += line_h
    return layer, total_h + 20


# ── Telugu auto-size helper ───────────────────────────────────────────────────
def get_telugu_font_and_lines(text, W, H):
    MAX_TEXT_H = int(H * 0.40) - 20
    MAX_TEXT_W = W - 80
    for size in range(48, 24, -2):
        font  = find_font("telugu", size)
        tmp   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d     = ImageDraw.Draw(tmp)
        lines = wrap_text(text, font, MAX_TEXT_W, d)
        sample = d.textbbox((0, 0), "అ", font=font)
        line_h = sample[3] - sample[1] + 10
        if line_h * len(lines) <= MAX_TEXT_H:
            return font, lines, line_h, line_h * len(lines)
    font   = find_font("telugu", 26)
    tmp    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d      = ImageDraw.Draw(tmp)
    lines  = wrap_text(text, font, MAX_TEXT_W, d)
    sample = d.textbbox((0, 0), "అ", font=font)
    line_h = sample[3] - sample[1] + 10
    return font, lines, line_h, line_h * len(lines)


# ── END CARD frame ────────────────────────────────────────────────────────────
def build_end_card(out_dir, channel_name="FactShastra"):
    W, H = 1280, 720

    # Deep saffron/spiritual gradient background
    bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)

    # Gradient: deep saffron top → dark maroon bottom
    for y in range(H):
        ratio = y / H
        r = int(180 - ratio * 80)
        g = int(60  - ratio * 40)
        b = int(0)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Decorative border
    GOLD = (255, 215, 0, 255)
    for thickness, alpha in [(6, 255), (2, 180)]:
        border_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(border_img)
        offset = 8 if thickness == 2 else 0
        bd.rectangle(
            [offset, offset, W - offset, H - offset],
            outline=(255, 215, 0, alpha), width=thickness
        )
        bg = Image.alpha_composite(bg, border_img)

    draw = ImageDraw.Draw(bg)

    # Om symbol at top
    try:
        font_om = find_font("sanskrit", 90)
    except:
        font_om = find_font("header", 60)

    om_text = "ॐ"
    bbox = draw.textbbox((0, 0), om_text, font=font_om)
    om_w = bbox[2] - bbox[0]
    draw.text(((W - om_w) // 2 + 2, 62), om_text, font=font_om, fill=(0, 0, 0, 180))
    draw.text(((W - om_w) // 2, 60),     om_text, font=font_om, fill=GOLD)

    # Channel name
    font_channel = find_font("header", 64)
    ch_bbox = draw.textbbox((0, 0), channel_name, font=font_channel)
    ch_w    = ch_bbox[2] - ch_bbox[0]
    draw.text(((W - ch_w) // 2 + 2, 182), channel_name, font=font_channel, fill=(0,0,0,200))
    draw.text(((W - ch_w) // 2,     180), channel_name, font=font_channel, fill=(255,255,255,255))

    # Divider line
    draw.rectangle([W//2 - 200, 258, W//2 + 200, 262], fill=GOLD)

    # Subscribe button (red pill shape)
    btn_w, btn_h = 380, 80
    btn_x = (W - btn_w) // 2
    btn_y = 290
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
                            radius=40, fill=(255, 0, 0, 255))
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
                            radius=40, outline=(255,255,255,200), width=3)

    font_btn = find_font("header", 36)
    sub_text = "🔔 SUBSCRIBE"
    sub_bbox = draw.textbbox((0, 0), sub_text, font=font_btn)
    sub_w    = sub_bbox[2] - sub_bbox[0]
    draw.text(((W - sub_w) // 2, btn_y + 22), sub_text, font=font_btn, fill=(255,255,255,255))

    # Bell + message
    font_msg = find_font("english", 30)
    msg = "Press the bell icon for daily Gita wisdom"
    msg_bbox = draw.textbbox((0, 0), msg, font=font_msg)
    msg_w    = msg_bbox[2] - msg_bbox[0]
    draw.text(((W - msg_w) // 2, 390), msg, font=font_msg, fill=(255, 230, 150, 255))

    # Telugu tagline
    font_tel = find_font("telugu", 34)
    tel_msg  = "ప్రతిరోజు గీత జ్ఞానం కోసం సబ్స్క్రైబ్ చేయండి 🙏"
    tel_bbox = draw.textbbox((0, 0), tel_msg, font=font_tel)
    tel_w    = tel_bbox[2] - tel_bbox[0]
    draw.text(((W - tel_w) // 2 + 2, 442), tel_msg, font=font_tel, fill=(0,0,0,180))
    draw.text(((W - tel_w) // 2,     440), tel_msg, font=font_tel, fill=(144, 238, 144, 255))

    # Bottom: social icons row
    font_social = find_font("header", 26)
    social_text = "YouTube  •  Instagram  •  Facebook  •  Telegram"
    soc_bbox    = draw.textbbox((0, 0), social_text, font=font_social)
    soc_w       = soc_bbox[2] - soc_bbox[0]
    draw.text(((W - soc_w) // 2, 510), social_text, font=font_social, fill=(255, 215, 0, 200))

    # Bottom bar
    draw.rectangle([0, H - 60, W, H], fill=(0, 0, 0, 200))
    font_tag = find_font("header", 28)
    tag = "🌸 Bhagavad Gita Daily • FactShastra 🌸"
    tag_bbox = draw.textbbox((0, 0), tag, font=font_tag)
    tag_w    = tag_bbox[2] - tag_bbox[0]
    draw.text(((W - tag_w) // 2, H - 45), tag, font=font_tag, fill=(255, 215, 0, 255))

    path = os.path.join(out_dir, "end_card.jpg")
    bg.convert("RGB").save(path, "JPEG", quality=95)
    return path


# ── Copy-paste content generator ─────────────────────────────────────────────
def generate_youtube_metadata(chapter, verse, sanskrit, meaning, telugu, channel_name="FactShastra"):
    title = f"Bhagavad Gita Chapter {chapter} Verse {verse} | గీత సారం | {channel_name}"

    hashtags = (
        f"#BhagavadGita #Gita #GitaChapter{chapter} #GitaVerse{chapter}{verse} "
        "#KrishnaQuotes #GitaSaar #GitaDaily #HinduPhilosophy #SanatanDharma "
        "#BhagavadGitaInTelugu #TeluguBhakti #TeluguSpiritual #TeluguDevotion "
        "#GitaTelugu #KrishnaArjuna #VedicWisdom #SpiritualWisdom #DailyGita "
        "#HinduScriptures #GitaQuotes #Dharma #Yoga #BhaktiYoga #JnanaYoga "
        "#KarmaYoga #Moksha #Vedanta #IndianPhilosophy #SpiritualIndia "
        "#FactShastra #GitaMotivation"
    )

    description = f"""🙏 Bhagavad Gita | Chapter {chapter} Verse {verse} 🙏

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 SANSKRIT SHLOKA | సంస్కృత శ్లోకం
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{sanskrit}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 ENGLISH MEANING | అర్థం (ఆంగ్లంలో)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{meaning}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌸 TELUGU TRANSLATION | తెలుగు అనువాదం
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{telugu}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 Subscribe to {channel_name} for daily Bhagavad Gita wisdom!
ప్రతిరోజు గీత జ్ఞానం కోసం సబ్స్క్రైబ్ చేయండి!

👍 Like | 💬 Comment | 🔗 Share this with your family & friends!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 Follow us on:
- YouTube: {channel_name}
- Instagram: @{channel_name.lower()}
- Facebook: {channel_name}
- Telegram: t.me/{channel_name.lower()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{hashtags}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ COPYRIGHT NOTICE:
All Bhagavad Gita content is from public domain sacred texts.
Background music is royalty-free.

🌺 Jai Shri Krishna 🌺 జై శ్రీ కృష్ణ 🌺"""

    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "tags": [
            f"Bhagavad Gita", f"Gita Chapter {chapter}",
            f"Gita Verse {verse}", "Krishna", "Arjuna",
            "Telugu Bhakti", "Gita in Telugu", "Gita Saar",
            "Hindu Philosophy", "Sanatan Dharma", "Vedic Wisdom",
            "Spiritual Wisdom", "Daily Gita", "BhagavadGita Telugu",
            "Gita Quotes", "Krishna Quotes", "Dharma", "Yoga",
            "Moksha", "Vedanta", channel_name, "FactShastra"
        ]
    }


# ── THREE FRAMES: one per language ───────────────────────────────────────────
def build_frames(img_path, out_dir, chapter, verse, sanskrit, english, telugu):
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

    font_header   = find_font("header",   40)
    font_sanskrit = find_font("sanskrit", 46)
    font_english  = find_font("english",  34)

    GOLD        = (255, 215,   0, 255)
    WHITE       = (255, 255, 255, 255)
    YELLOW      = (255, 230,   0, 255)
    LIGHT_GREEN = (100, 255, 120, 255)

    header_text = f"Bhagavad Gita | Chapter {chapter} Verse {verse}"
    max_text_w  = W - 80

    frame_paths = []

    # Sanskrit + English frames
    for filename, text, font, color in [
        ("sanskrit_frame.jpg", sanskrit, font_sanskrit, YELLOW),
        ("english_frame.jpg",  english,  font_english,  WHITE),
    ]:
        bg   = load_bg()
        draw = ImageDraw.Draw(bg)
        draw.rectangle([0, 0, W, 72], fill=(0, 0, 0, 190))
        draw.rectangle([0, 68, W, 72], fill=GOLD)
        draw.text((W // 2, 36), header_text, fill=GOLD, font=font_header, anchor="mm")
        text_layer, text_h = render_text_layer((W, H), text, font, color, max_text_w)
        strip_y = H - text_h - 20
        strip   = Image.new("RGBA", (W, text_h + 20), (0, 0, 0, 170))
        bg.alpha_composite(strip, (0, strip_y))
        bg.alpha_composite(text_layer, (0, strip_y + 10))
        path = os.path.join(out_dir, filename)
        bg.convert("RGB").save(path, "JPEG", quality=95)
        frame_paths.append(path)

    # Telugu frame — auto-sized font + stronger shadow
    bg   = load_bg()
    draw = ImageDraw.Draw(bg)
    draw.rectangle([0, 0, W, 72], fill=(0, 0, 0, 190))
    draw.rectangle([0, 68, W, 72], fill=GOLD)
    draw.text((W // 2, 36), header_text, fill=GOLD, font=font_header, anchor="mm")

    tel_font, tel_lines, line_h, total_h = get_telugu_font_and_lines(telugu, W, H)
    PADDING   = 24
    strip_top = H - total_h - PADDING * 2
    strip     = Image.new("RGBA", (W, total_h + PADDING * 2), (0, 0, 0, 210))
    bg.alpha_composite(strip, (0, strip_top))

    d = ImageDraw.Draw(bg)
    y = strip_top + PADDING
    for line in tel_lines:
        bbox = d.textbbox((0, 0), line, font=tel_font)
        tw   = bbox[2] - bbox[0]
        x    = (W - tw) // 2
        for dx, dy in [(-2,2),(2,2),(0,3),(0,-1),(-1,1),(1,1)]:
            d.text((x+dx, y+dy), line, font=tel_font, fill=(0, 0, 0, 230))
        d.text((x, y), line, font=tel_font, fill=LIGHT_GREEN)
        y += line_h

    path = os.path.join(out_dir, "telugu_frame.jpg")
    bg.convert("RGB").save(path, "JPEG", quality=95)
    frame_paths.append(path)

    return frame_paths


# ── API ───────────────────────────────────────────────────────────────────────
@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file   = request.files.get('audio')
        image_file   = request.files.get('image') or request.files.get('data')
        music_url    = request.form.get('music_url')
        channel_name = request.form.get('channel_name', 'FactShastra')

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

        # Build 3 language frames + end card
        frames   = build_frames(img_path, tmpdir, chapter, verse, sanskrit, meaning, telugu)
        end_card = build_end_card(tmpdir, channel_name)
        sanskrit_frame, english_frame, telugu_frame = frames

        # Audio duration → split into 3 equal parts for languages
        duration     = get_audio_duration(audio_path)
        third        = duration / 3
        END_CARD_DUR = 5.0   # seconds for end card

        # Mix audio (voice + background music)
        subprocess.run([
            'ffmpeg', '-y',
            '-i', audio_path, '-i', music_path,
            '-filter_complex', '[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first',
            mixed
        ], check=True)

        # Build silent video clips
        clips = []
        segments = [
            (sanskrit_frame, third),
            (english_frame,  third),
            (telugu_frame,   duration - 2 * third),
            (end_card,       END_CARD_DUR),
        ]
        for i, (frame, dur) in enumerate(segments):
            clip_path = os.path.join(tmpdir, f'clip_{i}.mp4')
            subprocess.run([
                'ffmpeg', '-y',
                '-loop', '1', '-i', frame,
                '-t', str(dur),
                '-vf', "zoompan=z='min(zoom+0.0004,1.08)':d=125:s=1280x720,scale=1280:720",
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-pix_fmt', 'yuv420p', '-r', '25',
                clip_path
            ], check=True)
            clips.append(clip_path)

        # Concatenate all clips
        with open(concat_txt, 'w') as f:
            for clip in clips:
                f.write(f"file '{clip}'\n")

        silent_concat = os.path.join(tmpdir, 'silent.mp4')
        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0', '-i', concat_txt,
            '-c', 'copy', silent_concat
        ], check=True)

        # Extend audio with silence to cover end card, then mux
        total_dur = duration + END_CARD_DUR
        extended_audio = os.path.join(tmpdir, 'extended.mp3')
        subprocess.run([
            'ffmpeg', '-y',
            '-i', mixed,
            '-af', f'apad=whole_dur={total_dur}',
            '-t', str(total_dur),
            extended_audio
        ], check=True)

        subprocess.run([
            'ffmpeg', '-y',
            '-i', silent_concat, '-i', extended_audio,
            '-c:v', 'copy', '-c:a', 'aac', '-shortest',
            output
        ], check=True)

        # Generate YouTube metadata
        metadata = generate_youtube_metadata(
            chapter, verse, sanskrit, meaning, telugu, channel_name
        )

        # Return video + metadata as JSON if requested, else just video
        want_meta = request.form.get('include_metadata', 'false').lower() == 'true'
        if want_meta:
            return jsonify({
                'metadata': metadata,
                'message': 'Video rendered. Fetch /download/<tmpdir> for the file.'
            })

        return send_file(output, mimetype='video/mp4', as_attachment=True,
                         download_name=f"BG_{chapter}_{verse}.mp4")

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Metadata-only endpoint ────────────────────────────────────────────────────
@app.route('/metadata', methods=['POST'])
def get_metadata():
    """
    Call this separately to get copy-paste YouTube title, description, hashtags.
    Body: { chapter, verse, sanskrit, meaning, telugu_translation, channel_name }
    """
    data         = request.get_json() or request.form
    chapter      = data.get('chapter', '')
    verse        = data.get('verse', '')
    sanskrit     = data.get('sanskrit', '')
    meaning      = data.get('meaning', '')
    telugu       = data.get('telugu_translation', '')
    channel_name = data.get('channel_name', 'FactShastra')
    meta = generate_youtube_metadata(chapter, verse, sanskrit, meaning, telugu, channel_name)
    return jsonify(meta)


@app.route('/health')
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
