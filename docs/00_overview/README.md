# SST Overview

SST (Steam Soundtrack Tagger) is a distributed system that:

- Identifies Steam soundtrack audio
- Matches with external DB (VGMdb / MusicBrainz)
- Enriches metadata
- Writes ID3 tags
- Stores processed audio

---

## Design Principles

1. Accuracy over speed
2. Failure isolation (review separation)
3. Deterministic + retryable
4. Stateless workers

---

## Target

- Steam soundtrack only

---

## Non-target

- Real-time processing
- Non-Steam sources
