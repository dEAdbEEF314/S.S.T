# SST Implementation Plan (CLI Focus)

This document defines the roadmap for SST as a **high-precision, standalone CLI tool**.

The goal has shifted from a distributed microservice architecture to a robust, local-first edge processing tool that prioritizes metadata accuracy via LLM-assisted "Factual Metadata Organization."

---

# 🎯 Project Goal

To provide a single-binary/script experience that:
1.  **Identifies**: Scans local Steam libraries.
2.  **Enriches**: Fetches metadata from Steam Store and MusicBrainz.
3.  **Consolidates**: Uses LLMs to resolve metadata conflicts with zero hallucination.
4.  **Transforms**: Converts audio to high-quality formats (AIFF/MP3) and applies strict tagging.
5.  **Packages**: Delivers a ready-to-use ZIP bundle with full processing logs.

---

# 🏗️ Execution Phases (Revised)

| Phase | Goal | Status |
|------|------|--------|
| Phase 1 | Core I/O & Local Scanning | **Done** |
| Phase 2 | External API Integration (Steam/MBZ) | **Done** |
| Phase 3 | LLM Consolidation (Iterative Chat) | **Done** |
| Phase 4 | Audio Transformation & Tagging | **Done** |
| Phase 5 | CLI UX Enhancement (Rich UI) | **Pending** |
| Phase 6 | Advanced LLM Strategies (Summary-first) | **Planned** |
| Phase 7 | Reliability & Error Recovery | **Ongoing** |

---

# 🧩 Phase 1-4: Core Engine (Current State)

The core logic is implemented in the `scout` package. It performs the full pipeline synchronously.

### Key Components:
- `SteamScanner`: Locates soundtracks and parses manifest files.
- `LocalProcessor`: The main orchestrator of the local pipeline.
- `LLMOrganizer`: Handles iterative chat sessions with rate limiting.
- `AudioTagger`: FFmpeg-based conversion and ID3v2.3 tagging.

---

# 🧩 Phase 5: CLI UX Enhancement

**Objective**: Replace the deprecated Web UI with a powerful, interactive CLI.

### Tasks:
- [ ] **Interactive Progress**: Implement `rich` or `tqdm` for beautiful multi-bar progress tracking.
- [ ] **Review Interface**: Allow users to approve or edit metadata suggestions directly in the terminal before tagging.
- [ ] **Result Summaries**: Display a clear table of processed vs. review-queued albums at the end of the run.
- [ ] **Log Browser**: A simple CLI command to view LLM chat histories or MBZ responses.

---

# 🧩 Phase 6: Advanced LLM Strategies

**Objective**: Improve the quality of consolidation.

### Tasks:
- [ ] **Summary-First Pass**: Send the entire album tracklist to the LLM first to establish global context (Artist consistency, Disc count).
- [ ] **Multi-Model Voting**: (Optional) Compare results from two different models to minimize outliers.
- [ ] **Parent Game Logic**: Fully automate the fetching of tags from the parent game when the soundtrack app is sparse.
| Phase 7 | Reliability & Notifications | **Planned** |

---

# 🧩 Phase 7: Reliability & Notifications

**Objective**: Ensure the tool is reliable for bulk processing and provides real-time feedback via external services.

### Tasks:
- [ ] **Discord Integration**: Implement a robust notification system with per-level Webhook support (Critical, Warning, Info, Completion).
- [ ] **Notification Throttling**: Implement cooldown logic to prevent spamming Discord during high-intensity error bursts.
- [ ] **Rich Error Reporting**: Send beautiful Discord Embeds including Album name, AppID, processing time, and failure reasons.
- [ ] **System Hardening**: Implement global fail-safes to ensure the processor can recover from network interruptions or database locking issues.
- [ ] **Performance Audit**: Fine-tune parallel worker counts for local vs. remote LLM modes based on real-world test data.
---

# 🚫 Discontinued / Outdated Goals

- **SeaweedFS / S3 Integration**: Removed. The system now uses the local filesystem and ZIP archives.
- **Web UI (FastAPI/React)**: Deprecated. The UI will be rebuilt as part of the CLI.
- **Prefect Orchestration**: Removed. The system is a standalone tool, not a distributed workflow.
- **AcoustID**: Deprecated due to low performance for VGM.
