# High School Football LED Scoreboard — Project Roadmap

> **Document purpose:** This is the living command-center document for the scoreboard project. It records the current plan, phase status, major decisions, unanswered questions, and the next concrete action.
>
> **Last updated:** September 4, 2026

## How to Use This Document

| Practice | Meaning |
|---|---|
| Update after meaningful work | Record completed tests, decisions, newly discovered constraints, and phase changes. |
| Separate facts from assumptions | A likely answer is not treated as confirmed until it has been tested or documented. |
| Keep near-term work detailed | The current and next phase should be specific. Later phases should stay flexible until earlier findings justify more detail. |
| Require a definition of done | A phase is complete only when its stated exit criteria have been met. |
| Prefer small experiments | Use inexpensive tests to answer uncertain architectural questions before committing to large implementations. |

## Status Key

| Status | Meaning |
|---|---|
| ✅ Complete | Finished and verified. |
| 🟡 In progress | Active work is underway. |
| ⏳ Pending | Planned but not started. |
| 🧪 Needs testing | Believed to be true but requires evidence. |
| ⛔ Blocked | Cannot continue until a dependency or decision is resolved. |
| ➖ Deferred | Intentionally postponed to protect the MVP scope. |

## Project North Star

Build a reliable, offline-capable, and extremely easy-to-operate football scoreboard and LED video-production system for a high-school stadium.

The system may eventually support sophisticated graphics, videos, sponsor content, replays, multiple operators, and the existing physical controller. The first priority is much smaller: prove that a dependable custom scoreboard can be displayed through the stadium's existing HDMI-to-LED signal chain.

**Guiding principle:** Reuse what already works. Build only what differentiates our system.

## Project Guardrails

| Guardrail | Practical effect |
|---|---|
| Reliability over features | A smaller system that survives an entire game is more valuable than an impressive but fragile system. |
| Offline core operation | Scoring and clocks must not depend on internet access or cloud services. |
| Preserve the vendor system | Do not modify, remove, bypass, or interfere with the licensed vendor system or USB key. Keep it available as a fallback. |
| HDMI is the preferred boundary | Treat the LED processor and wall as an existing display system unless testing proves that direct hardware integration is required. |
| Separate responsibilities | Keep game state, game rules, presentation, operator controls, media production, and hardware integrations logically separate. |
| Limit the MVP | Do not add replays, advanced statistics, networking, physical-controller support, or elaborate media tools before the core scoreboard is proven. |
| Correctness over visual polish | Clock and score behavior must be trustworthy before advanced animations or styling. |
| Human-friendly operation | Controls must be clear enough for a student or volunteer to use during a live game. |

## Current Understanding

| Type | Item | Status / Confidence |
|---|---|---|
| Known | The current vendor system uses a Windows 11 laptop and sends video to a processor through HDMI. | Confirmed |
| Known | The processor has four HDMI inputs and physical input-selection controls. | Confirmed by observation; model still unknown |
| Known | Two RJ45-style cables leave the processor, and disconnecting either one blanks one half of the LED wall. | Confirmed by experiment |
| Known | The existing physical scoreboard controller connects to the vendor computer through USB. | Confirmed |
| Known | The local project is initialized as a Git repository on `main`; the target GitHub repository advertised no branches or commits when inspected. | Confirmed September 4, 2026; initial commit/push tracked below |
| Hypothesis | A normal Windows laptop can drive the entire LED wall through an available HDMI input. | Approximately 90% confidence; not yet tested |
| Hypothesis | The LED wall can be treated as one conventional display target, allowing the internal LED protocol to remain irrelevant. | Depends on the HDMI test |
| Decision | Use one authoritative Python process with managed HTML/CSS/JavaScript operator and spectator webview windows for Phase 2. | Documented in `docs/ARCHITECTURE.md`; Windows host proof is Task 1 |
| Undecided | OBS Studio should be part of the system. | Evaluate after the core scoreboard works |
| Deferred | Existing physical-controller integration | Not part of the initial MVP |

## Phase Overview

