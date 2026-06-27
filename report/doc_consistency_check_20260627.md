# Documentation Consistency Check (2026-06-27)

## Scope
- README.md
- docs/LOGIC.md
- docs/TAGGING_RULE.md
- docs/error_handling.md
- docs/AGENT_GUIDE.md
- docs/data_flow_diagram.md
- docs/cache_architecture.md
- docs/Virtual_Album.md
- docs/VIRTUAL_ALBUM_RULES.md
- docs/DEPLOYMENT_GUIDE_jp.md

## Result Summary
- Status: PASS (within scoped documents)
- Blocking inconsistency: None
- Notes: Legacy proposal docs are explicitly labeled as historical material.

## Checklist

| Check Item | Expected | Result | Evidence |
|---|---|---|---|
| Reset command name | `--reset-db` only | PASS | docs/DEPLOYMENT_GUIDE_jp.md, docs/AGENT_GUIDE.md |
| Finalize ingestion status | Not implemented / future work | PASS | README.md, docs/AGENT_GUIDE.md, docs/DEPLOYMENT_GUIDE_jp.md |
| Review output format | `output/review/` as ZIP archives | PASS | README.md, docs/TAGGING_RULE.md, docs/LOGIC.md |
| Virtual album count | 4 virtual albums (`STEAM`, `FINGERPRINT`, `MBZ_SEARCH`, `LOCAL`) | PASS | README.md, docs/Virtual_Album.md, docs/data_flow_diagram.md, docs/VIRTUAL_ALBUM_RULES.md |
| Decision thresholds (normal path) | `identity_confidence >= 100` and `integrity_quality >= 95` | PASS | docs/LOGIC.md, docs/error_handling.md, docs/AGENT_GUIDE.md, docs/VIRTUAL_ALBUM_RULES.md |
| STEAM-TRUST exception | quality threshold relaxed to 75 when conditions are met | PASS | docs/LOGIC.md, docs/error_handling.md, docs/AGENT_GUIDE.md, docs/VIRTUAL_ALBUM_RULES.md |
| Cache table naming | `api_cache` (service/query_key) | PASS | docs/cache_architecture.md, docs/data_flow_diagram.md |

## Non-blocking Observation
- docs/VIRTUAL_ALBUM_RULES.md still contains an advisory statement in section 1.1 (`physical_match_ratio > 80%` implies confidence 95+ guidance). This is not contradictory to the final gate thresholds, but should be interpreted as guidance before final validation.

## Verification Commands
```bash
rg -n -S -- "--reset-db|--delete-db|--finalize|finalize|Identity Confidence|Integrity Quality|STEAM-TRUST|api_cache|acoustid_cache|mbz_cache|output/review|ZIP|Virtual Albums|4つの仮想アルバム|MBZ_SEARCH" README.md docs/{LOGIC.md,TAGGING_RULE.md,error_handling.md,AGENT_GUIDE.md,data_flow_diagram.md,cache_architecture.md,Virtual_Album.md,VIRTUAL_ALBUM_RULES.md,DEPLOYMENT_GUIDE_jp.md}
```
