#!/usr/bin/env python3
"""Download a concrete Bilibili BV/av video link as a local mp4."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, build_opener


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15"
QUALITY_MAP = {
    127: "8K",
    126: "Dolby Vision",
    125: "HDR",
    120: "4K",
    116: "1080P60",
    112: "1080P+",
    80: "1080P",
    74: "720P60",
    64: "720P",
    32: "480P",
    16: "320P",
}
DEFAULT_QUALITY = 127
VIDEO_PATTERN = re.compile(r"^/video/(?P<id>BV[0-9A-Za-z]+|av\d+)", re.IGNORECASE)
INVALID_TITLE_CHARS = re.compile(r"""[「」`~!@#$^&*()=|{}':;',\[\].<>/?~！@#￥……&*（）——|{}【】'；：""。，、？\s]+""")


@dataclass(frozen=True)
class BilibiliUrl:
    url: str
    video_id: str
    page: int


@dataclass(frozen=True)
class BilibiliPage:
    title: str
    bvid: str
    cid: int
    page: int
    source_url: str


@dataclass(frozen=True)
class StreamSelection:
    video_url: str
    audio_url: str
    quality: int
    quality_label: str


@dataclass(frozen=True)
class DownloadResult:
    title: str
    bvid: str
    cid: int
    page: int
    source_url: str
    output_path: str
    selected_quality: int
    selected_quality_label: str


class BilibiliDownloadError(RuntimeError):
    pass


class BilibiliClient:
    def __init__(self, sessdata: str = "") -> None:
        self.opener = build_opener()
        self.cookie = normalize_cookie(sessdata)
        self.bfe_id = ""

    def request(self, url: str, *, referer: str = "", response_type: str = "text") -> tuple[Any, str]:
        response = self.open(url, referer=referer)
        final_url = response.geturl()
        data = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)
        if response_type == "bytes":
            return data, final_url
        text = data.decode("utf-8", errors="replace")
        if response_type == "json":
            return json.loads(text), final_url
        return text, final_url

    def open(self, url: str, *, referer: str = ""):
        headers = self.headers(referer=referer)
        response = self.opener.open(Request(url, headers=headers))
        self.update_bfe_id(response.headers.get_all("Set-Cookie", []))
        return response

    def headers(self, *, referer: str = "") -> dict[str, str]:
        headers = {"User-Agent": UA, "Accept-Encoding": "identity"}
        cookie = self.cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        if referer:
            headers["Referer"] = referer
        return headers

    def cookie_header(self) -> str:
        parts = []
        if self.cookie:
            parts.append(self.cookie)
        if self.bfe_id:
            parts.append(f"bfe_id={self.bfe_id}")
        return "; ".join(parts)

    def update_bfe_id(self, cookies: list[str]) -> None:
        for item in cookies:
            match = re.search(r"(?:^|;\s*)bfe_id=([^;]+)", item)
            if match:
                self.bfe_id = match.group(1)
                return


def normalize_cookie(sessdata: str) -> str:
    value = sessdata.strip()
    if not value:
        return ""
    if "=" in value:
        return value
    return f"SESSDATA={value}"


def sanitize_title(title: str, fallback: str = "bilibili-video") -> str:
    value = INVALID_TITLE_CHARS.sub("", title).strip()
    return value or fallback


def classify_bilibili_url(url: str) -> BilibiliUrl:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host != "bilibili.com" and not host.endswith(".bilibili.com"):
        raise ValueError("Only bilibili.com video URLs are supported.")
    match = VIDEO_PATTERN.match(parsed.path)
    if not match:
        raise ValueError("Only concrete /video/BV... or /video/av... URLs are supported.")
    return BilibiliUrl(url=url, video_id=match.group("id"), page=extract_page_number(url))


def extract_page_number(url: str) -> int:
    values = parse_qs(urlparse(url).query).get("p", [])
    if not values:
        return 1
    try:
        return max(1, int(values[0]))
    except ValueError:
        return 1


def extract_json_assignment(html: str, name: str) -> dict[str, Any]:
    marker = f"window.{name}="
    start = html.find(marker)
    if start < 0:
        raise BilibiliDownloadError(f"Could not find window.{name}.")
    index = start + len(marker)
    while index < len(html) and html[index].isspace():
        index += 1
    if index >= len(html) or html[index] != "{":
        raise BilibiliDownloadError(f"window.{name} did not contain a JSON object.")

    depth = 0
    in_string = False
    escaped = False
    for end in range(index, len(html)):
        char = html[end]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[index : end + 1])
    raise BilibiliDownloadError(f"Could not parse window.{name}.")


def parse_playinfo(html: str) -> dict[str, Any] | None:
    try:
        payload = extract_json_assignment(html, "__playinfo__")
    except BilibiliDownloadError:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def parse_video_page(html: str, source_url: str, requested_page: int) -> tuple[BilibiliPage, dict[str, Any] | None]:
    state = extract_json_assignment(html, "__INITIAL_STATE__")
    video_data = state.get("videoData")
    if not isinstance(video_data, dict):
        raise BilibiliDownloadError("Bilibili page did not contain videoData.")

    pages = video_data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise BilibiliDownloadError("Bilibili video did not contain page data.")

    page_data = next((item for item in pages if isinstance(item, dict) and int(item.get("page", 0)) == requested_page), None)
    if page_data is None:
        page_data = pages[0]
        requested_page = int(page_data.get("page", 1))

    bvid = str(video_data.get("bvid") or page_data.get("bvid") or "")
    cid = int(page_data.get("cid") or video_data.get("cid") or 0)
    if not bvid or not cid:
        raise BilibiliDownloadError("Bilibili page did not contain bvid/cid.")

    root_title = str(video_data.get("title") or bvid)
    page_part = str(page_data.get("part") or root_title)
    title = root_title if len(pages) == 1 else f"{root_title}-P{requested_page}-{page_part}"

    return (
        BilibiliPage(
            title=title,
            bvid=bvid,
            cid=cid,
            page=requested_page,
            source_url=source_url,
        ),
        parse_playinfo(html),
    )


def stream_url(stream: dict[str, Any]) -> str:
    for key in ("baseUrl", "base_url"):
        value = stream.get(key)
        if isinstance(value, str) and value:
            return value
    backups = stream.get("backupUrl") or stream.get("backup_url")
    if isinstance(backups, list):
        for value in backups:
            if isinstance(value, str) and value:
                return value
    return ""


def choose_video_stream(streams: list[dict[str, Any]], requested_quality: int | None = None) -> dict[str, Any]:
    valid = [item for item in streams if isinstance(item, dict) and stream_url(item)]
    if not valid:
        raise BilibiliDownloadError("No downloadable video stream found.")
    if requested_quality is not None:
        matches = [item for item in valid if int(item.get("id", -1)) == requested_quality]
        if matches:
            return max(matches, key=lambda item: int(item.get("bandwidth") or 0))
    return max(valid, key=lambda item: (int(item.get("id") or 0), int(item.get("bandwidth") or 0)))


def choose_audio_stream(streams: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in streams if isinstance(item, dict) and stream_url(item)]
    if not valid:
        raise BilibiliDownloadError("No downloadable audio stream found.")
    return max(valid, key=lambda item: (int(item.get("id") or 0), int(item.get("bandwidth") or 0)))


def select_streams(playinfo: dict[str, Any], requested_quality: int | None = None) -> StreamSelection:
    dash = playinfo.get("dash")
    if not isinstance(dash, dict):
        raise BilibiliDownloadError("Bilibili playurl response did not include DASH streams.")
    video_stream = choose_video_stream(dash.get("video") or [], requested_quality)
    audio_stream = choose_audio_stream(dash.get("audio") or [])
    quality = int(video_stream.get("id") or 0)
    return StreamSelection(
        video_url=stream_url(video_stream),
        audio_url=stream_url(audio_stream),
        quality=quality,
        quality_label=QUALITY_MAP.get(quality, str(quality)),
    )


def fetch_playurl(client: BilibiliClient, page: BilibiliPage, quality: int) -> dict[str, Any]:
    params = urlencode(
        {
            "cid": page.cid,
            "bvid": page.bvid,
            "qn": quality,
            "type": "",
            "otype": "json",
            "fourk": 1,
            "fnver": 0,
            "fnval": 80,
            "session": "68191c1dc3c75042c6f35fba895d65b0",
        }
    )
    payload, _ = client.request(f"https://api.bilibili.com/x/player/playurl?{params}", response_type="json")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise BilibiliDownloadError("Bilibili playurl API returned no data.")
    return data


def build_ffmpeg_command(video_path: Path, audio_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c",
        "copy",
        str(output_path),
    ]


def download_file(client: BilibiliClient, url: str, path: Path, referer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with client.open(url, referer=referer) as response:
        with path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def merge_streams(video_path: Path, audio_path: Path, output_path: Path) -> None:
    subprocess.run(build_ffmpeg_command(video_path, audio_path, output_path), check=True)


def download_bilibili_video(
    url: str,
    output_root: Path,
    sessdata: str = "",
    quality: int = DEFAULT_QUALITY,
) -> DownloadResult:
    classify_bilibili_url(url)
    client = BilibiliClient(sessdata)
    html, final_url = client.request(url)
    parsed = classify_bilibili_url(final_url)
    page, embedded_playinfo = parse_video_page(html, final_url, parsed.page)
    playinfo = embedded_playinfo if embedded_playinfo else fetch_playurl(client, page, quality)
    selection = select_streams(playinfo, requested_quality=quality)

    safe_title = sanitize_title(page.title, page.bvid)
    output_dir = output_root.expanduser().resolve() / safe_title
    output_path = output_dir / f"{safe_title}.mp4"
    video_path = output_dir / f"{safe_title}-video.m4s"
    audio_path = output_dir / f"{safe_title}-audio.m4s"
    metadata_path = output_dir / "bilibili.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        print(f"Downloading video stream: {selection.quality_label}")
        download_file(client, selection.video_url, video_path, page.source_url)
        print("Downloading audio stream")
        download_file(client, selection.audio_url, audio_path, page.source_url)
        print("Merging streams")
        merge_streams(video_path, audio_path, output_path)
    except Exception:
        print(f"Kept temporary files in {output_dir}", file=sys.stderr)
        raise
    else:
        video_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)

    result = DownloadResult(
        title=page.title,
        bvid=page.bvid,
        cid=page.cid,
        page=page.page,
        source_url=page.source_url,
        output_path=str(output_path),
        selected_quality=selection.quality,
        selected_quality_label=selection.quality_label,
    )
    metadata_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a concrete Bilibili BV/av video link as mp4.")
    parser.add_argument("url", help="Bilibili /video/BV... or /video/av... URL.")
    parser.add_argument("--output-root", type=Path, default=Path.cwd(), help="Output root. Default: current directory.")
    parser.add_argument("--sessdata", default=os.environ.get("BILIBILI_SESSDATA", ""), help="Optional SESSDATA or cookie string.")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY, help="Requested qn quality. Default: best available.")
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    require_command("ffmpeg")
    try:
        result = download_bilibili_video(args.url, args.output_root, args.sessdata, args.quality)
    except (BilibiliDownloadError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
