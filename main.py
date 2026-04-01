import os, subprocess, tempfile, requests, threading
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

@app.route('/render', methods=['POST'])
def render_video():
    try:
        audio_file = request.files.get('audio')
        image_file = request.files.get('image') or request.files.get('data')  # fix: accept both
        music_url = request.form.get('music_url')

        if not audio_file:
            return jsonify({'error': 'Missing audio file'}), 400
        if not image_file:
            return jsonify({'error': 'Missing image file'}), 400
        if not music_url:
            return jsonify({'error': 'Missing music_url'}), 400

        tmpdir = tempfile.mkdtemp()  # don't use 'with' block - keep files alive

        img_path = os.path.join(tmpdir, 'image.jpg')
        audio_path = os.path.join(tmpdir, 'narration.mp3')
        music_path = os.path.join(tmpdir, 'music.mp3')
        mixed_path = os.path.join(tmpdir, 'mixed.mp3')
        output_path = os.path.join(tmpdir, 'output.mp4')

        image_file.save(img_path)
        audio_file.save(audio_path)

        r = requests.get(music_url, timeout=60)
        with open(music_path, 'wb') as f:
            f.write(r.content)

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

        # Step 2: Render video
        render_result = subprocess.run([
            'ffmpeg', '-y',
            '-loop', '1', '-i', img_path,
            '-i', mixed_path,
            '-c:v', 'libx264',
            '-tune', 'stillimage',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-shortest',
            output_path
        ], capture_output=True, text=True, timeout=240)

        if render_result.returncode != 0:
            return jsonify({'error': 'Video render failed', 'stderr': render_result.stderr}), 500

        return send_file(output_path, mimetype='video/mp4',
                         as_attachment=True, download_name='output.mp4')

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'FFmpeg timed out - file too large'}), 500
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