| Phase | Name | Primary outcome | Current status |
|---:|---|---|---|
| 0 | Discovery and feasibility | Validate the project boundary and document the existing system. | 🟡 Substantially complete; one critical HDMI test remains |
| 1 | Repository, requirements, and architecture | Establish a clean project foundation and an implementation-ready MVP design. | 🟡 In progress; foundation drafted, confirmations and synchronization verification remain |
| 2 | Core scoreboard MVP | Produce a dependable local Windows scoreboard with correct football controls and fullscreen output. | ⏳ Pending |
| 3 | Production graphics and OBS/media integration | Add controlled media, scenes, custom cutscenes, and polished presentation without compromising the core scoreboard. | ➖ Deferred |
| 4 | External controls and expanded operation | Investigate and integrate the physical controller and other operator-control options. | ➖ Deferred |
| 5 | Stadium production hardening | Validate full-game reliability, recovery, deployment, operating procedures, and fallback behavior. | ➖ Deferred |

---

## Phase 0 — Discovery and Feasibility

**Goal:** Establish whether custom software can use the existing processor and LED wall as a normal HDMI display, while documenting enough of the current hardware to make safe decisions.

### Phase 0 Checklist

| Work item | Status | Evidence or next action |
|---|---|---|
| Define the project goal and reliability principles | ✅ Complete | Recorded in the project instructions and knowledge base. |
| Document the suspected signal chain | ✅ Complete | Windows computer → HDMI → processor → two RJ45-style links → LED wall. |
| Confirm that the two outbound links serve different wall sections | ✅ Complete | Disconnecting either link blanked the top or bottom half. |
| Establish the vendor system as the protected fallback | ✅ Complete | No license bypass or disruptive modification is planned. |
| Define the intentionally small MVP boundary | ✅ Complete | Basic football scoreboard, clock, play clock, quarter, team names, and local controls. |
| Identify candidate architectures and open-source starting points | ✅ Complete | Candidates recorded; Phase 1 later selected a managed-webview hybrid after review. |
| Test a personal Windows laptop through an available processor HDMI input | 🧪 Needs testing | Planned for Tuesday, September 8, 2026. |
| Confirm the entire Windows desktop appears across the LED wall | 🧪 Needs testing | This is the critical Phase 0 gate. |
| Record Windows-reported resolution, refresh rate, scaling, and orientation | 🧪 Needs testing | Capture screenshots or photographs during the HDMI test. |
| Record processor make, model, connections, and visible configuration | 🧪 Needs testing | Photograph the front, rear, labels, adapters, and connected cables. |

### Phase 0 HDMI Test — Minimum Evidence to Capture

| Check | What to record | Pass condition |
|---|---|---|
| Source detection | Whether Windows detects a second display and how it identifies it | The processor presents a usable display target |
| Full-wall image | Photograph of the Windows desktop or test image on the entire wall | Both halves display one correctly assembled image |
| Resolution | Windows display resolution and active signal resolution | A stable, usable mode is available |
| Refresh rate | Windows-reported refresh rate | Stable image without visible sync problems |
| Scaling | Windows scaling percentage | Scaling behavior is known and reproducible |
| Geometry | Cropping, stretching, seams, offset, or unused pixels | Problems are absent or can be characterized |
| Stability | Leave the desktop visible and exercise normal window movement/video briefly | No dropouts, resync loops, or obvious instability |
| Hardware identity | Processor manufacturer/model and cable/adapter photos | Enough information exists to locate manuals later |
| Recovery | Disconnect/reconnect or reselect the input if safe to do so | The source returns without complicated recovery |

### Phase 0 Definition of Done

Phase 0 is complete when the personal laptop successfully displays a stable, correctly mapped image across the entire LED wall **and** the display settings and processor identity have been recorded. If the test fails, Phase 0 remains open and the observed failure becomes the next architectural investigation.

---

## Phase 1 — Repository, Requirements, Layout, and Architecture

**Goal:** Create a clean, synchronized development foundation and define the smallest application that is ready to implement without prematurely designing the full production system.

**Important constraint:** Phase 1 produces decisions, requirements, project structure, and narrow technical proofs. It should not quietly grow into the complete scoreboard.

### 1.1 Repository Creation and GitHub Synchronization

