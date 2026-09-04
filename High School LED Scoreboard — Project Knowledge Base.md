# High School Football LED Scoreboard — Project Knowledge Base

## 1. Project Overview

We are developing a custom software system for a high-school football stadium's newly installed giant LED scoreboard/video wall.

The existing vendor software works but is clunky, unintuitive, and appears to make very limited use of the capabilities of the giant LED display.

The desired system will eventually combine:

- Football scoreboard/game control
- Professional-looking LED graphics
- Animations
- Sponsor/advertising content
- Full-screen videos
- Hype graphics
- Potential replay/media capabilities
- Multiple operators
- Existing physical scoreboard-controller integration
- Multiple HDMI sources

The ultimate goal is a reliable "mini sports production system" rather than simply another traditional scoreboard UI.

---

# 2. User / Development Context

The user is a vibe coder.

He is not an expert software engineer but is comfortable with:

- Python
- Windows
- terminals
- installing packages
- Git/GitHub
- basic programming concepts
- using AI coding tools

Codex will be used as the primary implementation/coding agent.

ChatGPT's role is:

- Technical architect
- Researcher
- Product manager
- Codex prompt writer
- Code reviewer
- Troubleshooter
- Decision-maker/challenger

The user specifically wants assumptions challenged rather than blindly accepted.

When researching, distinguish between:
- Known facts
- Reasonable hypotheses
- Unverified assumptions

---

# 3. Existing Stadium Hardware

The high school recently installed a very large all-digital LED scoreboard.

Approximate physical size: 25 feet tall/wide.

Exact dimensions are unknown.

The entire display appears to behave like one enormous monitor/video wall.

Current suspected signal chain:

    Windows PC/Laptop
          |
        HDMI
          |
          v
    HDMI/video processor/switcher
          |
      two RJ45-style cables
          |
          v
    Giant LED display

The processor/switcher has:

- 4 HDMI inputs
- apparently 0 HDMI outputs
- physical buttons for switching inputs

The processor can switch between HDMI sources.

---

# 4. Important Hardware Experiment

The user unplugged one of the two RJ45/Ethernet-style cables going from the processor toward the LED display.

Result:

- Exactly the top OR bottom half of the LED wall went black.
- The other half continued displaying normally.

This suggests the processor is mapping/distributing the incoming video signal across two sections of the LED wall.

However:

**DO NOT assume the RJ45 cables are ordinary Ethernet.**

They may carry proprietary display data, specialized video transport, or another protocol.

The actual processor and adapter models are still unknown.

This hardware detail should NOT become a major development concern unless testing proves that the normal HDMI approach does not work.

---

# 5. Critical Upcoming Hardware Test

The most important test at the school is:

1. Bring the user's more powerful personal Windows laptop.
2. Connect it to an available HDMI input on the existing processor.
3. Switch the processor to that input using its physical buttons.
4. Confirm that a normal Windows desktop appears across the entire LED wall.
5. Record the Windows-reported display resolution.

If this works, our working model becomes:

    Custom software
          |
        HDMI
          |
    Existing processor
          |
      LED wall

In that case, our software does NOT need to know how the LED panels themselves work.

This is the preferred architecture.

---

# 6. Existing Vendor Computer

The current vendor scoreboard software runs on a Windows 11 school-issued laptop.

The laptop is not particularly powerful.

The vendor software requires a USB key/dongle.

The exact purpose of the dongle is unknown.

Possibilities include:
- software license key
- hardware authentication
- proprietary USB device
- storage device
- HID device

Do not investigate or circumvent the license mechanism.

Keep the existing vendor computer/software intact as an emergency fallback.

---

# 7. Existing Physical Controller

The vendor system includes a large physical controller.

It has:
- LCD screen
- buttons for adding points
- timeout controls
- clock controls
- other scoreboard controls

It connects to the vendor computer via USB.

This is potentially very valuable because it allows multiple people to control the game without relying entirely on a laptop UI.

