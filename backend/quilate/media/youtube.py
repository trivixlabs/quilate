from pathlib import Path

MAX_FILESIZE = 500 * 1024 * 1024  # ~10 h de áudio; acima disso é live gravada ou link errado


def download_audio(url: str, out_dir: Path) -> Path:
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bestaudio",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,  # watch?v=X&list=Y baixa só o vídeo X
        "match_filter": yt_dlp.utils.match_filter_func("!is_live"),  # live em andamento prenderia a thread por horas
        "max_filesize": MAX_FILESIZE,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return out_dir / f"{info['id']}.m4a"
