#!/usr/bin/env python3
"""Prepare, build, launch, and watch a config-driven Model Finder popup."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Sources" / "ModelFinderPopup" / "main.swift"
DEFAULT_BUILD_DIR = ROOT / ".build"
DEFAULT_CACHE_DIR = ROOT / ".cache"
MAX_AVATAR_BYTES = 8 * 1024 * 1024
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
THEME_FILES = {
    "frame": "wow-dungeon-finder-frame.png", "roleTank": "role-tank.png",
    "roleHealer": "role-healer.png", "roleDPS": "role-dps.png",
    "cursor": "wow-gauntlet-cursor@2x.png", "cursorActive": "wow-gauntlet-cursor-active@2x.png",
}


class ConfigError(ValueError):
    pass


def _fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = value.keys() - allowed
    if unknown:
        raise ConfigError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be an object")
    return value


def _text(value: Any, label: str, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    result = value.strip()
    if any(ord(char) < 32 for char in result):
        raise ConfigError(f"{label} must not contain control characters")
    if maximum is not None and len(result) > maximum:
        raise ConfigError(f"{label} must be at most {maximum} characters")
    return result


def profile_handle(value: str) -> str:
    """Accept an X/Twitter profile URL, never a general URL to fetch."""
    try:
        parsed = urlparse(value.strip())
    except ValueError as error:
        raise ConfigError("profile_url is malformed") from error
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        raise ConfigError("profile_url must be an https://x.com or https://twitter.com profile URL")
    handle = parsed.path.strip("/")
    if not HANDLE_PATTERN.fullmatch(handle) or parsed.query or parsed.fragment:
        raise ConfigError("profile_url must point to one profile, not a post or search")
    return handle


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{label} must be between {minimum:g} and {maximum:g}")
    return result


def load_config(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"config not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    return validate_config(raw)


def validate_config(raw: Any) -> dict[str, Any]:
    config = _mapping(raw, "config")
    _fields(config, {"$schema", "target", "members", "availability", "popup"}, "config")
    target = _mapping(config.get("target"), "target")
    _fields(target, {"model_id", "display_name"}, "target")
    _text(target.get("model_id"), "target.model_id", 128)
    _text(target.get("display_name"), "target.display_name", 24)

    members = config.get("members")
    if not isinstance(members, list) or len(members) != 5:
        raise ConfigError("members must contain exactly five entries")
    role_counts = {"tank": 0, "healer": 0, "dps": 0}
    local_count = 0
    names: set[str] = set()
    for index, value in enumerate(members):
        member = _mapping(value, f"members[{index}]")
        _fields(member, {"name", "role", "x_handle", "profile_url", "avatar", "portrait_zoom", "is_local"}, f"members[{index}]")
        name = _text(member.get("name"), f"members[{index}].name", 20)
        if name.casefold() in names:
            raise ConfigError(f"member name is duplicated: {name}")
        names.add(name.casefold())
        role = _text(member.get("role"), f"members[{index}].role").lower()
        if role not in role_counts:
            raise ConfigError(f"members[{index}].role must be tank, healer, or dps")
        role_counts[role] += 1
        has_handle = "x_handle" in member
        has_avatar = "avatar" in member
        if sum(key in member for key in ("x_handle", "profile_url", "avatar")) != 1:
            raise ConfigError(f"members[{index}] must have exactly one of x_handle, profile_url, or avatar")
        if has_handle:
            handle = _text(member["x_handle"], f"members[{index}].x_handle").removeprefix("@")
            if not HANDLE_PATTERN.fullmatch(handle):
                raise ConfigError(f"members[{index}].x_handle is not a valid X handle")
        elif "profile_url" in member:
            profile_handle(_text(member["profile_url"], f"members[{index}].profile_url"))
        else:
            _text(member["avatar"], f"members[{index}].avatar")
        _number(member.get("portrait_zoom", 1.15), f"members[{index}].portrait_zoom", 1, 2)
        if member.get("is_local", False) is not False and member.get("is_local") is not True:
            raise ConfigError(f"members[{index}].is_local must be a boolean")
        local_count += int(member.get("is_local", False))
    if role_counts != {"tank": 1, "healer": 1, "dps": 3}:
        raise ConfigError("party composition must be one tank, one healer, and three dps")
    if local_count > 1:
        raise ConfigError("at most one member may set is_local")

    availability = _mapping(config.get("availability", {}), "availability")
    _fields(availability, {"interval_seconds", "timeout_seconds", "command"}, "availability")
    if "availability" in config:
        validate_availability(availability)

    popup = _mapping(config.get("popup"), "popup")
    _fields(popup, {"destination_url", "destination_label", "idle_seconds", "confirmation_min_seconds", "confirmation_max_seconds", "sounds", "theme"}, "popup")
    destination = _text(popup.get("destination_url"), "popup.destination_url")
    try:
        parsed = urlparse(destination)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as error:
        raise ConfigError("popup.destination_url is malformed") from error
    if parsed.scheme.lower() not in {"codex", "http", "https"} or not host or parsed.username or parsed.password or any(char.isspace() for char in host):
        raise ConfigError("popup.destination_url must use codex, http, or https with a host and no credentials")
    _text(popup.get("destination_label", "CODEX" if parsed.scheme == "codex" else "LINK"), "popup.destination_label", 14)
    _number(popup.get("idle_seconds", 90), "popup.idle_seconds", 5, 300)
    minimum = _number(popup.get("confirmation_min_seconds", 0.8), "popup.confirmation_min_seconds", 0.5, 60)
    maximum = _number(popup.get("confirmation_max_seconds", 4.4), "popup.confirmation_max_seconds", 0.5, 60)
    if minimum > maximum:
        raise ConfigError("popup.confirmation_min_seconds cannot exceed confirmation_max_seconds")
    if math.ceil(minimum * 2) > math.floor(maximum * 2):
        raise ConfigError("popup confirmation range must contain at least one half-second bucket")
    sounds = _mapping(popup.get("sounds", {}), "popup.sounds")
    _fields(sounds, {"ready", "enter", "confirm"}, "popup.sounds")
    for key in ("ready", "enter", "confirm"):
        if key in sounds and sounds[key] != "":
            _text(sounds[key], f"popup.sounds.{key}")
    theme = _mapping(popup.get("theme", {}), "popup.theme")
    _fields(theme, set(THEME_FILES), "popup.theme")
    for key, value in theme.items():
        _text(value, f"popup.theme.{key}")
    return config


def validate_availability(availability: dict[str, Any]) -> None:
    interval = availability.get("interval_seconds")
    if isinstance(interval, bool) or not isinstance(interval, int) or not 10 <= interval <= 86400:
        raise ConfigError("availability.interval_seconds must be an integer from 10 to 86400")
    timeout = availability.get("timeout_seconds", 90)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 600:
        raise ConfigError("availability.timeout_seconds must be an integer from 5 to 600")
    command = availability.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise ConfigError("availability.command must be a non-empty array of non-empty strings")

    for value in command:
        if "\x00" in value:
            raise ConfigError("availability.command must not contain NUL characters")


def _image_extension(data: bytes, content_type: str) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ConfigError(f"avatar response was not a supported image ({content_type or 'unknown content type'})")


def fetch_x_avatar(handle: str, cache_directory: Path, refresh: bool) -> Path:
    if not HANDLE_PATTERN.fullmatch(handle):
        raise ConfigError("invalid X handle")
    avatar_directory = cache_directory / "avatars"
    avatar_directory.mkdir(parents=True, exist_ok=True)
    safe_handle = handle.lower()
    cached = sorted(avatar_directory.glob(f"x-{safe_handle}.*"))
    if cached and not refresh:
        candidate = cached[0]
        if candidate.stat().st_size <= MAX_AVATAR_BYTES:
            _image_extension(candidate.read_bytes(), "cached image")
            return candidate.resolve()
        raise ConfigError(f"cached avatar for @{handle} exceeded the size limit")

    url = f"https://unavatar.io/x/{quote(handle)}?fallback=false"
    request = Request(url, headers={"User-Agent": "ModelFinderKit/0.1 (+local-avatar-cache)"})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            data = response.read(MAX_AVATAR_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ConfigError(f"could not fetch public avatar for @{handle}: {error}") from error
    if len(data) > MAX_AVATAR_BYTES:
        raise ConfigError(f"avatar for @{handle} exceeded {MAX_AVATAR_BYTES // (1024 * 1024)} MiB")
    extension = _image_extension(data, content_type)
    destination = avatar_directory / f"x-{safe_handle}{extension}"
    atomic_write(destination, data)
    for stale in cached:
        if stale != destination:
            stale.unlink(missing_ok=True)
    return destination.resolve()


def atomic_write(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".model-finder-", delete=False) as temporary:
            temporary.write(data)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _resolve_file(value: str, config_directory: Path, label: str, optional: bool = False) -> str | None:
    if optional and not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_directory / path
    path = path.resolve()
    if not path.is_file():
        hint = " Run scripts/install-wow-media.py --accept-third-party-terms for the optional original WoW media." if "wow-" in path.name else ""
        raise ConfigError(f"{label} file not found: {path}.{hint}")
    return str(path)


def prepare_runtime(config_path: Path, cache_directory: Path, refresh: bool = False) -> Path:
    config_path = config_path.resolve()
    config = load_config(config_path)
    config_directory = config_path.parent
    members: list[dict[str, Any]] = []
    for member in config["members"]:
        if "x_handle" in member or "profile_url" in member:
            handle = member["x_handle"].strip().removeprefix("@") if "x_handle" in member else profile_handle(member["profile_url"])
            avatar_path = fetch_x_avatar(handle, cache_directory, refresh)
            avatar_source = f"https://x.com/{handle}"
        else:
            avatar_path = Path(_resolve_file(member["avatar"], config_directory, f"avatar for {member['name']}") or "")
            avatar_source = "local"
        members.append(
            {
                "name": member["name"].strip(),
                "role": member["role"].strip().lower(),
                "avatarPath": str(avatar_path),
                "avatarSource": avatar_source,
                "portraitZoom": float(member.get("portrait_zoom", 1.15)),
                "isLocal": bool(member.get("is_local", False)),
            }
        )

    sounds_config = config["popup"].get("sounds", {})
    sounds: dict[str, str | None] = {}
    for key in ("ready", "enter", "confirm"):
        sounds[key] = _resolve_file(
            sounds_config.get(key, ""),
            config_directory,
            f"popup.sounds.{key}",
            optional=True,
        )

    runtime = {
        "target": {
            "modelID": config["target"]["model_id"].strip(),
            "displayName": config["target"]["display_name"].strip(),
        },
        "members": members,
        "popup": {
            "destinationURL": config["popup"]["destination_url"].strip(),
            "destinationLabel": config["popup"].get("destination_label", "CODEX" if urlparse(config["popup"]["destination_url"]).scheme == "codex" else "LINK"),
            "idleSeconds": float(config["popup"].get("idle_seconds", 90)),
            "confirmationMinSeconds": float(config["popup"].get("confirmation_min_seconds", 0.8)),
            "confirmationMaxSeconds": float(config["popup"].get("confirmation_max_seconds", 4.4)),
            "sounds": sounds,
            "theme": {
                key: _resolve_file(config["popup"].get("theme", {}).get(key, str(ROOT / "assets" / "theme" / filename)), config_directory, f"popup.theme.{key}")
                for key, filename in THEME_FILES.items()
            },
        },
    }
    cache_directory.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(runtime, indent=2) + "\n").encode("utf-8")
    runtime_path = cache_directory / f"runtime-{hashlib.sha256(serialized).hexdigest()[:16]}.json"
    atomic_write(runtime_path, serialized)
    return runtime_path.resolve()


def build_popup(build_directory: Path) -> Path:
    if sys.platform != "darwin":
        raise ConfigError("the native popup currently requires macOS")
    swiftc_lookup = subprocess.run(["xcrun", "--find", "swiftc"], text=True, capture_output=True, check=False)
    if swiftc_lookup.returncode != 0:
        raise ConfigError("swiftc was not found; install Xcode Command Line Tools")
    swiftc = swiftc_lookup.stdout.strip()
    sdk_lookup = subprocess.run(["xcrun", "--show-sdk-path"], text=True, capture_output=True, check=False)
    if sdk_lookup.returncode != 0:
        raise ConfigError("the macOS SDK was not found; install Xcode Command Line Tools")
    architecture = platform.machine()
    if architecture not in {"arm64", "x86_64"}:
        raise ConfigError(f"unsupported Mac architecture: {architecture}")
    deployment_target = os.environ.get("MODEL_FINDER_MACOS_TARGET", "13.0")
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", deployment_target):
        raise ConfigError("MODEL_FINDER_MACOS_TARGET must look like 13.0")
    build_directory.mkdir(parents=True, exist_ok=True)
    binary = build_directory / "model-finder-popup"
    temporary_build = tempfile.TemporaryDirectory(prefix="compile-", dir=build_directory)
    temporary_binary = Path(temporary_build.name) / "model-finder-popup"
    command = [
        swiftc,
        "-O",
        str(SOURCE),
        "-target", f"{architecture}-apple-macosx{deployment_target}",
        "-sdk", sdk_lookup.stdout.strip(),
        "-framework", "AppKit",
        "-framework", "AVFoundation",
        "-framework", "QuartzCore",
        "-o", str(temporary_binary),
    ]
    try:
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise ConfigError(f"Swift popup build failed with exit code {result.returncode}")
        os.replace(temporary_binary, binary)
    finally:
        temporary_build.cleanup()
    return binary.resolve()


def launch_popup(runtime_path: Path, binary: Path) -> int:
    return subprocess.run([str(binary), str(runtime_path)], check=False).returncode


def expanded_check_command(config: dict[str, Any]) -> list[str]:
    if not config.get("availability"):
        raise ConfigError("add availability.command and interval_seconds to enable checking; launch/demo does not need a checker")
    substitutions = {
        "{model}": config["target"]["model_id"].strip(),
        "{display_name}": config["target"]["display_name"].strip(),
    }
    result: list[str] = []
    for value in config["availability"]["command"]:
        expanded = value
        for token, replacement in substitutions.items():
            expanded = expanded.replace(token, replacement)
        result.append(expanded)
    return result


def run_check(config: dict[str, Any], cwd: Path | None = None, quiet: bool = False) -> int:
    command = expanded_check_command(config)
    timeout = config["availability"].get("timeout_seconds", 90)
    try:
        completed = subprocess.run(command, check=False, timeout=timeout, cwd=cwd,
                                   stdout=subprocess.DEVNULL if quiet else None,
                                   stderr=subprocess.DEVNULL if quiet else None)
        return completed.returncode
    except FileNotFoundError as error:
        raise ConfigError(f"availability executable not found: {command[0]}") from error
    except subprocess.TimeoutExpired:
        return 124


def command_validate(args: argparse.Namespace) -> int:
    load_config(args.config.resolve())
    print(f"VALID {args.config.resolve()}")
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    runtime = prepare_runtime(args.config, args.cache_dir, args.refresh_avatars)
    print(f"PREPARED {runtime}")
    return 0


def command_build(args: argparse.Namespace) -> int:
    binary = build_popup(args.build_dir)
    print(f"BUILT {binary}")
    return 0


def command_launch(args: argparse.Namespace) -> int:
    runtime = prepare_runtime(args.config, args.cache_dir, args.refresh_avatars)
    binary = build_popup(args.build_dir) if not args.no_build else args.build_dir / "model-finder-popup"
    if not binary.is_file():
        raise ConfigError(f"popup binary not found: {binary}")
    return launch_popup(runtime, binary)


def command_check(args: argparse.Namespace) -> int:
    config = load_config(args.config.resolve())
    code = run_check(config, cwd=args.config.resolve().parent)
    status = "AVAILABLE" if code == 0 else ("UNAVAILABLE" if code == 1 else "CHECK_ERROR")
    print(f"{status} exit={code}")
    return code


def command_watch(args: argparse.Namespace) -> int:
    config = load_config(args.config.resolve())
    expanded_check_command(config)
    # One watcher per config in this cache. Hold the OS lock until the popup exits.
    import fcntl
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(str(args.config.resolve()).encode()).hexdigest()[:16]
    lock = (args.cache_dir / f"watch-{identity}.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise ConfigError("a watcher for this config is already running") from error
    try:
        runtime = prepare_runtime(args.config, args.cache_dir, args.refresh_avatars)
        binary = build_popup(args.build_dir) if not args.no_build else args.build_dir / "model-finder-popup"
        if not binary.is_file():
            raise ConfigError(f"popup binary not found: {binary}")
        return watch_loop(args, config, runtime, binary)
    finally:
        lock.close()


def watch_loop(args: argparse.Namespace, config: dict[str, Any], runtime: Path, binary: Path) -> int:
    interval = config["availability"]["interval_seconds"]
    attempt = 0
    previous_status = None
    while True:
        attempt += 1
        code = run_check(config, cwd=args.config.resolve().parent, quiet=not args.verbose)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if code == 0:
            print(f"{timestamp} AVAILABLE attempt={attempt}", flush=True)
            return launch_popup(runtime, binary)
        status = "UNAVAILABLE" if code == 1 else f"CHECK_ERROR exit={code}"
        if args.one_check:
            print(f"{timestamp} {status} attempt={attempt}", flush=True)
            return code
        if args.verbose or status != previous_status:
            print(f"{timestamp} {status} attempt={attempt}; retrying in {interval}s", flush=True)
        previous_status = status
        time.sleep(interval)


def command_render(args: argparse.Namespace) -> int:
    runtime = prepare_runtime(args.config, args.cache_dir, args.refresh_avatars)
    binary = build_popup(args.build_dir) if not args.no_build else args.build_dir / "model-finder-popup"
    if not binary.is_file():
        raise ConfigError(f"popup binary not found: {binary}")
    command = [str(binary.resolve()), str(runtime), "--render-states", str(args.output.resolve())]
    if args.no_cursor:
        command.append("--no-cursor")
    return subprocess.run(command, check=False).returncode


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    def config_command(name: str, handler: Any) -> argparse.ArgumentParser:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("config", type=Path)
        subparser.set_defaults(handler=handler)
        return subparser

    config_command("validate", command_validate)
    prepare = config_command("prepare", command_prepare)
    prepare.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    prepare.add_argument("--refresh-avatars", action="store_true")

    build = subparsers.add_parser("build")
    build.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    build.set_defaults(handler=command_build)

    launch = config_command("launch", command_launch)
    launch.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    launch.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    launch.add_argument("--refresh-avatars", action="store_true")
    launch.add_argument("--no-build", action="store_true")

    demo = subparsers.add_parser("demo", help="show the bundled simulated Astra party; no account check or network")
    demo.set_defaults(handler=command_launch, config=ROOT / "model-finder.example.json", refresh_avatars=False)
    demo.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    demo.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    demo.add_argument("--no-build", action="store_true")

    render = config_command("render", command_render)
    render.add_argument("--output", type=Path, default=ROOT / "dist" / "frames")
    render.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    render.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    render.add_argument("--refresh-avatars", action="store_true")
    render.add_argument("--no-build", action="store_true")
    render.add_argument("--no-cursor", action="store_true", help="keep hover states but do not paint a cursor (for video compositing)")

    config_command("check", command_check)
    watch = config_command("watch", command_watch)
    watch.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    watch.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    watch.add_argument("--refresh-avatars", action="store_true")
    watch.add_argument("--no-build", action="store_true")
    watch.add_argument("--one-check", action="store_true", help="run one check without sleeping")
    watch.add_argument("--verbose", action="store_true", help="print unchanged checks and checker output")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (ConfigError, OSError) as error:
        print(f"model-finder: {error}", file=sys.stderr)
        return 64
    except KeyboardInterrupt:
        print("model-finder: stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
