import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import argparse
import subprocess
import sys
from prepare_fixture import create_fixture


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("model_finder", ROOT / "model_finder.py")
assert SPEC and SPEC.loader
MODEL_FINDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL_FINDER)


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "model-finder.example.json").read_text())

    def test_example_contract_is_valid(self) -> None:
        MODEL_FINDER.validate_config(self.config)

    def test_requires_exact_party_composition(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["members"][0]["role"] = "dps"
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "party composition"):
            MODEL_FINDER.validate_config(broken)

    def test_rejects_member_with_two_avatar_sources(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["members"][0]["x_handle"] = "thsottiaux"
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "exactly one"):
            MODEL_FINDER.validate_config(broken)

    def test_check_placeholders_are_argv_local(self) -> None:
        config = copy.deepcopy(self.config)
        config["availability"] = {"command": ["checker", "--model={model}", "{display_name}"]}
        self.assertEqual(
            MODEL_FINDER.expanded_check_command(config),
            ["checker", "--model=gpt-6-astra", "Astra"],
        )

    def test_local_paths_resolve_from_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            portrait = root / "face.png"
            portrait.write_bytes(b"not-used-by-validation")
            resolved = MODEL_FINDER._resolve_file("face.png", root, "portrait")
            self.assertEqual(resolved, str(portrait.resolve()))

    def test_online_example_is_valid(self):
        MODEL_FINDER.load_config(ROOT / "examples/from-x.json")

    def test_demo_requires_no_checker(self):
        self.assertNotIn("availability", self.config)
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "add availability"):
            MODEL_FINDER.expanded_check_command(self.config)

    def test_rejects_unknown_fields(self):
        for container, key in [(self.config, "typo"), (self.config["popup"], "destnation_url"), (self.config["members"][0], "avatar_url")]:
            container[key] = "unexpected"
            with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "unknown fields"):
                MODEL_FINDER.validate_config(self.config)
            del container[key]

    def test_rejects_bad_destinations(self):
        for url in ["file:///etc/passwd", "javascript:alert(1)", "https:", "https://user:pass@example.com", "codex:", "https://:", "https://example.com:bad", "https://[::1", "https://bad host"]:
            self.config["popup"]["destination_url"] = url
            with self.assertRaises(MODEL_FINDER.ConfigError):
                MODEL_FINDER.validate_config(self.config)

    def test_profile_urls_are_profile_only(self):
        self.assertEqual(MODEL_FINDER.profile_handle("https://x.com/thsottiaux"), "thsottiaux")
        self.assertEqual(MODEL_FINDER.profile_handle("https://twitter.com/sama/"), "sama")
        for url in ["http://x.com/sama", "https://x.com/sama/status/1", "https://x.com.evil.test/sama", "https://x.com/sama?x=1", "https://x.com/sama#x", "https://user@x.com/sama"]:
            with self.assertRaises(MODEL_FINDER.ConfigError):
                MODEL_FINDER.profile_handle(url)

    def test_duplicate_members_and_multiple_locals_rejected(self):
        self.config["members"][0]["name"] = "Billy"
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "duplicated"):
            MODEL_FINDER.validate_config(self.config)
        self.config["members"][0]["name"] = "Tibo"
        self.config["members"][0]["is_local"] = True
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "at most one"):
            MODEL_FINDER.validate_config(self.config)

    def test_numbers_and_controls_rejected(self):
        for value in [True, float("nan"), float("inf"), -1]:
            self.config["popup"]["idle_seconds"] = value
            with self.assertRaises(MODEL_FINDER.ConfigError):
                MODEL_FINDER.validate_config(self.config)
        self.config["popup"]["idle_seconds"] = 90
        self.config["members"][0]["name"] = "Tibo\x00"
        with self.assertRaises(MODEL_FINDER.ConfigError):
            MODEL_FINDER.validate_config(self.config)

    def test_timing_minimum_cannot_exceed_maximum(self):
        self.config["popup"]["confirmation_min_seconds"] = 7
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "cannot exceed"):
            MODEL_FINDER.validate_config(self.config)

    def test_bad_availability_rejected(self):
        for command in [[], "echo yes", ["echo", "\x00"]]:
            self.config["availability"] = {"interval_seconds": 600, "command": command}
            with self.assertRaises(MODEL_FINDER.ConfigError):
                MODEL_FINDER.validate_config(self.config)

    def test_missing_or_bad_json_is_readable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "missing.json"
            with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "not found"):
                MODEL_FINDER.load_config(config)
            config.write_text("{")
            with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "invalid JSON"):
                MODEL_FINDER.load_config(config)


