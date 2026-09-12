# Buckswood auto Mashup

Turn two songs into an editable arrangement with alternating vocals and backing instruments. A local music-production experiment for **macOS on Apple Silicon**, built with Python, React and open-source audio models.

[![Checks](https://github.com/LudwigKienle/Buckswood-auto-Mashup/actions/workflows/checks.yml/badge.svg)](https://github.com/LudwigKienle/Buckswood-auto-Mashup/actions/workflows/checks.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

## What it does

- Separates vocals, drums, bass and other instruments; an optional two-stage RoFormer → Demucs pipeline targets cleaner vocals.
- Finds downbeats and proposes longer, recurring musical phrases. Vocals can continue across an instrumental change.
- Aligns tempo and pitch with Rubber Band, preserving vocal formants and using observed bar boundaries when available.
- Lets you edit source positions, vocal/instrumental choices, section lengths, builds, drops, levels and timing.
- Exports 24-bit WAV, 320 kbit/s MP3 and separate vocal/instrumental buses as 32-bit float WAV in a ZIP, before mastering.
- Processes audio on your Mac. Initial installation and first use download dependencies and public model weights.

**Early experimental release.** Automatic plans still need listening and editing: separation can leave artifacts, key estimates can be wrong, and the planner does not understand lyrics or guarantee matching chord progressions. The current interface is in German. See [quality methods and limitations](docs/quality.md).

## Install

You need an Apple Silicon Mac, a recent macOS version supported by MLX, Xcode Command Line Tools, **uv**, **Node.js 22.19+ / npm**, **FFmpeg / ffprobe**, and Git. Python 3.11 is installed by uv. Allow several GB for runtimes, model downloads, stems and exports; long songs can use substantial memory. Intel Macs, Linux and Windows are currently unsupported by the installers.

If you use Homebrew, install the prerequisites with:

```sh
xcode-select --install  # Skip if the Command Line Tools are already installed.
brew install uv node ffmpeg
```

Then:

```sh
git clone https://github.com/LudwigKienle/Buckswood-auto-Mashup.git
cd Buckswood-auto-Mashup
./scripts/setup.sh
./scripts/setup_hq.sh  # Optional, recommended for the two-stage vocal separation.
./"Buckswood auto Mashup.command"
```

The app opens at **http://127.0.0.1:18765/**. You can also double-click the `.command` launcher in Finder after installation.

The base installer installs pinned Python dependencies, checks out a fixed AutoMashup revision, builds Rubber Band 4.0.0 from source, copies the application into local storage, and builds the frontend. The HQ installer creates a separate MLX environment and downloads a pinned RoFormer checkpoint (about 456 MB), checked against SHA-256. No API key is required. Demucs and Beat This! download their public checkpoints on first use.

## Make a mashup

1. Upload your two songs into Track A and Track B.
2. Click **Musikalisch planen** to prepare stems and propose a coherent arrangement. With HQ installed, this prepares the improved stems automatically; **Vocals neu trennen** also starts that separation directly.
3. Listen to the vocal solos and compare the available separation versions at the same playback position.
4. Review the proposed tempo, section entries and pitch shift. Large tempo changes can make a voice sound unnatural even with formant preservation.
5. Render a preview, adjust the arrangement, then render the full mix and download the exports.

The mastering target is −14 LUFS integrated / −1.2 dBTP; these are targets, not a promise of perceptual quality. The float buses let you finish the mix in a DAW.

## Audio processing improvements (V6)

V6 plans a deliberate opening connected to the first backing passage. The musical planner compares 4- and 8-bar lead-ins using their rhythm energy and build; the quick planner also connects the intro to the following section instead of independently selecting a quiet excerpt. When preceding bars are unavailable, the intro introduces the upcoming motif. **Intro neu aufbauen** updates the opening of an existing arrangement while keeping its subsequent sections.

Bass and drums enter progressively during the intro. Their levels are shaped in the original stems before the combined backing is stretched, reaching full level before the first vocal. The preview now plays the actual first 32 bars, including the intro; it no longer skips directly to vocals.

V5 preserves short vocal pickups and releases across bar boundaries when a sustained pause bounds the original phrase and the neighboring singer leaves space. It uses up to roughly two beats of actual source audio (capped at 1.6 seconds), keeps the bar grid and arrangement duration fixed, and skips uncertain or occupied extensions. **Auftakte und Wortenden erhalten** can be switched off for comparison. Manually offset vocal sections retain manual timing without automatic handles.

The planner now measures sustained vocal pauses and penalizes phrases whose endings or pickups would collide at the singer handover. This is acoustic phrase-boundary detection, not transcription or lyric understanding. Existing cached profiles and exports remain available; new profiles use a separate cache.

V4 processes a complete backing as one stereo signal and keeps continuing backing/vocal passages in one stretch pass. Hybrid arrangements recombine bass and other instruments before stretching. Fixed pitch shifts use Rubber Band's high-quality mode, and small detector jitter does not force unnecessary timing corrections.

EQ and vocal-triggered backing reduction run across the assembled song, with a smooth release and phase-aligned midrange extraction. New imports retain float precision. The planner compares 8- and 16-bar candidates and penalizes prominent vocal-timbre/activity changes inside a phrase. These are heuristics, not lyric or speaker recognition. The separation models themselves have not changed.

New exports are labeled **V6**. Switching results in the history keeps the playback position for comparisons. Restored pickups/releases are counted below the player and recorded in the arrangement JSON, including handles that could not fit.

## Local storage and updates

The default data folder remains `~/Library/Application Support/Mashup Studio` for compatibility with earlier local builds. It contains `app`, `runtime`, `separation-runtime`, `tracks`, `exports`, `jobs` and model/build caches. Existing libraries do not need migrating when the product name changes.

Set `MASHUP_DATA` to an **absolute path** before every setup/launch command to use a different location:

```sh
export MASHUP_DATA="$HOME/Music/BuckswoodData"
```

Keep this folder outside cloud-synced directories. The repository contains editable source; the launcher runs the installed copy. To update, stop the local server when no jobs are running, pull the code and run `./scripts/setup.sh` again. Re-run HQ setup if its requirements changed. The launcher reuses an already-running studio process, so a backend update requires restarting that process.

## Development and checks

After base setup, run from the repository root:

```sh
buckswood_data="${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}"
uv pip install --python "$buckswood_data/runtime/bin/python" -r requirements-dev.txt
"$buckswood_data/runtime/bin/python" -m pytest -q
cd web
npm ci
npm run build
```

Tests use a temporary library, synthetic audio and the installed native Rubber Band library. They cover pitch/duration, timing anchors, vocal continuity, phrase planning, overlap-add reconstruction and local API protections. They do not measure subjective separation quality against ground-truth music stems. CI runs base installation, tests and the frontend build on an Apple Silicon macOS runner; it does not run full neural separation.

To run the backend directly from your checkout, build `web/dist` first and run:

```sh
"${MASHUP_DATA:-$HOME/Library/Application Support/Mashup Studio}/runtime/bin/python" -m uvicorn studio.server:app --host 127.0.0.1 --port 18765
```

The default launcher already uses port 18765; stop that instance first. Keep the server on loopback. This is a single-user local tool, not an authenticated multi-user web service.

See [CONTRIBUTING.md](CONTRIBUTING.md) for useful reports and quality contributions.

## Credits and license

Built on [AutoMashup](https://github.com/ax-le/automashup) by Axel Marmoret for key/pitch helpers, [Demucs](https://github.com/facebookresearch/demucs), [Beat This!](https://github.com/CPJKU/beat_this), [Rubber Band](https://github.com/breakfastquay/rubberband), [MLX Audio](https://github.com/Blaizzy/mlx-audio) and the [Kim Vocal 2 MLX RoFormer conversion](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx), alongside librosa, NumPy, SciPy, PyTorch, SoundFile, FFmpeg, FastAPI and React.

This is an independent application, not an official release of those projects. Its planner and rendering pipeline are implemented here; it does not run the complete upstream AutoMashup research pipeline.

Copyright © 2026 Ludwig Kienle and contributors. Project code is licensed under **GPL-3.0-only**; see [LICENSE](LICENSE). Dependency and model licenses remain their own; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This repository contains no songs, recordings, model weights or rendered mashups. The code license does not grant rights to input music or output recordings.
