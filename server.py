import os
import time
import tempfile
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "mediavault_files")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cleanup_old_files(max_age_seconds=900):
    now = time.time()
    for fname in os.listdir(DOWNLOAD_DIR):
        fpath = os.path.join(DOWNLOAD_DIR, fname)
        try:
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                os.remove(fpath)
        except Exception:
            pass


def is_youtube_url(url):
    lower = url.lower()
    return "youtube.com" in lower or "youtu.be" in lower


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "online", "service": "MediaVault Backend"}), 200


@app.route("/files/<path:filename>", methods=["GET"])
def serve_file(filename):
    clean_display = filename.split("_", 1)[-1] if "_" in filename else filename
    return send_from_directory(
        DOWNLOAD_DIR,
        filename,
        as_attachment=True,
        download_name=clean_display,
    )


@app.route("/api/download", methods=["POST"])
def download_media():
    cleanup_old_files()
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    media_type = data.get("type", "video").lower()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if is_youtube_url(url):
        return jsonify({"error": "YouTube links are not supported."}), 400

    job_id = str(uuid.uuid4())[:8]
    out_template = os.path.join(DOWNLOAD_DIR, f"{job_id}_%(title).50s.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "restrictfilenames": True,
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

        stored_filename = os.path.basename(final_path)
        clean_name = stored_filename.split("_", 1)[-1]
        base_url = request.host_url.rstrip("/").replace("http://", "https://")
        file_url = f"{base_url}/files/{stored_filename}"

        return jsonify({
            "download_url": file_url,
            "filename": clean_name
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