| Work item | Expected result | Status |
|---|---|---|
| Choose the repository name | A short, durable name that is not tied to a temporary implementation choice such as OBS | ✅ `scoreboard` |
| Create a local Git repository | The working project has version history and a deliberate default branch | 🟡 Repository initialized on `main`; initial commit tracked by this Phase 1 task |
| Create the GitHub repository | Private or public visibility is explicitly selected | 🟡 Repository exists and advertised no commits; visibility still requires owner confirmation |
| Connect local and GitHub repositories | Local commits can be pushed and pulled successfully | 🟡 Target verified as empty; add/push `origin` and clean-clone verification remain |
| Add a practical `.gitignore` | Python environments, caches, logs, local settings, generated media, OBS profiles, and secrets are excluded as appropriate | ✅ Added and reviewed |
| Add a human-readable `README.md` | Purpose, current status, setup instructions, run instructions, and MVP scope are clear | ✅ Added; explicitly pre-implementation |
| Add a license or record that the repository is private/unlicensed | Reuse expectations are unambiguous | ✅ README records that no license is selected; visibility/license choice remains open |
| Establish a simple branch policy | Prefer small branches and reviewed merges; avoid unnecessary workflow complexity | ✅ Recorded in README and agent instructions |
| Verify a clean clone/setup | The project can be cloned into a new folder and prepared using documented steps | ⏳ Pending |

### 1.2 MVP Requirements

| Requirement area | Questions to resolve in Phase 1 | Required output |
|---|---|---|
| Game clock | Starting value, count direction, start/stop behavior, editing, expiration, tenths, and quarter transitions | Written clock behavior specification |
| Play clock | 25/40-second presets, start/stop/reset behavior, visibility, expiration, and independence from game clock | Written play-clock specification |
| Scoring | Required increments, subtraction/correction, maximum display width, and accidental-input handling | Scoring rules and control list |
| Quarter | Allowed values, overtime representation, and whether changes are manual | Quarter behavior specification |
| Team identity | Editable names, abbreviations, colors, and persistence between launches | MVP team-setting requirements |
| Operator input | Mouse controls, keyboard shortcuts, focus behavior, and prevention of browser/OS shortcut conflicts | Input map |
| Display output | Fullscreen behavior, target monitor selection, aspect-ratio handling, and safe margins | Display requirements |
| Recovery | Behavior after closing, crashing, restarting, or losing the display connection | Minimum recovery requirement |
| Persistence | Which values survive restart and when state is saved | Persistence rules |
| Logging | Which operator actions and system events are recorded | Minimal event-log/logging requirement |
| Offline operation | Packages, assets, fonts, and runtime behavior without internet | Offline checklist |
| Accessibility/usability | Button size, contrast, dangerous-action treatment, and running/stopped clock indication | Operator usability checklist |

The testable baseline is now in [`docs/MVP_REQUIREMENTS.md`](docs/MVP_REQUIREMENTS.md). It includes conservative provisional defaults so implementation can proceed, while preserving owner confirmation for official clock rules, tenths, accuracy tolerance, and play-clock reset/start semantics.

### 1.3 Application Layout and Operator Workflow

| Deliverable | What it should answer | Status |
|---|---|---|
| Display-board wireframe | What spectators see and how the layout adapts to the confirmed LED resolution | ✅ Resolution-independent baseline in `docs/UX_AND_LAYOUT.md`; stadium geometry remains open |
| Operator-screen wireframe | Where primary controls live and which information is visible at a glance | ✅ Baseline in `docs/UX_AND_LAYOUT.md`; owner/operator review remains |
| Control hierarchy | Which actions are frequent, occasional, corrective, or dangerous | ✅ Documented |
| Keyboard map | Which shortcuts are fast, memorable, and unlikely to be triggered accidentally | ✅ Provisional, testable map documented; rehearsal may revise it |
| Basic game workflow | Pregame setup → kickoff → normal operation → quarter change → halftime → game end | ✅ Documented |
| Error-correction workflow | How an operator fixes an incorrect score, clock, quarter, or team setting | ✅ Undo, minus, and confirmed direct-set paths documented |
| Display-loss workflow | What the operator does if the fullscreen display closes or the HDMI signal disappears | ✅ Continue authority, alert operator, explicit reopen/reselect workflow documented |

