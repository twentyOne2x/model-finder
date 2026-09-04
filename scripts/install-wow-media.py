#!/usr/bin/env python3
"""Install the optional World of Warcraft media used by the original demo.

The files downloaded by this script are not covered by this repository's MIT
license. Running the script records only that the caller reviewed the linked
third-party terms; it does not create or grant any copyright, trademark, or
redistribution rights.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import wave


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BLIZZARD_LEGAL_FAQ = (
    "https://www.blizzard.com/en-us/legal/"
    "c1ae32ac-7ff9-4ac3-a03b-fc04b8697010/blizzard-legal-faq"
)
BLIZZARD_VIDEO_POLICY = (
    "https://www.blizzard.com/en-gb/legal/"
    "2068564f-f427-4c1c-8664-c107c90b34d5/blizzard-video-policy"
)
CRAFTCURSORS_COMMIT = "d6f03365925751fca2635f14bfd17d8058a4dd43"
MAX_SOURCE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class AudioAsset:
    source_name: str
    url: str
    source_sha256: str
    source_size: int
    output_name: str
    frames: int
    pcm_sha256: str


@dataclass(frozen=True)
class CursorAsset:
    source_name: str
    url: str
    source_sha256: str
    source_size: int
    output_name: str
    pixel_signature: str


AUDIO_ASSETS = (
    AudioAsset(
        "levelup2.ogg",
        "https://wow.zamimg.com/sound-ids/live/enus/182/567478/levelup2.ogg",
        "1153339e3d4fab1cfcb2c37ab3781462b517f6c69616c6e2b4326b76c73d1e68",
        60_724,
        "wow-dungeon-ready-567478.wav",
        221_399,
        "e9c45ac52cc02045f7ff988a35f1ea7e255de36843e6e5b2bd7060e483c4c6c2",
    ),
    AudioAsset(
        "uCharacterSheetTab.ogg",
        "https://wow.zamimg.com/sound-ids/live/enus/126/567422/uCharacterSheetTab.ogg",
        "1752f34b3f0af011fcc87d48524b86af76bf6d38f888cdf68da972aaa6541e50",
        4_753,
        "wow-enter-dungeon-click-567422.wav",
        8_960,
        "c0d0cb205e6e9d1ae28f3a7e5b45b701846422ac667c15f15cf7f1a273e1640f",
    ),
    AudioAsset(
        "LFG_RoleCheck.ogg",
        "https://wow.zamimg.com/sound-ids/live/enus/217/567513/LFG_RoleCheck.ogg",
        "77e24671b9507fa7e6fd239aa1ac8999d5a04cbd32255dc87079829e59b25f4a",
        29_481,
        "wow-party-member-confirm-567513.wav",
        138_240,
        "0091289aecd16cc9a5eebb026d12c24a3a88cb0d56e0912668c5cce3da48a545",
    ),
)

CURSOR_ASSETS = (
    CursorAsset(
        "gauntlet.cur",
        f"https://raw.githubusercontent.com/Slackcraft/CraftCursors/{CRAFTCURSORS_COMMIT}/assets/cur/gauntlet.cur",
        "caa4d4954e6a685cb8e64651402d58db3ddfe3c7d2327c63066b0783722e1491",
        4_286,
        "wow-gauntlet-cursor@2x.png",
        "ff5284ab589e66a1bd4a72585a3e7e985167e45b274736b20b8a3af8c2fd820c",
    ),
    CursorAsset(
        "gauntlet_active.cur",
        f"https://raw.githubusercontent.com/Slackcraft/CraftCursors/{CRAFTCURSORS_COMMIT}/assets/cur/gauntlet_active.cur",
        "748822c7104718f3403e515ec1295cfc3a04cf5b89c0f60ecafd893f2656a370",
        4_286,
        "wow-gauntlet-cursor-active@2x.png",
        "ab0baba589d071e9ee146b28a538342d0a7875217c70804708c1c24dda8d0dac",
    ),
)


class InstallError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(asset: AudioAsset | CursorAsset, destination: Path, timeout: int) -> None:
    request = Request(
        asset.url,
        headers={"User-Agent": "ModelFinder/1.0 (optional third-party media installer)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > MAX_SOURCE_BYTES:
                raise InstallError(f"{asset.source_name}: server declared an oversized response")
            data = response.read(MAX_SOURCE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
        raise InstallError(f"{asset.source_name}: download failed: {error}") from error
    if len(data) > MAX_SOURCE_BYTES:
        raise InstallError(f"{asset.source_name}: response exceeded {MAX_SOURCE_BYTES} bytes")
    if len(data) != asset.source_size:
        raise InstallError(
            f"{asset.source_name}: size mismatch (expected {asset.source_size}, got {len(data)})"
        )
    actual = sha256(data)
    if actual != asset.source_sha256:
        raise InstallError(
            f"{asset.source_name}: SHA-256 mismatch (expected {asset.source_sha256}, got {actual})"
        )
    destination.write_bytes(data)


def run_tool(command: list[str], timeout: int) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InstallError(f"tool failed: {command[0]}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no error text"
        raise InstallError(f"tool failed ({result.returncode}): {command[0]}: {detail}")


def validate_audio(path: Path, asset: AudioAsset) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            return False
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
                audio.getnframes(),
            ) != (2, 2, 44_100, asset.frames):
                return False
            samples = audio.readframes(audio.getnframes())
        return sha256(samples) == asset.pcm_sha256
    except (OSError, EOFError, wave.Error):
        return False


def cursor_signature(magick: str, path: Path, timeout: int) -> str | None:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        return None
    try:
        result = subprocess.run(
            [magick, "identify", "-format", "%w %h %#", str(path)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def validate_cursor(magick: str, path: Path, asset: CursorAsset, timeout: int) -> bool:
    return cursor_signature(magick, path, timeout) == f"64 64 {asset.pixel_signature}"


def install(output_root: Path, download_timeout: int, tool_timeout: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    magick = shutil.which("magick")
    if not ffmpeg:
        raise InstallError("ffmpeg was not found on PATH")
    if not magick:
        raise InstallError("ImageMagick's `magick` was not found on PATH")

    audio_directory = output_root / "assets" / "audio"
    theme_directory = output_root / "assets" / "theme"
    audio_directory.mkdir(parents=True, exist_ok=True)
    theme_directory.mkdir(parents=True, exist_ok=True)

    audio_ready = all(validate_audio(audio_directory / item.output_name, item) for item in AUDIO_ASSETS)
    cursor_ready = all(
        validate_cursor(magick, theme_directory / item.output_name, item, tool_timeout)
        for item in CURSOR_ASSETS
    )
    if audio_ready and cursor_ready:
        print(f"World of Warcraft media already installed and verified under {output_root}")
        return

    with tempfile.TemporaryDirectory(prefix=".model-finder-media-", dir=output_root) as temporary:
        staging = Path(temporary)
        staged_outputs: list[tuple[Path, Path]] = []

        for asset in AUDIO_ASSETS:
            source = staging / asset.source_name
            result = staging / asset.output_name
            download(asset, source, download_timeout)
            run_tool(
                [
                    ffmpeg,
                    "-nostdin",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    str(result),
                ],
                tool_timeout,
            )
            if not validate_audio(result, asset):
                raise InstallError(f"{asset.output_name}: converted audio failed validation")
            staged_outputs.append((result, audio_directory / asset.output_name))

        for asset in CURSOR_ASSETS:
            source = staging / asset.source_name
            converted = staging / f"{asset.source_name}.png"
            result = staging / asset.output_name
            download(asset, source, download_timeout)
            run_tool([magick, str(source), str(converted)], tool_timeout)
            run_tool(
                [magick, str(converted), "-filter", "point", "-resize", "64x64", str(result)],
                tool_timeout,
            )
            if not validate_cursor(magick, result, asset, tool_timeout):
                raise InstallError(f"{asset.output_name}: converted cursor failed validation")
            staged_outputs.append((result, theme_directory / asset.output_name))

        for staged, destination in staged_outputs:
            os.chmod(staged, 0o644)
            os.replace(staged, destination)

    if not all(validate_audio(audio_directory / item.output_name, item) for item in AUDIO_ASSETS):
        raise InstallError("installed audio did not pass final validation")
    if not all(
        validate_cursor(magick, theme_directory / item.output_name, item, tool_timeout)
        for item in CURSOR_ASSETS
    ):
        raise InstallError("installed cursor images did not pass final validation")
    print(f"Installed and verified optional World of Warcraft media under {output_root}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--accept-third-party-terms",
        action="store_true",
        help="confirm that you reviewed the linked owner policies; this grants no rights",
    )
    result.add_argument(
        "--output-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="project root that will receive assets/audio and assets/theme",
    )
    result.add_argument("--download-timeout-seconds", type=int, default=20)
    result.add_argument("--tool-timeout-seconds", type=int, default=60)
    return result


def main() -> int:
    args = parser().parse_args()
    if not 1 <= args.download_timeout_seconds <= 120:
        print("install-wow-media: download timeout must be 1-120 seconds", file=sys.stderr)
        return 64
    if not 1 <= args.tool_timeout_seconds <= 600:
        print("install-wow-media: tool timeout must be 1-600 seconds", file=sys.stderr)
        return 64
    if not args.accept_third_party_terms:
        print(
            "This optional installer retrieves copyrighted World of Warcraft media.\n"
            f"Review Blizzard's Legal FAQ: {BLIZZARD_LEGAL_FAQ}\n"
            f"Review Blizzard's Video Policy: {BLIZZARD_VIDEO_POLICY}\n"
            "Also review CraftCursors: https://github.com/Slackcraft/CraftCursors\n"
            "If those terms fit your use, rerun with --accept-third-party-terms.\n"
            "The flag records review only; it does not grant or expand your rights.",
            file=sys.stderr,
        )
        return 2
    try:
        install(args.output_root.expanduser().resolve(), args.download_timeout_seconds, args.tool_timeout_seconds)
        return 0
    except (InstallError, OSError) as error:
        print(f"install-wow-media: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
