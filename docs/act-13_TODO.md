# act-13 TODO: Discord Notifications and Reliability Hardening

Objective: Implement a multi-level Discord notification system to provide real-time feedback for long-running batch processes, and further harden the system's reliability.

## 1. Discord Notification System (Priority: Critical)
- [ ] **Config Extension**: Update `scout/src/scout/main.py` to support `NOTIFY_ENABLED`, `NOTIFY_COOLDOWN`, and the 4 Webhook URLs (`CRITICAL`, `WARNING`, `INFO`, `COMPLETION`).
- [ ] **Notification Manager**: Create `scout/src/scout/notify.py` to handle Discord Webhook POST requests.
- [ ] **Throttling/Cooldown**: Implement logic to skip redundant notifications of the same type within the `NOTIFY_COOLDOWN` window.
- [ ] **Rich Embeds**: Design beautiful Discord Embeds (Colors: Red for error, Yellow for warning, Green for completion) including:
    - Album Name & AppID
    - Classification Result
    - Processing Time
    - Failure Reason (if any)

## 2. Integration & Events
- [x] **Semantic Labeling**: Update LLM Phase 1 to generate a `semantic_label` summarizing data anomalies (e.g., SFX mixing). Display this in the CLI summary instead of generic missing metadata errors.
- [ ] **Logging Hook**: Integrate the notification system with the logging flow or specific processing events in `processor.py`.
- [ ] **Completion Summary**: Send a single, comprehensive "Total Run Summary" to the `COMPLETION` webhook when the main loop finishes.
- [ ] **Circuit Breaker Notification**: Send a `CRITICAL` alert if the LLM daily limit (RPD) is reached and the system stops.

## 3. Reliability Hardening
- [ ] **Locking Verification**: Double-check SQLite and MusicBrainz locking behavior under high parallel load.
- [ ] **Empty Response Guard**: Further verify the new retry logic against real-world "機嫌が悪い" API behavior.

## 4. Documentation
- [ ] Update `docs/HANDOVER_act-13.md` for team onboarding.