### 1.4 Architecture Decision

| Candidate | Strengths to validate | Concerns to validate | Phase 1 decision |
|---|---|---|---|
| Python game engine + local web renderer | Clear separation, familiar tools, flexible graphics, future WebSocket/API path | Packaging, browser fullscreen behavior, clock authority, multiple-process complexity | ✅ Selected as a one-process managed-webview hybrid |
| HTML/CSS/JavaScript-only local app | Very small initial footprint and strong presentation tools | Reliable persistence, authoritative timing, packaging, future integrations | ➖ Rejected as authoritative core; web presentation retained |
| Python-native desktop/rendering | Single runtime and direct local control | Visual/media flexibility, layout effort, future OBS/browser integration | ➖ Rejected for presentation; native webview hosting retained |
| Adapt an existing open-source project | May save time and provide proven workflows | License, code quality, football completeness, maintainability, Windows support | ➖ Rejected for adoption after six-repository review; borrow concepts only |
| OBS-centered core | Mature scenes, media, and transitions | Configuration burden and unnecessary dependency for basic scoring | ➖ Deferred to Phase 3; not an MVP dependency |
| Hybrid: Python authority + managed web views | One process, testable state/clocks, flexible presentation, controlled Windows windows | pywebview/WebView2 and packaging require an early proof | ✅ Recommended for Phase 2 |

The architecture decision should explicitly identify:

| Decision area | Required answer |
|---|---|
| Authoritative state | Which component owns scores, clocks, quarter, and team settings? |
| Clock model | How is elapsed time calculated without accumulating timer drift? |
| Communication | If controls and display are separate, how do they exchange state locally? |
| Process model | How many applications/processes must an operator start? |
| Packaging | How will the system run on Windows without a developer setup? |
| Display targeting | How will the output reliably open on the correct monitor in fullscreen? |
| Persistence | Where is configuration and recoverable game state stored? |
| Failure behavior | What remains visible and recoverable when a component fails? |
| Extension boundary | How can OBS, media, or physical controls be added later without rewriting game logic? |

### 1.5 Open-Source Evaluation

Evaluate the known candidates before deciding whether to build or adapt. Research should use repository code, licenses, documentation, issues, and recent activity—not screenshots or feature claims alone.

| Evaluation criterion | Why it matters |
|---|---|
| License | Determines whether code can legally be reused or modified. |
| Recent maintenance | Reduces the risk of adopting abandoned dependencies or broken setup instructions. |
| Football rules and controls | A visually attractive overlay may not provide usable game operation. |
| Architecture | Game state and presentation should be reusable independently. |
| Windows and offline support | These are core operating requirements. |
| Clock implementation | Timing must resist drift and support reliable pause/resume/correction. |
| OBS coupling | OBS support is helpful later but should not make the core scoreboard fragile. |
| Packaging/setup | A live operator should not need a development environment. |
| Test coverage and code clarity | Codex-assisted changes still need understandable, verifiable foundations. |
| Meaningful reuse | Adopt only if it saves more effort than it creates. |

✅ Six candidate repositories were inspected at recorded commits. Findings and per-candidate recommendations are in [`docs/OPEN_SOURCE_REVIEW.md`](docs/OPEN_SOURCE_REVIEW.md). No code was copied; missing and conflicting licenses are explicitly recorded.

### 1.6 Initial Project Structure

The Phase 2 architecture is selected, but implementation modules remain uncreated until their backlog task needs them. The structure preserves these concerns:

| Concern | Responsibility |
|---|---|
| Game state | Scores, clocks, quarter, team identity, and validation |
| Game logic | Legal state transitions and football-specific behavior |
| Operator interface | Human controls and correction workflows |
| Display renderer | Spectator-facing scoreboard presentation |
| Configuration | Teams, defaults, display selection, and local settings |
| Persistence/logging | Restart recovery and a record of important actions |
| Integrations | Future OBS, media, controller, or external-device adapters |
| Tests | Clock, scoring, state transitions, persistence, and launch behavior |
| Documentation | Setup, operation, recovery, and architecture decisions |

