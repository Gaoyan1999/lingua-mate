#!/usr/bin/env python3
"""Download a concrete YouTube video link as a local mp4."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
DEFAULT_YOUTUBE_DL_ROOT = Path("/Users/daniel/Workspace/youtube-dl")
VIDEO_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]{11}$")
INVALID_TITLE_CHARS = re.compile(r"""[「」`~!@#$^&*()=|{}':;',\[\].<>/?~！@#￥……&*（）——|{}【】'；：""。，、？\s]+""")


@dataclass(frozen=True)
class YouTubeUrl:
    url: str
    video_id: str


@dataclass(frozen=True)
class DownloadResult:
    title: str
    video_id: str
    source_url: str
    output_path: str
    selected_format: str
    duration: float | None
    uploader: str


class YouTubeDownloadError(RuntimeError):
    pass


def sanitize_title(title: str, fallback: str = "youtube-video") -> str:
    value = INVALID_TITLE_CHARS.sub("", title).strip()
    return value or fallback


def classify_youtube_url(url: str) -> YouTubeUrl:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("Only concrete YouTube video URLs are supported.")

    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host == "youtube.com" or host.endswith(".youtube.com") or host == "youtube-nocookie.com" or host.endswith(
        ".youtube-nocookie.com"
    ):
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        else:
            match = re.match(r"^/(?:shorts|embed|v|live)/([^/?#]+)", parsed.path)
            if match:
                video_id = match.group(1)
    else:
        raise ValueError("Only YouTube video URLs are supported.")

    if not VIDEO_ID_PATTERN.match(video_id):
        raise ValueError("Only concrete YouTube video URLs are supported.")

    return YouTubeUrl(url=url, video_id=video_id)


def default_youtube_dl_root() -> Path:
    return Path(os.environ.get("YOUTUBE_DL_ROOT") or DEFAULT_YOUTUBE_DL_ROOT)


def import_youtube_dl(downloader_root: Path | None = None):
    root = downloader_root.expanduser().resolve() if downloader_root else default_youtube_dl_root().expanduser().resolve()
    if (root / "youtube_dl" / "__init__.py").exists():
        root_text = str(root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
    elif downloader_root or os.environ.get("YOUTUBE_DL_ROOT"):
        raise YouTubeDownloadError(f"Could not find youtube_dl package under {root}.")

    try:
        import youtube_dl  # type: ignore
    except ImportError as error:
        raise YouTubeDownloadError(
            "Could not import youtube_dl. Set YOUTUBE_DL_ROOT or pass --youtube-dl-root to the reference checkout."
        ) from error
    return youtube_dl


def build_ydl_options(
    output_template: Path | None,
    *,
    format_spec: str = DEFAULT_FORMAT,
    cookies: Path | None = None,
    quiet: bool = False,
    skip_download: bool = False,
    recode_mp4: bool = False,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "format": format_spec,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "quiet": quiet,
        "no_warnings": quiet,
        "skip_download": skip_download,
    }
    if output_template is not None:
        options["outtmpl"] = str(output_template)
    if cookies is not None:
        options["cookiefile"] = str(cookies.expanduser())
    if recode_mp4:
        options["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]
    return options


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def resolve_cookies(cookies: Path | None) -> Path | None:
    if cookies is None:
        value = os.environ.get("YOUTUBE_COOKIES", "").strip()
        cookies = Path(value) if value else None
    if cookies is None:
        return None
    path = cookies.expanduser().resolve()
    if not path.exists():
        raise YouTubeDownloadError(f"YouTube cookies file does not exist: {path}")
    return path


def find_downloaded_media(output_dir: Path, safe_title: str) -> Path:
    candidates = [
        path
        for path in output_dir.glob(f"{safe_title}.*")
        if path.is_file()
        and path.suffix.lower() not in {".json", ".part", ".ytdl", ".temp"}
        and not re.search(r"\.f[0-9A-Za-z_-]+\.", path.name)
    ]
    mp4_candidates = [path for path in candidates if path.suffix.lower() == ".mp4"]
    selected = mp4_candidates or candidates
    if not selected:
        raise YouTubeDownloadError(f"Could not find downloaded media in {output_dir}.")
    return max(selected, key=lambda path: path.stat().st_mtime)


def download_youtube_video(
    url: str,
    output_root: Path,
    downloader_root: Path | None = None,
    cookies: Path | None = None,
    format_spec: str = DEFAULT_FORMAT,
    recode_mp4: bool = False,
) -> DownloadResult:
    parsed = classify_youtube_url(url)
    cookie_path = resolve_cookies(cookies)
    youtube_dl = import_youtube_dl(downloader_root)

    probe_options = build_ydl_options(
        None,
        format_spec=format_spec,
        cookies=cookie_path,
        quiet=True,
        skip_download=True,
    )
    with youtube_dl.YoutubeDL(probe_options) as ydl:
        info = ydl.extract_info(parsed.url, download=False)
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
        raise YouTubeDownloadError("YouTube URL did not resolve to a single video.")

    title = str(info.get("title") or parsed.video_id)
    video_id = str(info.get("id") or parsed.video_id)
    safe_title = sanitize_title(title, video_id)
    output_dir = output_root.expanduser().resolve() / safe_title
    output_dir.mkdir(parents=True, exist_ok=True)

    output_template = output_dir / f"{safe_title}.%(ext)s"
    download_options = build_ydl_options(
        output_template,
        format_spec=format_spec,
        cookies=cookie_path,
        quiet=False,
        skip_download=False,
        recode_mp4=recode_mp4,
    )
    try:
        with youtube_dl.YoutubeDL(download_options) as ydl:
            downloaded_info = ydl.extract_info(parsed.url, download=True)
    except Exception as error:
        print(f"Kept temporary files in {output_dir}", file=sys.stderr)
        raise YouTubeDownloadError(str(error)) from error

    final_info = downloaded_info if isinstance(downloaded_info, dict) else info
    output_path = find_downloaded_media(output_dir, safe_title)
    result = DownloadResult(
        title=title,
        video_id=video_id,
        source_url=str(final_info.get("webpage_url") or parsed.url),
        output_path=str(output_path),
        selected_format=str(final_info.get("format_id") or final_info.get("format") or format_spec),
        duration=final_info.get("duration") if isinstance(final_info.get("duration"), (int, float)) else None,
        uploader=str(final_info.get("uploader") or ""),
    )
    (output_dir / "youtube.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a concrete YouTube video link as mp4.")
    parser.add_argument("url", help="YouTube watch, youtu.be, shorts, embed, or live video URL.")
    parser.add_argument("--output-root", type=Path, default=Path.cwd(), help="Output root. Default: current directory.")
    parser.add_argument("--youtube-dl-root", type=Path, default=None, help="Path to the reference youtube-dl checkout.")
    parser.add_argument("--cookies", type=Path, default=None, help="Optional Netscape cookies.txt path. Defaults to YOUTUBE_COOKIES.")
    parser.add_argument("--format", default=DEFAULT_FORMAT, help="youtube-dl format selector.")
    parser.add_argument("--recode-mp4", action="store_true", help="Transcode the final video to mp4 if youtube-dl writes another container.")
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    require_command("ffmpeg")
    try:
        result = download_youtube_video(
            args.url,
            args.output_root,
            args.youtube_dl_root,
            args.cookies,
            args.format,
            args.recode_mp4,
        )
    except (YouTubeDownloadError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
