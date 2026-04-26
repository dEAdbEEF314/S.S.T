# Project S.S.T Onboarding & Handover: Act-12

Welcome to the **Steam Soundtrack Tagger (S.S.T)** project. This document provides a high-level overview for engineers starting work on **Act-12**.

## 1. Project Overview
S.S.T is a high-precision CLI tool that automates the tagging of Steam soundtracks by consolidating data from Steam API, MusicBrainz, and local files using LLMs.

## 2. Core Architecture (`scout` package)
- **`main.py`**: Entry point. Handles CLI arguments and orchestrates the parallel album processing.
- **`processor.py`**: The heart of the system. Orchestrates sources (MBZ/Steam), calls LLM, and manages the audio processing lifecycle.
- **`llm.py`**: Handles all AI interactions. Uses a 2-phase strategy (Global Identity -> Track Mapping) to manage large context and output limits.
- **`tagger.py`**: Wrapper for FFmpeg and Mutagen. Handles audio conversion and ID3 tagging.
- **`scanner.py`**: Finds soundtracks in the Steam Library (including hidden DLCs).

## 3. Key Concepts for Act-12

### LOG_LEVEL Definitions
- **DEBUG**: Raw prompts, raw API responses, FFmpeg parameters.
- **INFO**: Standard progress (Start/End of album processing, artwork download).
- **WARNING**: Review triggers (missing data, low confidence), API rate limits.
- **ERROR**: Critical failures that stop a specific album or the system.

### ENV_MODE Differences
- **`development`**: Priority on debuggability. Keep `temp_output` on error. Ignore caches.
- **`production`**: Priority on speed/UX. Silent logging (redirected to file). Clean stdout (Progress bars only). Mandatory cleanup.

## 4. Immediate Goals
Your first task is to integrate the `rich` library to replace raw text output with beautiful progress bars and dashboards. You also need to implement the mode-based behavior logic discussed in `act-12_TODO.md`.

Refer to `docs/act-11_TODO.md` (history) and `docs/act-12_TODO.md` (future) for more context.