✅ The minimal boundary directories and a dependency-directed Phase 2 tree are documented in [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md). Only useful boundary README files were created; feature modules remain for the ordered backlog.

### 1.7 Narrow Technical Proofs

Only create a technical proof when it answers a decision that documents alone cannot resolve.

| Proof | Question answered | Success condition |
|---|---|---|
| Fullscreen display proof | Can the chosen renderer open cleanly on a selected Windows display? | Repeatable fullscreen launch without browser chrome or manual rearrangement |
| Clock proof | Can the chosen timing model pause/resume accurately without cumulative drift? | Measured behavior stays within the agreed tolerance |
| Local state update proof | Can operator actions update the display immediately and predictably? | Fast, ordered, observable state changes |
| Restart proof | Can the application restore a safe state after restart? | Documented restart behavior works consistently |

### 1.8 Phase 1 Deliverables

| Deliverable | Definition | Status / evidence |
|---|---|---|
| Synchronized repository | Local and GitHub repositories are connected and a clean clone works. | 🟡 Initial commit, push, and clean-clone verification are the remaining repository checks. |
| MVP requirements | Ambiguous behavior has been resolved and written down. | 🟡 Testable provisional baseline in `docs/MVP_REQUIREMENTS.md`; owner-only clock decisions remain. |
| Display and operator wireframes | Layouts are understandable before visual polish begins. | ✅ `docs/UX_AND_LAYOUT.md`; owner/operator agreement still requested before UI build. |
| Architecture decision record | Selected approach, rejected alternatives, tradeoffs, and extension boundaries are documented. | ✅ `docs/ARCHITECTURE.md`. |
| Project skeleton | Minimal structure exists for the selected architecture. | ✅ Source/test/asset boundaries exist without feature code; detailed tree in `docs/PROJECT_STRUCTURE.md`. |
| Testing strategy | Core logic, UI behavior, fullscreen output, and recovery have explicit test approaches. | ✅ Requirements, architecture, and backlog contain verification methods. |
| Phase 2 implementation backlog | Small, ordered tasks exist with acceptance criteria. | ✅ Twelve bounded tasks in `docs/PHASE_2_BACKLOG.md`. |

### Phase 1 Definition of Done

Phase 1 is complete when a fresh Windows checkout can be prepared from documented instructions; the MVP behavior and operator workflow are unambiguous; display and control layouts are agreed upon; the core architecture has been selected with written tradeoffs; and Phase 2 has a small, testable implementation backlog.

---

## Phase 2 — Core Scoreboard MVP

**Goal:** Deliver the smallest reliable local scoreboard that can be operated on Windows and displayed fullscreen on a monitor, television, and then the stadium LED wall.

| Planned capability | Current scope |
|---|---|
| Authoritative game state | Home/away scores, game clock, play clock, quarter, and team names |
| Reliable clocks | Start, stop, reset, edit/correct, and accurate elapsed-time calculation |
| Scoring controls | Required football increments plus safe correction/undo behavior |
| Operator interface | Clear mouse controls and documented keyboard shortcuts |
| Spectator display | Readable fullscreen layout designed for the confirmed wall geometry |
| Local persistence | Safe recovery of the agreed state after an interruption |
| Event logging | Important control actions and failures recorded locally |
| Offline packaging | Repeatable Windows installation and launch without internet access |
| Verification | Automated logic tests plus monitor/TV and stadium display testing |

### Phase 2 Definition of Done

The MVP can be installed and launched on the target Windows laptop, operated without development tools or internet access, run its clocks and scoring correctly, recover according to the agreed policy, and display legibly on the stadium wall during a sustained rehearsal.

---

## Phase 3 — Production Graphics, OBS, and Media

**Goal:** Add professional presentation capabilities around the proven scoreboard core.

| Possible workstream | Examples | Current status |
|---|---|---|
| OBS evaluation/integration | Browser source, scenes, transitions, hotkeys, and local WebSocket control | ➖ Deferred |
| Custom cutscenes | Touchdown, big play, defense, player introduction, and hype animations | ➖ Deferred |
| Media playback | Fullscreen videos, images, music-linked content if appropriate, and emergency stop | ➖ Deferred |
| Sponsor content | Static sponsors, scheduled rotation, and proof-of-play logging if needed | ➖ Deferred |
| Visual system | Team themes, logos, typography, safe zones, and reusable templates | ➖ Deferred |
| Source switching workflow | Scoreboard versus media/secondary HDMI source procedures | ➖ Deferred |

