---
name: sst-handover
description: Generates a technical handover document (Handover_Document_<branch>_<YYYYMMDD>.md) summarizing the current project state, recent changes, and next tasks for the S.S.T project. Use when the user wants to create a handover document, save the current context, or switch to a new session.
---

# S.S.T Handover Document Generator

## Overview

This skill automates the creation of a technical handover document for the S.S.T (Steam Soundtrack Tagger) project. It ensures that the project's complex context, architecture, recent changes, and next steps are perfectly captured so that a new AI session can seamlessly resume work.

## Workflow

When triggered to create a handover document, follow these steps:

### 1. Determine Dynamic Values
- **Branch Name**: Retrieve the current Git branch name using the shell command `git branch --show-current`. If not in a git repo, use `main` or `unknown`.
- **Date**: Retrieve the current date in `YYYYMMDD` format using the shell command `date +%Y%m%d`.

### 2. Synthesize Content
Write a comprehensive Markdown document that includes:
- **1. プロジェクト概要**: The core philosophy ("一度のアーカイブで、一生の信頼を", 100% reliability for Archive, fallback to Review).
- **2. 現在のアーキテクチャ**: The 3-tier API architecture (Official Store API, Local PICS Bridge via Docker, Steam Web API).
- **3. 重要な技術仕様と直近の改善点**: Summarize the significant technical specifications and the most recent changes you have made in this branch.
- **4. 実行環境**: The runtime environment (Windows 11 / WSL2 (Ubuntu), Python 3.12, FFmpeg, SQLite, Local Ollama or Gemini API, etc.).
- **5. 現在のディレクトリ構造 (主要部分)**: The current main directory structure.
- **6. 次に着手すべきタスク**: The next tasks to be done by the user or the next AI session.

### 3. Generate the File
Save the synthesized content to a file named `Handover_Document_<branch-name>_<YYYYMMDD>.md` in the project root directory.

### 4. Notify the User
Inform the user that the handover document has been successfully created and that they can copy/paste it into a new session to resume work perfectly.
