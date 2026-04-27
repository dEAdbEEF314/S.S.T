# Project S.S.T Onboarding & Handover: Act-13

Welcome to the **Steam Soundtrack Tagger (S.S.T)** project. You are joining at the start of **Act-13**, focused on external notifications and system hardening.

## 1. Project State after Act-12
S.S.T is now a fully functional standalone CLI tool with:
- **Rich CLI**: Multi-bar progress tracking and color-coded logging.
- **Batched LLM Processing**: Stateful 2-phase consolidation (Soul & Body) to handle large context and output limits.
- **Robust Scanner**: Support for hidden DLC soundtracks.
- **Launcher Script**: Use `./sst` from the root to manage everything (stats, tail, run, delete-db).

## 2. Your Mission: Act-13
The main objective is to implement **Discord Webhook Integration**. 

### Key Technical Areas:
- **`scout/src/scout/notify.py`**: (To be created) Logic for sending Discord messages with rich embeds.
- **Configuration**: Support for multiple webhook levels (Critical, Warning, Info, Completion).
- **Throttling**: Ensure the system doesn't spam Discord during error bursts (cooldown logic).

## 3. Important Files
- **`scout/src/scout/main.py`**: Main orchestration and CLI setup.
- **`scout/src/scout/processor.py`**: Core logic where processing events occur.
- **`sst`**: Root launcher script.

## 4. Current Workflows
- **Running**: `./sst -n 5`
- **Stats**: `./sst --stats`
- **Tail Logs**: `./sst --tail`

Refer to `docs/fixed/` for historical TODOs and `docs/act-13_TODO.md` for your current roadmap.