### Phase 3 Definition of Done

To be defined after Phase 2 field testing. At minimum, production features must fail safely without corrupting game state or preventing the basic scoreboard from operating.

---

## Phase 4 — External Controls and Expanded Operation

**Goal:** Integrate useful physical or remote controls only after the core application is stable.

| Possible workstream | Examples | Current status |
|---|---|---|
| Peripheral identification | Determine whether the vendor controller appears as HID, keyboard, serial/COM, storage, or a proprietary USB device | ➖ Deferred |
| Safe input mapping | Observe and document control events without modifying the vendor system | ➖ Deferred |
| Controller adapter | Translate supported physical inputs into the application's public control interface | ➖ Deferred |
| Multiple operators | Separate clock, scoreboard, and media responsibilities if operationally justified | ➖ Deferred |
| Additional control surfaces | Stream Deck, keypad, tablet, or dedicated button box if they improve reliability | ➖ Deferred |
| Conflict handling | Define authority when multiple controls attempt simultaneous changes | ➖ Deferred |

### Phase 4 Definition of Done

To be defined after real operators have used Phase 2 and Phase 3. External controls must remain optional: failure or disconnection of a peripheral must not prevent keyboard/mouse operation of the core scoreboard.

---

## Phase 5 — Stadium Production Hardening

**Goal:** Turn the proven system into a documented, recoverable game-day product.

| Possible workstream | Examples | Current status |
|---|---|---|
| Sustained reliability | Full simulated games, soak tests, clock accuracy, and repeated launch tests | ➖ Deferred |
| Failure recovery | App crash, HDMI loss, laptop restart, power interruption, and corrupted local settings | ➖ Deferred |
| Operator procedures | Pregame checklist, live-operation guide, troubleshooting card, and shutdown process | ➖ Deferred |
| Vendor fallback | Rehearsed input switch and clearly defined conditions for returning to the vendor system | ➖ Deferred |
| Deployment | Versioned releases, installer/update process, configuration backup, and rollback | ➖ Deferred |
| Observability | Useful logs, health indicators, and exportable diagnostic information | ➖ Deferred |
| Training | Short training session and practice game for student/volunteer operators | ➖ Deferred |
| Production readiness review | Formal go/no-go checklist before live use | ➖ Deferred |

### Phase 5 Definition of Done

To be defined from field experience. Production readiness will require successful full-game simulations, documented recovery and fallback procedures, trained operators, and a deliberate go/no-go decision by the project owner.

---

## Questions That Need Answers

Answers should be added directly to these tables. When an answer becomes an architectural decision, also record it in the Decision Log.

### Immediate / Phase 0 Questions

| Priority | Question | Current understanding | How to answer | Status |
|---:|---|---|---|---|
| Critical | Can the personal Windows laptop display across the entire LED wall through a normal HDMI input? | Approximately 90% likely | Stadium test planned for September 8, 2026 | 🧪 Needs testing |
| Critical | What resolution and refresh rate does Windows report? | Unknown | Record Windows advanced display settings | 🧪 Needs testing |
| Critical | Does the displayed image have cropping, stretching, seams, offsets, or unused areas? | Unknown | Use a full-screen alignment/test image and photograph the result | 🧪 Needs testing |
| High | What is the processor manufacturer and model? | Unknown | Photograph front, rear, and labels | 🧪 Needs testing |
| High | Does the processor reliably recover after changing or reconnecting HDMI sources? | Unknown | Test input reselection/reconnection when safe | 🧪 Needs testing |
| Medium | Where does HDMI audio go, and will this project need it? | Unknown | Inspect Windows audio devices and stadium audio routing | ⏳ Pending |

### Phase 1 Product Questions

