# Third-party media notices

Model Finder's MIT license applies to original code and documentation only. It
does not relicense the photographs, likenesses, World of Warcraft media, source
reference, names, trademarks, or other third-party material described here.
Those items remain subject to their owners' rights and terms.

This notice records provenance; it is not legal advice or a grant of rights.
The `--accept-third-party-terms` installer flag records that the caller reviewed
the linked policies. It does not mean that a use is permitted and does not
create, transfer, or expand any license.

## World of Warcraft audio

The following original game sounds are not stored in Git. The optional installer
downloads them from `wow.zamimg.com`, verifies the exact source bytes, and makes
local PCM WAV files for the popup:

| Upstream file | File data ID | Local purpose |
| --- | ---: | --- |
| [`levelup2.ogg`](https://wow.zamimg.com/sound-ids/live/enus/182/567478/levelup2.ogg) | 567478 | dungeon/model-ready sound |
| [`uCharacterSheetTab.ogg`](https://wow.zamimg.com/sound-ids/live/enus/126/567422/uCharacterSheetTab.ogg) | 567422 | Enter button sound |
| [`LFG_RoleCheck.ogg`](https://wow.zamimg.com/sound-ids/live/enus/217/567513/LFG_RoleCheck.ogg) | 567513 | party-member confirmation sound |

World of Warcraft and its game media are associated with Blizzard
Entertainment. CDN availability is not a redistribution license. Review
[Blizzard's Legal FAQ](https://www.blizzard.com/en-us/legal/c1ae32ac-7ff9-4ac3-a03b-fc04b8697010/blizzard-legal-faq)
and [Blizzard's Video Policy](https://www.blizzard.com/en-gb/legal/2068564f-f427-4c1c-8664-c107c90b34d5/blizzard-video-policy)
before using the files. The video policy addresses qualifying community videos;
it should not be read as blanket permission to redistribute extracted game
assets. Use your own licensed sounds if the owner policies do not cover your
intended use.

## World of Warcraft cursor art

The optional installer also downloads `gauntlet.cur` and
`gauntlet_active.cur` from
[Slackcraft/CraftCursors](https://github.com/Slackcraft/CraftCursors) at pinned
commit [`d6f03365925751fca2635f14bfd17d8058a4dd43`](https://github.com/Slackcraft/CraftCursors/tree/d6f03365925751fca2635f14bfd17d8058a4dd43),
then converts them locally to 64 x 64 PNGs.

CraftCursors does not contain a standard open-source license file. Its README
describes personal, fansite, non-commercial, and development use; excludes
certain commercial products; attributes the cursor images to Blizzard
Entertainment; and attributes its original code to Slackcraft.org. Read those
terms and Blizzard's policies for yourself. Neither CraftCursors nor its cursor
art is covered by this repository's MIT license. GitHub's
[licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
explains that the absence of a license normally leaves default copyright in
place.

## Portraits and likenesses

The real portrait snapshots are bundled because the project's creator expressly
requested that the original five-person demo remain intact. That request is not
represented as permission from every photographer, subject, platform, or other
rights holder. Public profile availability does not itself grant reuse rights,
and inclusion does not imply participation in or endorsement of this project.
No separate portrait or likeness permission record was found in the originating
task materials. [X's Terms of Service](https://x.com/en/tos) describe rights
retained by people who submit content and the license granted to X; they are not
a general-purpose license for third-party reuse.

| File | Person / public profile | Acquisition record |
| --- | --- | --- |
| `assets/portraits/tibo.jpg` | [Tibo](https://x.com/thsottiaux) | resolved through Unavatar on 2026-09-04 |
| `assets/portraits/andrew.jpg` | [Andrew](https://x.com/ajambrosino) | resolved through Unavatar on 2026-09-04 |
| `assets/portraits/victor.jpg` | [Victor](https://x.com/victornunez) | resolved through Unavatar on 2026-09-04 |
| `assets/portraits/sam.jpg` | [Sam](https://x.com/sama) | resolved through Unavatar on 2026-09-04 |
| `assets/portraits/billy.png` | Billy | supplied directly by the project's creator in the originating task |

Copyright and likeness rights remain with their respective owners. If you fork
or redistribute the demo, verify that your use is permitted, replace the images
where necessary, and honor a valid removal request.

The four public-profile snapshots were retrieved through Unavatar's public
resolver. [Avatars provided by Unavatar](https://unavatar.io). Its
[documentation](https://unavatar.io/docs) describes attribution and service
limits. That service attribution does not license the underlying portraits.

## Generated fantasy UI art

`assets/theme/wow-dungeon-finder-frame.png` and the three
`assets/theme/role-*.png` medallions were generated with OpenAI image generation
for this project. The frame was generated from a supplied World of Warcraft
Dungeon Finder screenshot used as a visual layout reference; the role medallions
were generated from text only. The exact requests are preserved in
[`docs/frame-prompt.md`](docs/frame-prompt.md) and
[`docs/role-icons-prompt.md`](docs/role-icons-prompt.md). The supplied frame
reference was downloaded from [CREO Community](https://www.creocommunity.de/wp-content/uploads/2024/01/Rangliste-der-zehn-besten-Dungeons-in-World-of-Warcraft.jpg).

Under [OpenAI's Terms of Use](https://openai.com/policies/terms-of-use/), as
between the user and OpenAI and to the extent permitted by applicable law, the
user owns output; the user remains responsible for ensuring that content and
use do not violate law or third-party rights, and output may not be unique. The
repository does not attempt to relicense rights held by Blizzard, the
reference-image owner, or anyone else in these generated outputs. The project's
MIT license remains scoped to original code and documentation.

## Names and trademarks

World of Warcraft, Warcraft, Blizzard, and related names and marks belong to
their respective owners. Astra, Codex, OpenAI, X, and other names and marks also
belong to their respective owners. Model Finder is an independent fan-made demo;
no affiliation, sponsorship, or endorsement is implied.

See [`docs/asset-provenance.md`](docs/asset-provenance.md) for the reproducible
source hashes and conversion records.