Eventually investigate what Windows sees when it is connected.

Potential possibilities:

- USB HID
- keyboard-like input
- USB serial/COM device
- proprietary USB protocol

Potential eventual architecture:

    Physical controller
          |
         USB
          |
        Python
          |
      Game State
          |
     Presentation

However:

**Physical controller integration is explicitly NOT part of MVP #1.**

---

# 8. HDMI Source Strategy

The existing processor has four HDMI inputs.

The user wants to leverage this.

Potential arrangement:

HDMI 1:
    Custom scoreboard application

HDMI 2:
    Separate laptop/video source

Additional inputs:
    Vendor system / future cameras / other sources

The user wants to eventually use the second HDMI source for:

- custom videos
- replays
- full-screen content
- arbitrary graphics

The processor already has physical input-selection buttons, so automated source switching is not required for the MVP.

---

# 9. OBS Studio

OBS Studio is being considered as a production/rendering component.

Conceptually, OBS acts like a digital TV control room.

It supports:
- scenes
- sources
- browser sources
- video
- images
- transitions
- media playback
- hotkeys
- WebSocket control

Potential architecture:

    Python application
          |
      WebSocket/API
          |
         OBS
          |
        HDMI
          |
    Existing processor
          |
      LED wall

The operator would ideally interact with our custom application, not OBS directly.

OBS is NOT yet an architectural commitment.

Evaluate it against alternatives before adopting it.

---

# 10. Candidate Architecture

Current leading hypothesis:

    Python backend/game engine
              |
          API/WebSocket
              |
              v
    HTML/CSS/JavaScript renderer
              |
              v
             OBS
              |
             HDMI
              |
      Existing processor
              |
           LED wall

Alternative architectures:

### A. Python + HTML/CSS/JS + OBS
Potentially strongest production-oriented architecture.

### B. Python + HTML/CSS/JS directly to fullscreen HDMI
Potentially simpler if OBS adds unnecessary complexity.

### C. Python-only rendering
Potentially simple but may make sophisticated graphics/video production harder.

### D. Existing open-source scoreboard + modifications
Potentially fastest if a strong codebase can be adapted.

### E. Hybrid
Reuse existing scoreboard/game-state logic while replacing presentation/operator experience.

Do not choose based on preference alone.

Evaluate:
- Reliability
- Simplicity
- Windows compatibility
- Offline operation
- Video playback
- Animations
- Fullscreen output
- Multiple operators
- Maintainability
- Ease of Codex development
- Future physical-controller integration

---

# 11. Open-Source Research

Several relevant projects have already been identified.

## AmericanFootballScoreboard

https://github.com/chris109b/AmericanFootballScoreboard

Relevant because it provides:
- American football scoreboard
- remote/web control
- smartphone/tablet control
- high-resolution display support
- plugins
- OBS integration
- game logging

Inspect architecture and license before considering reuse.

## Football-Scoreboard

https://github.com/KevinZheng2025/Football-Scoreboard

Python-based football scoreboard with OBS-oriented display.

Potentially useful for football/game-state concepts.

## fly-scoreboard

https://github.com/mmlTools/fly-scoreboard

Relevant features include:
- football
- timers
- hotkeys
- OBS dock
- WebSocket/remote control
- event logging

## alpower/scoreboard

https://github.com/alpower/scoreboard

HTML/CSS/JavaScript scoreboard intended for OBS Browser Source with interactive control.

Potentially relevant to the web-renderer architecture.

## Streamn Scoreboard

https://github.com/StreamnDad/streamn-scoreboard

OBS scoreboard plugin supporting football and other sports.

Potentially useful for understanding OBS integration.

## scorebug

https://github.com/david-mcgaughy/scorebug

High-school basketball-oriented project with:
- control dashboard
- OBS WebSockets
- animations
- team logos
- live configuration
- ticker

Potentially useful as a model for high-school sports production workflows.

These repositories are research starting points, NOT automatically recommended foundations.

