# Asset provenance and integrity manifest

This is the reproducibility record for the media in the original Astra Model
Finder demo. SHA-256 values identify the exact bytes acquired or bundled on
2026-09-04. They are integrity pins, not evidence of permission. Rights and
policy notes are in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Original game audio installed locally

The installer downloads each OGG into a private temporary directory, checks its
byte length and SHA-256, and runs this equivalent FFmpeg transform:

```text
ffmpeg -nostdin -y -hide_banner -loglevel error -i INPUT \
  -c:a pcm_s16le -ar 44100 -ac 2 OUTPUT.wav
```

It validates WAV format, sample count, and the SHA-256 of decoded PCM samples.
The container-level WAV hashes below are from the original 2026-09-04 build and
are informational; FFmpeg metadata can make whole-file bytes tool-dependent.

### Dungeon/model-ready sound

- Source: [`levelup2.ogg`](https://wow.zamimg.com/sound-ids/live/enus/182/567478/levelup2.ogg)
- World of Warcraft file data ID: `567478`
- Source length: `60,724` bytes
- Source SHA-256: `1153339e3d4fab1cfcb2c37ab3781462b517f6c69616c6e2b4326b76c73d1e68`
- Local output: `assets/audio/wow-dungeon-ready-567478.wav`
- Output format: stereo, 16-bit PCM, 44,100 Hz, `221,399` frames
- PCM SHA-256: `e9c45ac52cc02045f7ff988a35f1ea7e255de36843e6e5b2bd7060e483c4c6c2`
- Original build WAV SHA-256: `f300a4a48d60c000f23a6863b7e1f77e929553c04d3c5cd489ce97efd6ab4ab7`

### Enter button sound

- Source: [`uCharacterSheetTab.ogg`](https://wow.zamimg.com/sound-ids/live/enus/126/567422/uCharacterSheetTab.ogg)
- World of Warcraft file data ID: `567422`
- Source length: `4,753` bytes
- Source SHA-256: `1752f34b3f0af011fcc87d48524b86af76bf6d38f888cdf68da972aaa6541e50`
- Local output: `assets/audio/wow-enter-dungeon-click-567422.wav`
- Output format: stereo, 16-bit PCM, 44,100 Hz, `8,960` frames
- PCM SHA-256: `c0d0cb205e6e9d1ae28f3a7e5b45b701846422ac667c15f15cf7f1a273e1640f`
- Original build WAV SHA-256: `3f1497ac61e921e7da06d67f3eae4e07aa8412893f6a3cbbb30abd86edc63b17`

### Party-member confirmation sound

- Source: [`LFG_RoleCheck.ogg`](https://wow.zamimg.com/sound-ids/live/enus/217/567513/LFG_RoleCheck.ogg)
- World of Warcraft file data ID: `567513`
- Source length: `29,481` bytes
- Source SHA-256: `77e24671b9507fa7e6fd239aa1ac8999d5a04cbd32255dc87079829e59b25f4a`
- Local output: `assets/audio/wow-party-member-confirm-567513.wav`
- Output format: stereo, 16-bit PCM, 44,100 Hz, `138,240` frames
- PCM SHA-256: `0091289aecd16cc9a5eebb026d12c24a3a88cb0d56e0912668c5cce3da48a545`
- Original build WAV SHA-256: `d29516f74d5168289c70d24b65fab17f5527634df86379c536a43dc487d0cace`

## World of Warcraft cursors installed locally

- Upstream repository: [`Slackcraft/CraftCursors`](https://github.com/Slackcraft/CraftCursors)
- Pinned commit: [`d6f03365925751fca2635f14bfd17d8058a4dd43`](https://github.com/Slackcraft/CraftCursors/tree/d6f03365925751fca2635f14bfd17d8058a4dd43)
- Local conversion: ImageMagick CUR to PNG, then point-filter resize to
  exactly 64 x 64 pixels.

### Normal cursor

- Source: [`assets/cur/gauntlet.cur`](https://raw.githubusercontent.com/Slackcraft/CraftCursors/d6f03365925751fca2635f14bfd17d8058a4dd43/assets/cur/gauntlet.cur)
- Source length: `4,286` bytes
- Source SHA-256: `caa4d4954e6a685cb8e64651402d58db3ddfe3c7d2327c63066b0783722e1491`
- Local output: `assets/theme/wow-gauntlet-cursor@2x.png`
- ImageMagick pixel signature at 64 x 64:
  `ff5284ab589e66a1bd4a72585a3e7e985167e45b274736b20b8a3af8c2fd820c`

### Active cursor

- Source: [`assets/cur/gauntlet_active.cur`](https://raw.githubusercontent.com/Slackcraft/CraftCursors/d6f03365925751fca2635f14bfd17d8058a4dd43/assets/cur/gauntlet_active.cur)
- Source length: `4,286` bytes
- Source SHA-256: `748822c7104718f3403e515ec1295cfc3a04cf5b89c0f60ecafd893f2656a370`
- Local output: `assets/theme/wow-gauntlet-cursor-active@2x.png`
- ImageMagick pixel signature at 64 x 64:
  `ab0baba589d071e9ee146b28a538342d0a7875217c70804708c1c24dda8d0dac`

PNG file hashes are deliberately not pinned because ImageMagick can embed
time-dependent container metadata. The installer checks rendered dimensions and
pixel signatures instead.

## Retained portrait snapshots

Four profile pictures were requested from Unavatar's X resolver on 2026-09-04.
The profile URL is the human-review source; the resolver URL records the network
path used for the snapshot. Billy's image came from a user-supplied task
attachment. No embedded author or copyright metadata was found in these files.

| Local file | Public profile / source | Resolver | SHA-256 |
| --- | --- | --- | --- |
| `assets/portraits/tibo.jpg` | [`@thsottiaux`](https://x.com/thsottiaux) | [`unavatar.io/x/thsottiaux`](https://unavatar.io/x/thsottiaux) | `94f7a3d5cf0f68d1ffad703a3856e22af4ad41e04ffaf5fb808e45c65fb04bfc` |
| `assets/portraits/andrew.jpg` | [`@ajambrosino`](https://x.com/ajambrosino) | [`unavatar.io/x/ajambrosino`](https://unavatar.io/x/ajambrosino) | `5455f24f08fbc5e33eb92afd0fa70251d8f582e11e63a1c1f9e3aac8bbe31e98` |
| `assets/portraits/victor.jpg` | [`@victornunez`](https://x.com/victornunez) | [`unavatar.io/x/victornunez`](https://unavatar.io/x/victornunez) | `9dc51ed778b12d35c79cfcd60c1ea53682dfd78d66f6ae16a7e2e73e1505320e` |
| `assets/portraits/sam.jpg` | [`@sama`](https://x.com/sama) | [`unavatar.io/x/sama`](https://unavatar.io/x/sama) | `0bc416b53db7d0c6d572ac5ca8043e285420fae428f4cf644f9a7f9045e7c58b` |
| `assets/portraits/billy.png` | user-supplied attachment | not applicable | `98a0ab5a3e510a15a96784950cdf0bdc3d2720928d9e042e736c7d6c9b052af2` |

[Avatars provided by Unavatar](https://unavatar.io). Service attribution does
not grant rights in the resolved images.

## Generated theme art

### Frame plate

- Local file: `assets/theme/wow-dungeon-finder-frame.png`
- Dimensions: 1611 x 976 RGB PNG
- SHA-256: `c6c9a8efb2f286f7d45c068d0eb31a33856f8b1878df006f4d40b9084a104479`
- Generator: OpenAI image generation, run in the originating Codex task
- Exact request: [`frame-prompt.md`](frame-prompt.md)
- Supplied visual-layout reference:
  [`Rangliste-der-zehn-besten-Dungeons-in-World-of-Warcraft.jpg`](https://www.creocommunity.de/wp-content/uploads/2024/01/Rangliste-der-zehn-besten-Dungeons-in-World-of-Warcraft.jpg)

### Role medallions

- Generator: OpenAI image generation, text-only request in the originating
  Codex task
- Exact request: [`role-icons-prompt.md`](role-icons-prompt.md)
- Generated source strip SHA-256:
  `1cac6c4e7c8cb893411e7d828a0cbe50b13176b652461726b0e096c1652bf506`
- The 384 x 128 source strip was split into three 128 x 128 RGBA PNGs:

| Local file | SHA-256 |
| --- | --- |
| `assets/theme/role-tank.png` | `208096abb638501c98761388895ee98312629353a9636da517886734b8ed7b17` |
| `assets/theme/role-healer.png` | `1abc310809135331e9a63849b7e3c99b3dd15e54eea16939b82dc8d6267351b6` |
| `assets/theme/role-dps.png` | `4ab323f7fc9d0fb02e200208c99d2ea6c7c7eae19824daa4f4b12c7dbc0a34e0` |

## What is intentionally absent

- The downloaded OGG and CUR inputs are temporary and never copied into the
  project.
- The converted Blizzard audio and cursor PNGs are ignored by Git and restored
  only by explicit local setup.
- Avatar resolver caches, generated runtime JSON, binaries, videos, private
  background captures, absolute local paths, and task/thread identifiers are not
  release assets.
