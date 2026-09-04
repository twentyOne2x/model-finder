# Assets

This directory deliberately mixes three different provenance classes. Do not
assume that the repository's MIT license applies to every file here.

```text
assets/
  audio/       original WoW sounds installed locally; ignored by Git
  portraits/   retained snapshots for the named demo; separate rights
  theme/       generated frame/role art plus locally installed WoW cursors
```

The full rights and source record is in
[`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), with checksums in
[`../docs/asset-provenance.md`](../docs/asset-provenance.md).

## Restore the original demo media

A clean clone does not contain the Blizzard audio or cursor PNGs. Install
FFmpeg and ImageMagick so `ffmpeg` and `magick` are on `PATH`, review the linked
owner policies, then run:

```sh
python3 scripts/install-wow-media.py --accept-third-party-terms
```

The script uses only Python's standard library. It downloads five fixed,
checksum-pinned inputs, rejects unexpected sizes or SHA-256 values, converts
them without a shell, validates the normalized outputs, and targets only the
named asset paths under the selected project root. Downloads are temporary; the
original OGG and CUR files are not retained.

To install into a disposable or alternate project root:

```sh
python3 scripts/install-wow-media.py \
  --accept-third-party-terms \
  --output-root /absolute/path/to/model-finder-copy
```

Running it again is safe: valid outputs are checked and left in place. The
acknowledgement flag only records that you reviewed the policies. It does not
grant copyright, trademark, commercial, or redistribution rights.

## Bundled portraits

The five portrait snapshots are intentionally retained so the repository
reproduces the original Astra party. Four were resolved from public X profiles
through Unavatar; Billy's image was supplied in the originating task. They are
not presented as MIT-licensed stock images. Preserve the notice, verify your own
right to use them, or replace them before redistribution.

[Avatars provided by Unavatar](https://unavatar.io). Profile images can change or
resolve incorrectly, so review any refresh before using it.

## Generated theme art

The frame and tank/healer/DPS medallions are generated project art. Their exact
generation requests are kept in `docs/`. The frame used a World of Warcraft
Dungeon Finder screenshot as a layout reference, so generated does not mean
free of third-party design or derivative-work concerns.

## Replacing assets

For a version intended for broad redistribution or commercial use, point your
configuration at portraits, sounds, frame art, role icons, and cursors for which
you have the required rights. The reference assets use:

- square portraits (the bundled snapshots are 400 x 400);
- a 1611 x 976 frame plate;
- transparent 128 x 128 role medallions;
- 64 x 64 normal and active cursors; and
- stereo 16-bit PCM WAV at 44.1 kHz.

Other dimensions can work because the popup scales its inputs, but matching
those shapes preserves the original composition. Do not commit ignored media
merely to make a local demo portable unless you can document redistribution
permission.
