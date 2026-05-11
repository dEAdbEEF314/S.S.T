---
name: sst-verifier
description: Automates deployment, health checks, visual verification (Playwright), and data integrity for the S.S.T system. Use to confirm code changes or perform full system smoke tests.
---

# S.S.T Verifier Skill

This skill provides a unified workflow to verify the integrity of the S.S.T system, including visual analysis via Playwright.

## Workflow

1.  **Preparation**: Ensure the `.env` file is properly configured in the workspace root.
2.  **Execution**: Run the verification script:
    ```bash
    python3 skills/sst-verifier/scripts/verify_sst.py
    ```
3.  **Visual Check**: 
    - Open the `ui_verification/` directory to see screenshots of each page.
    - As an AI agent, I will analyze these screenshots (via their metadata and DOM structure) to detect layout issues or visibility bugs.
4.  **Data Validation**: 
    - The script automatically checks API health and metadata presence.

## Key Checks Performed

- UI container accessibility (Port 8000).
- Visual verification: Renders correct CSS, no 404s on images/assets.
- Metadata integrity: Ensuring `tracks` info exists in the final JSON.

## Requirements

- Node.js & Playwright (for visual capture).
- Docker (for UI deployment).
- Python 3 (for the main runner).