| Priority | Question | Why it matters | Status |
|---:|---|---|---|
| Critical | Is the 25/40-second play clock required in the first implemented MVP? | Yes. Higher-priority instructions make it crucial and `docs/MVP_REQUIREMENTS.md` includes it. | ✅ Resolved |
| Critical | What are the exact game-clock start, reset, edit, expiration, and quarter-transition behaviors? | A conservative, testable baseline is specified; official school/state behavior still needs confirmation before live use. | 🟡 Provisional baseline; owner confirmation required |
| Critical | Should the clock display tenths below one minute? | Changes timing logic, testing, and display layout. | ⏳ Pending decision |
| High | Which score-correction method is required: minus buttons, direct edit, undo, or a combination? | Use one-level Undo, separate minus controls, and confirmed direct entry; every correction is logged. | ✅ Resolved for MVP baseline |
| High | What state must be restored after an application restart? | Provisional baseline restores teams, scores, quarter, and materialized clock values with both clocks stopped. | 🟡 Owner confirmation required before live use |
| High | What Windows computer will become the primary production machine? | Determines performance, outputs, packaging, and setup constraints. | ⏳ Pending |
| High | What is the intended first live-use date? | Determines how aggressively features must be limited. | ⏳ Pending |
| High | Who will operate the system, and how many operators are expected initially? | Determines workflow and control complexity. | ⏳ Pending |
| Medium | Are team colors and logos required in Phase 2, or are names sufficient? | Names are sufficient for the MVP; colors/logos are explicitly deferred unless display testing reveals a basic contrast need. | ✅ Resolved for MVP scope |
| Medium | Should the spectator display and operator controls run in one application window or separate windows? | Separate managed windows in one Python process, sharing one authoritative state. | ✅ Architecture decision |
| Medium | What clock-accuracy tolerance is acceptable over a full quarter? | Provides a measurable test target. | ⏳ Pending decision |
| Medium | Does the school impose restrictions on software installation or personal laptops? | Could constrain packaging and deployment. | ⏳ Pending |
| Medium | Should the GitHub repository be private or public? | Determines repository setup and licensing needs. | ⏳ Pending decision |
| Medium | Should a 25/40 play-clock preset reset-and-start immediately or load the value while stopped? | Changes the number of live operator actions and accidental-start risk. A reset-and-start default is documented. | ⏳ Owner confirmation |
| Medium | Which overtime labels and clock defaults apply under the school's governing rules? | Prevents the application from inventing a live overtime workflow. | ⏳ Owner/rules confirmation |
| Medium | Does the operator accept the proposed initial shortcut map? | The implementation can use it provisionally, but rehearsal may reveal ambiguous or awkward keys. | ⏳ Operator rehearsal/confirmation |

### Later-Phase Questions

| Phase | Question | Why it can wait | Status |
|---:|---|---|---|
| 3 | Does OBS materially improve the actual stadium workflow? | The core scoreboard can be proven without it. | ➖ Deferred |
| 3 | Will production media use the same laptop, a second laptop, or another HDMI input? | Requires hardware performance and operator-workflow evidence. | ➖ Deferred |
| 3 | What media formats, resolutions, frame rates, and audio routes are required? | Depends on the processor and content workflow. | ➖ Deferred |
| 3 | Who will create and approve cutscenes, logos, sponsor media, and other assets? | Content operations are unnecessary for the core MVP. | ➖ Deferred |
| 4 | How does Windows identify the existing physical controller? | Controller integration is explicitly outside the MVP. | ➖ Deferred |
| 4 | Is using the vendor controller technically and contractually permissible? | Must be answered before building an adapter. | ➖ Deferred |
| 4 | Would a simpler dedicated keypad or Stream Deck be more reliable than adapting the vendor controller? | Actual operator experience should guide the choice. | ➖ Deferred |
| 5 | What is the acceptable recovery time during a live game? | Requires real workflow and fallback testing. | ➖ Deferred |
| 5 | Who has authority to switch back to the vendor system? | Part of the eventual game-day operating procedure. | ➖ Deferred |
| 5 | What spare hardware and backup configuration will be available? | Depends on budget and production setup. | ➖ Deferred |

## Decision Log

Record decisions here so later implementation work does not silently reverse them.

