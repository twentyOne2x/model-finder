# Rendering a shareable video

`scripts/render-video.mjs` turns the popup's rendered states into a 1280x800,
60 fps H.264/AAC video. It keeps the native reveal, smooth cursor movement,
click timing, overlapping party confirmations, and conservative audio headroom.

## Requirements

- Node.js 18 or newer
- `ffmpeg` on `PATH`
- ImageMagick's `magick` command on `PATH`
- macOS and the built popup binary when rendered states are not supplied

Override tool discovery with `MODEL_FINDER_FFMPEG` and
`MODEL_FINDER_MAGICK`, or pass `--ffmpeg` and `--magick` explicitly.
If your config selects the optional WoW media, run the repository's documented
`scripts/install-wow-media.py` setup first. The video renderer only uses local
paths from the prepared runtime; it does not fetch or embed remote assets by
itself.

## Render

First prepare a content-addressed runtime file and build the popup with the main
CLI. `prepare` prints the exact runtime path consumed by the renderer:

```sh
runtime_path="$(python3 model_finder.py prepare model-finder.example.json | sed 's/^PREPARED //')"
python3 model_finder.py build
node scripts/render-video.mjs \
  --runtime "$runtime_path" \
  --background /path/to/background.png \
  --output dist/model-finder.mp4 \
  --preset tweet
```

When `--states` is omitted, the script asks `.build/model-finder-popup` to
render the required frames through the runtime JSON. A different binary can be
selected with `--popup-binary`.

To compose already-rendered states, including on a machine that cannot run the
macOS popup:

```sh
node scripts/render-video.mjs \
  --runtime "$runtime_path" \
  --states .cache/rendered-states \
  --background /path/to/background.png \
  --output dist/model-finder.mp4 \
  --preset native
```

`--background` is always explicit: the renderer never captures the screen or
downloads media. If it is omitted, a neutral dark canvas is generated locally.

## Presets

- `tweet` is the default. It uses a 760x460 popup for feed legibility, encodes a
  readable 0.65-second opening cover, dissolves it, and replays the complete
  native entrance. The output is about 12.73 seconds.
- `native` uses a 430x260 popup to preserve its desktop-relative size and starts
  directly with the 0.34-second native entrance. The output is about 11.83
  seconds.

Both presets use the cursor and optional sounds named in `popup.theme` and
`popup.sounds` in the prepared runtime JSON; no project-specific filenames are
assumed. Missing sound fields produce a valid silent mix. Five confirmation
tags occur at 5.18, 6.33, 6.45, 8.18, and 8.30 seconds after the native entrance
begins, so some confirmations intentionally overlap.

By default the script also writes `*-preview.png`; the tweet preset writes the
literal first frame as `*-cover.png`. Pass `--no-preview` to create only the
video. Run `node scripts/render-video.mjs --help` for every option.