class RuntimeTests(unittest.TestCase):
    def test_fixture_prepares_offline_with_real_portraits_and_generated_theme(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(MODEL_FINDER, "urlopen", side_effect=AssertionError("demo must be offline")):
            config = create_fixture(Path(directory) / "fixture.json")
            runtime_path = MODEL_FINDER.prepare_runtime(config, Path(directory))
            runtime = json.loads(runtime_path.read_text())
            self.assertEqual(len(runtime["members"]), 5)
            self.assertEqual(runtime["members"][-1]["name"], "Billy")
            self.assertEqual(runtime["members"][-1]["portraitZoom"], 1.23)
            self.assertEqual(runtime["popup"]["confirmationMaxSeconds"], 4.4)
            self.assertEqual(runtime["popup"]["destinationLabel"], "REPO")
            for member in runtime["members"]:
                self.assertTrue(Path(member["avatarPath"]).is_file())
            for asset in runtime["popup"]["theme"].values():
                self.assertTrue(Path(asset).is_file())
            self.assertTrue(all(value is None for value in runtime["popup"]["sounds"].values()))

    def test_runtime_names_are_content_addressed(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            config = create_fixture(cache / "fixture.json")
            first = MODEL_FINDER.prepare_runtime(config, cache)
            second = MODEL_FINDER.prepare_runtime(config, cache)
            self.assertEqual(first, second)
            self.assertEqual(len(list(cache.glob("runtime-*.json"))), 1)
            self.assertEqual(list(cache.glob(".model-finder-*")), [])

    def test_image_magic_rejects_html(self):
        self.assertEqual(MODEL_FINDER._image_extension(b"\x89PNG\r\n\x1a\n", "image/png"), ".png")
        with self.assertRaisesRegex(MODEL_FINDER.ConfigError, "supported image"):
            MODEL_FINDER._image_extension(b"<html>not an avatar", "text/html")

    def test_cached_avatar_requires_valid_image_and_handle(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            (cache / "avatars").mkdir()
            (cache / "avatars/x-test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            with patch.object(MODEL_FINDER, "urlopen", side_effect=AssertionError("no fetch for cache hit")):
                self.assertTrue(MODEL_FINDER.fetch_x_avatar("test", cache, False).is_absolute())
            with self.assertRaises(MODEL_FINDER.ConfigError):
                MODEL_FINDER.fetch_x_avatar("../bad", cache, False)

    def test_profile_resolution_maps_only_expected_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config = json.loads(create_fixture(folder / "fixture.json").read_text())
            del config["members"][0]["avatar"]
            config["members"][0]["profile_url"] = "https://x.com/thsottiaux"
            source = folder / "config.json"
            source.write_text(json.dumps(config))
            avatar = ROOT / "assets/portraits/tibo.jpg"
            with patch.object(MODEL_FINDER, "fetch_x_avatar", return_value=avatar) as fetch:
                runtime = json.loads(MODEL_FINDER.prepare_runtime(source, folder / "cache").read_text())
            fetch.assert_called_once_with("thsottiaux", folder / "cache", False)
            self.assertEqual(runtime["members"][0]["avatarSource"], "https://x.com/thsottiaux")


class CheckerTests(unittest.TestCase):
    def config(self, code):
        return {"target": {"model_id": "unit-test", "display_name": "Test"},
                "availability": {"interval_seconds": 600, "timeout_seconds": 5,
                                 "command": [sys.executable, "-c", f"raise SystemExit({code})"]}}

    def test_preserves_available_unavailable_and_error_exit_codes(self):
        for code in [0, 1, 7]:
            self.assertEqual(MODEL_FINDER.run_check(self.config(code), quiet=True), code)

    def test_timeout_is_error_not_unavailable(self):
        with patch.object(MODEL_FINDER.subprocess, "run", side_effect=subprocess.TimeoutExpired("checker", 5)):
            self.assertEqual(MODEL_FINDER.run_check(self.config(0)), 124)

    def test_no_implicit_shell_and_explicit_working_directory(self):
        config = self.config(0)
        config["availability"]["command"] = ["checker", "$(touch /tmp/should-not-exist)", "{model}"]
        with patch.object(MODEL_FINDER.subprocess, "run", return_value=Mock(returncode=1)) as run:
            self.assertEqual(MODEL_FINDER.run_check(config, cwd=ROOT), 1)
        args, kwargs = run.call_args
        self.assertEqual(args[0][1], "$(touch /tmp/should-not-exist)")
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["cwd"], ROOT)

    def test_watch_launches_once_then_returns_popup_failure_without_retry(self):
        args = argparse.Namespace(config=ROOT / "model-finder.example.json", verbose=False, one_check=False)
        with patch.object(MODEL_FINDER, "run_check", side_effect=[1, 0]) as check, \
             patch.object(MODEL_FINDER.time, "sleep") as sleep, \
             patch.object(MODEL_FINDER, "launch_popup", return_value=69) as launch:
            code = MODEL_FINDER.watch_loop(args, self.config(0), Path("runtime"), Path("binary"))
        self.assertEqual(code, 69)
        self.assertEqual(check.call_count, 2)
        sleep.assert_called_once_with(600)
        launch.assert_called_once()

    def test_one_check_never_sleeps_or_launches_on_error(self):
        args = argparse.Namespace(config=ROOT / "model-finder.example.json", verbose=False, one_check=True)
        with patch.object(MODEL_FINDER, "run_check", return_value=124), \
             patch.object(MODEL_FINDER.time, "sleep") as sleep, \
             patch.object(MODEL_FINDER, "launch_popup") as launch:
            self.assertEqual(MODEL_FINDER.watch_loop(args, self.config(0), Path("runtime"), Path("binary")), 124)
        sleep.assert_not_called()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
