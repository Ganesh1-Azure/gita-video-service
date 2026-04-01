import os, subprocess, tempfile, requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image')
        music_url = request.form.get('music_url')
        sanskrit = request.form.get('sanskrit', '')
        translation = request.form.get('translation', '')
        telugu = request.form.get('telugu_translation', '')
        chapter_verse = request.form.get('chapter_verse', '')

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, 'image.jpg')
            audio_path = os.path.join(tmpdir, 'narration.mp3')
            music_path = os.path.join(tmpdir, 'music.mp3')

            image_file.save(img_path)
            audio_file.save(audio_path)

            r = requests.get(music_url, timeout=30)
            with open(music_path, 'wb') as f:
                f.write(r.content)

            mixed_path = os.path.join(tmpdir, 'mixed.mp3')
            subprocess.run([
                'ffmpeg', '-y',
                '-i', audio_path,
                '-i', music_path,
                '-filter_complex', '[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first',
                mixed_path
            ], check=True)

            def esc(t): return t.replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")

            output_path = os.path.join(tmpdir, 'output.mp4')
            subprocess.run([
                'ffmpeg', '-y',
                '-loop', '1', '-i', img_path,
                '-i', mixed_path,
                '-vf', (
                    f"drawtext=text='{esc(chapter_verse)}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=30:box=1:boxcolor=black@0.5:boxborderw=10,"
                    f"drawtext=text='{esc(sanskrit)}':fontcolor=yellow:fontsize=20:x=(w-text_w)/2:y=h-220:box=1:boxcolor=black@0.6:boxborderw=8,"
                    f"drawtext=text='{esc(translation)}':fontcolor=white:fontsize=16:x=(w-text_w)/2:y=h-160:box=1:boxcolor=black@0.6:boxborderw=8,"
                    f"drawtext=text='{esc(telugu)}':fontcolor=cyan:fontsize=16:x=(w-text_w)/2:y=h-100:box=1:boxcolor=black@0.6:boxborderw=8"
                ),
                '-c:v', 'libx264', '-tune', 'stillimage',
                '-c:a', 'aac', '-b:a', '192k',
                '-pix_fmt', 'yuv420p',
                '-shortest',
                output_path
            ], check=True)

            return send_file(output_path, mimetype='video/mp4',
                           as_attachment=True, download_name='output.mp4')

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