Check current status, activity, license, architecture, Windows support, and actual usefulness before adopting anything.

---

# 12. Reddit Research

Reddit research has already found discussions involving:

- OBS scoreboards
- remote scoreboard control
- custom scoreboard overlays
- scoreboard projects
- high-school sports production

The broad takeaway is that:

    scoreboard application
          +
    OBS
          +
    browser/graphics source
          +
    external control

is an established pattern.

However, the project is specifically targeting a physical stadium LED board, not merely a livestream scoreboard overlay.

Future Reddit research should include:
- r/obs
- sports production communities
- high-school athletics communities
- LED display/video-wall discussions
- relevant GitHub discussions/issues

Use Reddit for practical experience and pain points, while verifying technical claims against authoritative documentation/code.

---

# 13. MVP #1

The first MVP must be intentionally small.

Run entirely on Windows.

It should display:

    HOME 00
    AWAY 00

    1st
    12:00

Required controls:

- Home +1
- Home +2
- Home +3
- Home +6
- Away +1
- Away +2
- Away +3
- Away +6
- Start clock
- Stop clock
- Reset clock
- Quarter
- Team names

Mouse and keyboard are sufficient.

No physical controller.

No direct LED protocol.

No automated HDMI switching.

No advanced statistics.

No networking.

No replay system.

No cloud dependency.

No giant feature set.

---

# 14. MVP Testing Strategy

Development should initially happen entirely at home.

Use a normal:
- monitor
- TV
- HDMI display

The first proof should be a simple football scoreboard.

Then test:
- score changes
- clock behavior
- quarter changes
- team names

After that:
- visual polish
- animations
- video playback
- scenes

Only then test at the actual stadium.

---

# 15. Long-Term Feature Roadmap

## Game Controls
- Home/away score
- Game clock
- Play clock
- Quarter
- Down/distance
- Timeouts
- Possession
- Penalties
- Scoring types
- Undo
- Event history
- Game save/recovery

## Graphics
- Touchdown
- Field goal
- Safety
- Interception
- Sack
- Turnover
- First down
- Big play
- Player introduction
- Starting lineup
- Halftime
- Victory
- Defensive hype
- Crowd prompts

## Sponsors
- Full-screen ads
- Sponsor rotation
- Sponsor ticker
- Scheduled advertising
- Animated sponsor graphics

## Video
- MP4 playback
- Pregame videos
- Hype videos
- Touchdown videos
- Replay clips
- Second HDMI source

## Operators
- Keyboard shortcuts
- Touchscreen-friendly interface
- Multiple operators
- Remote control
- Role-based controls
- Emergency/fallback mode
- Undo/recovery

## Hardware
- Existing physical USB controller
- Potential capture devices
- Potential camera integration
- Potential automated HDMI source switching

## Data
- Rosters
- Player numbers
- Statistics
- Scoring history
- Game log
- Export

---

# 16. Reliability Requirements

This system may eventually be used during actual football games.

Reliability is more important than feature count.

Priorities:

1. Stability
2. Predictability
3. Fast recovery
4. Simple operation
5. Offline operation
6. Clear errors
7. Logging
8. Backup/fallback
9. Fancy features

Core game operation should not require internet access.

The existing vendor system must remain available as an emergency fallback.

---

# 17. Immediate Next Steps

1. Research existing open-source projects thoroughly.
2. Compare architectures.
3. Select MVP architecture.
4. Build a tiny local scoreboard.
5. Test it on a normal Windows HDMI display.
6. At the next school visit, test personal-laptop HDMI output to the entire LED wall.
7. Gather hardware/model information.
8. Only then begin stadium-specific integration.
9. Add visual/production features incrementally.
10. Integrate the physical controller later.

---

# 18. Core Principle

**Reuse what already works. Build only what differentiates our system.**

The objective is not to prove that we can write a scoreboard from scratch.

The objective is to create a better system with the least unnecessary engineering.