| Date | Decision | Reason | Revisit when |
|---|---|---|---|
| September 4, 2026 | Keep the personal-laptop HDMI test as the final Phase 0 gate. | It validates the central assumption that the existing LED system can be treated as a normal display. | Revisit only if the test fails or reveals significant mapping problems. |
| September 4, 2026 | Treat the HDMI outcome as likely but unconfirmed. | The project owner estimates a favorable result at approximately 90% confidence, but no direct test has occurred. | Update immediately after the stadium test. |
| September 4, 2026 | Keep OBS optional until after the core scoreboard is proven. | OBS may help production features but is not required to validate scoring, clocks, or fullscreen output. | Evaluate in Phase 3 or earlier only if Phase 1 evidence justifies it. |
| September 4, 2026 | Preserve the vendor system as the fallback. | Live-game reliability requires a known working recovery path. | Do not reverse without an explicit production-readiness decision. |
| September 4, 2026 | Include the independent 25/40-second play clock in the Phase 2 MVP. | The project instructions identify it as crucial; omitting it would leave the MVP operationally incomplete. | Revisit only with explicit owner direction. |
| September 4, 2026 | Use one Python authority with separate managed HTML/CSS/JavaScript operator and spectator windows. | It is the smallest design that combines testable clock/state logic, flexible presentation, one-action startup, and Windows display control without requiring OBS or a local server. | Revisit if the Phase 2 Windows host proof or HDMI test fails materially. |
| September 4, 2026 | Use monotonic deadline-based clocks, not callback-count decrementing. | UI and scheduler delays must not accumulate clock drift. | Revisit only if tests disprove the implementation approach. |
| September 4, 2026 | Use atomic versioned JSON snapshots plus a backup and append-only JSONL event logs. | A local app needs understandable recovery without a database server. | Revisit if measured reliability reveals a concrete limitation. |
| September 4, 2026 | Do not adopt any of the six reviewed scoreboard repositories. | None satisfies the American-football MVP, direct fullscreen, clock/recovery, Windows, testing, and licensing needs together. | Revisit if requirements change or a better maintained/licensed candidate appears. |
| September 4, 2026 | Keep this repository unlicensed until the owner selects visibility and licensing. | The project must not imply redistribution permission without an explicit owner decision. | Revisit when repository visibility/license is decided. |

## Test and Evidence Log

| Date | Test or observation | Result | Evidence location | Effect on plan |
|---|---|---|---|---|
| Before September 4, 2026 | Disconnected each RJ45-style output link from the processor | Each cable appeared to serve one half of the LED wall | Project knowledge base; photographs not yet recorded here | Supports the hypothesis that the processor distributes video to wall sections; no need to inspect the protocol yet. |
| September 4, 2026 | Inspected six public candidate repositories from shallow clones | No suitable adoption base; useful architecture/timing/UX concepts recorded; two candidates lacked licenses and one had conflicting license evidence | `docs/OPEN_SOURCE_REVIEW.md` records commits and evidence | Select an independent Python-authority/managed-webview architecture and copy no candidate code. |
| September 4, 2026 | Inspected target GitHub repository with `git ls-remote --symref` | No advertised branches or commits; repository appears empty from Git | Command output in Phase 1 session | Safe to establish `main` without integrating remote history; visibility remains unknown. |
| Planned September 8, 2026 | Personal Windows laptop → HDMI processor input → full LED wall | Pending | Add photographs, screenshots, and notes | Determines whether Phase 0 can close and confirms the preferred system boundary. |

## Current Status

| Item | Current state |
|---|---|
| Active phase | Phase 1 documentation/repository foundation in progress; Phase 0 hardware gate remains open in parallel |
| Open phase gate | Personal laptop HDMI test on the complete LED wall |
| Confidence in preferred outcome | Approximately 90%, still unverified |
| Implementation status | Phase 2 application code has not begun; architecture and twelve-task backlog are documented |
| Repository status | Local Git initialized on `main`; target remote appears empty; initial commit/push and clean-clone verification remain |

## Next Action

On Tuesday, September 8, 2026, perform the personal-laptop HDMI test and capture the minimum evidence listed in the Phase 0 HDMI Test table. Update this document immediately with the result. In software, do not begin feature work before the Phase 2 Task 1 Windows multi-window/fullscreen host proof and owner review of the provisional clock decisions.
