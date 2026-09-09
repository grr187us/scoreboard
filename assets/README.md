# Static assets

Store only versioned assets that the project owns or is licensed to redistribute. Record source and license information for third-party fonts, logos, images, audio, or video before committing them.

Generated media, recordings, replay captures, local team packages, and machine-specific content do not belong here and are ignored where practical.

## Bundled assets and their provenance

Everything the spectator boards load at game time ships inside
`src/scoreboard/views/shared/` -- nothing is fetched over the network
(`docs/PACKAGING.md`, W-002). `tools/build_package.py` verifies each file is in
the built package and `tests/integration/test_packaging.py` keeps the list from
drifting.

### Fonts (`src/scoreboard/views/shared/fonts/`)

| File | Face | Weight | Licence | Source |
|---|---|---|---|---|
| `Graduate-Regular.ttf` | Graduate (copyright 2012 The Graduate Project Authors, Eduardo Tunni) | 400 | SIL Open Font License 1.1 (`Graduate-OFL.txt`) | google/fonts, `ofl/graduate` |
| `BarlowCondensed-Medium.ttf` | Barlow Condensed (copyright 2017 The Barlow Project Authors, Jeremy Tribby) | 500 | SIL Open Font License 1.1 (`Barlow-OFL.txt`) | google/fonts, `ofl/barlowcondensed` |
| `BarlowCondensed-SemiBold.ttf` | Barlow Condensed (copyright 2017 The Barlow Project Authors, Jeremy Tribby) | 600 | SIL Open Font License 1.1 (`Barlow-OFL.txt`) | google/fonts, `ofl/barlowcondensed` |
| `BarlowCondensed-Bold.ttf` | Barlow Condensed (copyright 2017 The Barlow Project Authors, Jeremy Tribby) | 700 | SIL Open Font License 1.1 (`Barlow-OFL.txt`) | google/fonts, `ofl/barlowcondensed` |

Both families are declared by `@font-face` in `views/shared/board.css` and
exposed to the layout editor as the `graduate` and `barlow_condensed` font
families (`scoreboard.presentation.layout.FONT_FAMILIES`). Barlow Condensed was
added on September 8, 2026 for the Broadcast Welcome pre-game and halftime
screens; Graduate on September 7, 2026 for the Scoreboard Grid preset. The OFL
permits bundling and redistribution with the licence text alongside, which is
why each `*-OFL.txt` ships next to its font. Jersey M54 is deliberately **not**
bundled (personal-use licence); the `varsity` stack only prefers it when the
operator has installed it.

### Images (`src/scoreboard/views/shared/img/`)

| File | What | Rights | Source |
|---|---|---|---|
| `tigers-crest.png` | TMSA Tigers crest, 218x174 | Owner-supplied reference; rights to be confirmed with the school before any public use | Copy of `brand-baseline/official-logo-reference.png`, supplied by the owner on September 4, 2026 |

The crest is referenced by layout image elements as `asset:tigers-crest`
(`scoreboard.presentation.layout.BUNDLED_IMAGES`) and resolved by `board.js`
to `shared/img/tigers-crest.png`; nothing about it is stored in a layout
document. The same wording as `brand-baseline/README.md` applies: it is a
reference mark, not a cleared asset, until the school confirms.
