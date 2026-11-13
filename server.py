import os
import tempfile
import uuid
from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, expose_headers=["Content-Disposition"])

DOWNLOAD_DIR = tempfile.gettempdir()

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "online", "service": "MediaVault Backend"}), 200

@app.route("/api/download", methods=["POST"])
def download_media():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    media_type = data.get("type", "video").lower()  # 'video' or 'audio'

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    job_id = str(uuid.uuid4())[:8]
    out_template = os.path.join(DOWNLOAD_DIR, f"{job_id}_%(title).60s.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
    }

    if media_type == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = ydl.prepare_filename(info)

            if media_type == "audio":
                final_path = os.path.splitext(prepared)[0] + ".mp3"
            else:
                final_path = os.path.splitext(prepared)[0] + ".mp4"
                if not os.path.exists(final_path) and os.path.exists(prepared):
                    final_path = prepared

        if not os.path.exists(final_path):
            return jsonify({"error": "File conversion failed on server."}), 500

        clean_name = os.path.basename(final_path).split("_", 1)[-1]

        @after_this_request
        def cleanup(response):
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
            except Exception:
                pass
            return response

        return send_file(
            final_path,
            as_attachment=True,
            download_name=clean_name,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
