# Task 8 browser observations

**Historical scope:** These captures document the original Task 8 event screen.
The current schema-v3 pregame and halftime screens deliberately retain team
names and scores beneath the countdown, so the statements and images below are
pre-C3 evidence, not the current spectator layout contract.

September 4, 2026. Captured with installed headless Microsoft Edge 152.0.4191.62
using the bundled file pages and Python-produced view models. HTTP requests were
blocked. This is browser evidence, not a physical LED or two-display result.

Manual inspection of the linked images found separate, readable score/clock
regions, no cropped characters, and deliberate unused space around the portrait
canvas. The 24-character stress names wrap to two lines without touching scores.
The play clock remains a prominent lower-right readout. Pregame shows only
KICKOFF IN and its countdown; interval shows its supplied phase, title, time,
and the warmup note only during HALFTIME.

| Inspected capture | Viewport | Measured canvas | Horizontal safe inset | Observation |
|---|---|---|---|---|
| [Game](1280x720-3.png) | 1280 x 720 | 1280 x 720 | 51.19 px | 199/199 and 24 W characters per team fit |
| [Game](1366x768-3.png) | 1366 x 768 | 1365.33 x 767.98 | 54.61 px | Subpixel pillarbox; no stretched type |
| [Game](1920x1080-3.png) | 1920 x 1080 | 1920 x 1080 | 76.80 px | Same proportions and field separation |
| [Interval](390x844-5.png) | 390 x 844 | 390 x 219.38 | 15.59 px | Centered letterbox; HALFTIME and warmup note fit |
| [Pregame](1280x720-4.png) | 1280 x 720 | 1280 x 720 | 51.19 px | Only KICKOFF IN / 30:00 |
| [Warmup](1280x720-7.png) | 1280 x 720 | 1280 x 720 | 51.19 px | WARMUP / UNTIL SECOND HALF / 3:00; no halftime note |

All 36 automated viewport cases measured text bounding rectangles inside the
safe area and their layout boxes, no pairwise text overlaps, and document scroll
dimensions equal to viewport dimensions. A 0.5 CSS-pixel tolerance accounts for
subpixel rounding. The first pass exposed text-bound overlap; increasing line
spacing and reducing score/clock scale removed it before these captures.

[Exact captured measurements](measurements.json) accompany all 16 captures.
Capture suffixes: 3 = 199/199 game, 4 = pregame, 5 = 15:00 halftime,
7 = 3:00 warmup. Automated checks additionally render 0/99/100 scores and
3:01/0:00 interval boundaries at every viewport.

Pending: stadium geometry/overscan/readability, physical 1366 x 768 Windows
scaling under WebView2, two-display close/reopen/fullscreen, and measured
command-to-visible-pixels latency on the target laptop. The immediate push test
proves removal of the tick wait; it does not prove the 100/250 ms hardware target.
