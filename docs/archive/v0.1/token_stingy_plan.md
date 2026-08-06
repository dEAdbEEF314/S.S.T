# Token Stingy Detailed Plan

## Purpose

この文書は、次の 2 項目を実装するための詳細計画書です。

1. アルバム総曲数または Tier に応じて `num_ctx` と並列度を切り替える実行プロファイル機構を導入する。
2. その実行プロファイルを `.env.example` に表現できる設定体系へ拡張する。

本計画は、既存の request-level VRAM scheduling、Phase 2 chunk 並列化、Coherence Map-Reduce、Ollama 相関観測の成果を前提とします。

---

## Background

現状の S.S.T は以下の状態にあります。

- 推奨ローカルモデルは `ornith:9b`
- request-level の VRAM 見積りと acquire/release は導入済み
- Phase 2 chunk 並列化は導入済み
- `ornith:9b` では複数 slot 相当の動作が確認済み
- `.env` では `LLM_OLLAMA_NUM_CTX` が単一の固定値として扱われる
- `llm_request_parallelism_max_workers` も単一の固定値として扱われる

一方で、実運用上は以下の相反する要求があります。

- 小〜中規模アルバムでは `num_ctx` を絞り、並列 request を増やしたい
- 大規模アルバムでは並列度を抑えてでも `num_ctx` を大きく取り、一貫性を優先したい
- 100 曲超クラスでは Coherence と One-shot 寄りの戦略が品質面で有利

したがって、固定値 1 本ではなく「アルバムサイズ別の実行プロファイル」が必要です。

---

## Scope

この計画書の対象は以下です。

- `processor.py` でのアルバムごとの実行プロファイル決定
- `llm.py` での `num_ctx` 上限と Phase 2 worker 数のプロファイル反映
- `config.py` の設定項目拡張
- `.env.example` の tier 別設定追記
- `README.md` / `docs` の簡易追記
- テストの追加

この計画書の対象外は以下です。

- VRAM 推定ロジック自体の全面刷新
- `bytes_per_token` の実測式導入
- `gemma3:1b` など小型モデル特有の JSON 破綻防御強化
- `MAX_PARALLEL_ALBUMS` のクラウド API 向け制御見直し

---

## Design Goal

設計目標は次の 4 点です。

1. 小さいアルバムでは throughput を最大化する
2. 大きいアルバムでは一貫性を最大化する
3. 既存の VRAM scheduling と矛盾しない
4. `.env` だけで実行プロファイルを再現できるようにする

---

## High-Level Strategy

単一の `LLM_OLLAMA_NUM_CTX` と `LLM_REQUEST_PARALLELISM_MAX_WORKERS` を直接使うのではなく、アルバムごとに `AlbumExecutionProfile` を作ります。

この profile は少なくとも次を持ちます。

- `tier_name`
- `track_count_min`
- `track_count_max`
- `num_ctx_cap`
- `phase2_parallel_workers`
- `force_coherence`
- `prefer_one_shot`

この profile を `LocalProcessor` が決定し、`LLMOrganizer` に渡します。

`LLMOrganizer` は profile を使って以下を制御します。

- Phase 1 identity request の `num_ctx` 上限
- Phase 1.5 coherence request の `num_ctx` 上限
- Phase 2 mapping request の `num_ctx` 上限
- Phase 2 の parallel worker 数
- `coherence_threshold` を越えなくても強制的に Coherence を使うかどうか

---

## Proposed Tier Model

初期案として、以下の 3 Tier を採用します。

### Small

- 対象: `1-50` tracks
- 目的: throughput 優先
- 推奨:
  - `num_ctx_cap = 8192`
  - `phase2_parallel_workers = 3`
  - `force_coherence = false`
  - `prefer_one_shot = false`

### Medium

- 対象: `51-100` tracks
- 目的: throughput と一貫性のバランス
- 推奨:
  - `num_ctx_cap = 16384`
  - `phase2_parallel_workers = 2`
  - `force_coherence = false`
  - `prefer_one_shot = true`

### Large

- 対象: `101+` tracks
- 目的: 一貫性優先
- 推奨:
  - `num_ctx_cap = 32768`
  - `phase2_parallel_workers = 1`
  - `force_coherence = true`
  - `prefer_one_shot = true`

---

## Effective num_ctx Rule

`num_ctx` は profile の値をそのまま固定で使わず、次のルールで決めます。

```text
effective_num_ctx = min(profile.num_ctx_cap, request_estimate.resolved_num_ctx)
```

意味は以下です。

- profile は「このアルバムで許可する最大 `num_ctx`」を決める
- request estimate は「その request が実際に必要とする `num_ctx`」を決める
- 最終的には両者の小さい方を使う

これにより、大規模アルバムでも identity / coherence では大きめの `num_ctx` を取りつつ、短い Phase 2 chunk で毎回 32768 を抱え込むことを防げます。

---

## Code Change Plan

### 1. `src/sst/config.py`

追加する設定案:

- `llm_album_tier_small_max_tracks: int = 50`
- `llm_album_tier_medium_max_tracks: int = 100`
- `llm_ollama_num_ctx_small: int = 8192`
- `llm_ollama_num_ctx_medium: int = 16384`
- `llm_ollama_num_ctx_large: int = 32768`
- `llm_request_parallelism_max_workers_small: int = 3`
- `llm_request_parallelism_max_workers_medium: int = 2`
- `llm_request_parallelism_max_workers_large: int = 1`
- `llm_force_coherence_large: bool = True`

必要な変更:

- `Config` に上記を追加
- `build_llm_organizer_kwargs()` に profile 用設定を渡す

### 2. `src/sst/processor.py`

新規追加候補:

- `AlbumExecutionProfile` dataclass
- `_build_album_execution_profile(track_count: int) -> AlbumExecutionProfile`

役割:

- `track_count` を見て tier を決定
- `profile` を `consolidate_virtual_albums()` 呼び出しへ渡す

現在の

```python
num_ctx = getattr(self.config, "llm_ollama_num_ctx", 32768)
```

は、profile ベースに置き換える。

### 3. `src/sst/llm.py`

変更点:

- `consolidate_virtual_albums()` に `execution_profile` 引数を追加
- `_call_llm()` に渡す `num_ctx` を request ごとに `execution_profile.num_ctx_cap` で制約
- Phase 2 の worker 数を `self.llm_request_parallelism_max_workers` ではなく `execution_profile.phase2_parallel_workers` 優先で決定
- `force_coherence` が true なら `coherence_threshold` 未満でも Phase 1.5 を実行可能にする

追加候補 helper:

- `_resolve_execution_num_ctx(profile, request_estimate)`
- `_resolve_phase2_worker_count(profile, segment_count)`

### 4. `.env.example`

追記する設定群:

```env
LLM_ALBUM_TIER_SMALL_MAX_TRACKS=50
LLM_ALBUM_TIER_MEDIUM_MAX_TRACKS=100

LLM_OLLAMA_NUM_CTX_SMALL=8192
LLM_OLLAMA_NUM_CTX_MEDIUM=16384
LLM_OLLAMA_NUM_CTX_LARGE=32768

LLM_REQUEST_PARALLELISM_MAX_WORKERS_SMALL=3
LLM_REQUEST_PARALLELISM_MAX_WORKERS_MEDIUM=2
LLM_REQUEST_PARALLELISM_MAX_WORKERS_LARGE=1

LLM_FORCE_COHERENCE_LARGE=true
```

コメントで以下を明記する:

- 小型アルバムは throughput 優先
- 中型アルバムはバランス型
- 大型アルバムは一貫性優先

### 5. `README.md`

追加する内容:

- `ornith:9b` 向け tiered profile の説明
- `16384 / workers=2` を標準推奨
- `8192 / workers=3` を速度寄り比較候補
- `32768 / workers=1` を大型アルバム向け一貫性優先候補

---

## Backward Compatibility

既存ユーザーへの影響を抑えるため、以下のフォールバックを入れる。

- tier 用新規設定が未指定なら、既存の `llm_ollama_num_ctx` と `llm_request_parallelism_max_workers` を共通値として使う
- `execution_profile` が渡されない場合は従来挙動に戻る
- `coherence_threshold` は既存値を維持し、`force_coherence` は追加条件として扱う

---

## Risk Analysis

### Risk 1: Small tier の `num_ctx` が低すぎて quality 劣化

対策:

- `1027880` のような安定ケースだけでなく `1586580`, `1270860` で比較
- review 悪化が出たら tier cap を引き上げる

### Risk 2: Large tier で worker 数を 1 にすると throughput が落ちすぎる

対策:

- Phase 2 全体を 1 worker にするだけでなく、identity / coherence を確実に厚く取ることで再試行や review 増加を防ぎ、総時間で判断する

### Risk 3: force_coherence が過剰に働く

対策:

- 初期実装では `Large` tier のみ `force_coherence=true`
- `Medium` では threshold 条件を維持

### Risk 4: 設定項目が増えすぎて理解しづらい

対策:

- `.env.example` には標準推奨値を明記
- README に profile 別の用途を短く整理

---

## Validation Plan

各 tier 設定候補で、最低限次を確認する。

### App Set

- `1027880`
- `1586580`
- `1270860`

### Metrics

- `status`
- `confidence_score`
- `integrity_quality`
- `confidence_reason`
- `avg_done_seconds`
- `peak_inflight_requests`
- `slot_ids_seen`
- truncation retry 回数
- fatal error の有無

### Acceptance Criteria

- `Small` tier で throughput が改善し、複雑ケースの quality 悪化が許容範囲内
- `Medium` tier は現行 16384 / workers=2 と同等以上
- `Large` tier で 100 曲超アルバムの一貫性が改善、または少なくとも悪化しない

---

## Implementation Order

1. `.env.example` の後半に残る `MAX_PARALLEL_ALBUMS` 再定義を削除
2. `config.py` に tier 用設定を追加
3. `processor.py` に `AlbumExecutionProfile` を導入
4. `llm.py` に `execution_profile` 受け渡しと worker / num_ctx 制御を追加
5. `.env.example` に tier 用設定を追記
6. `README.md` に標準 / 比較 / 一貫性優先の 3 プロファイルを追記
7. 単体テスト追加
8. 実測比較

---

## Test Plan

追加候補テスト:

- `tests/test_execution_profile.py`
  - track_count から Small / Medium / Large を正しく選ぶ
  - tier 上限値が正しく profile に反映される

- `tests/test_llm_parallelism.py`
  - `execution_profile.phase2_parallel_workers` が worker 数決定に効く
  - `execution_profile.num_ctx_cap` が `_call_llm()` の `effective_num_ctx` に効く
  - `force_coherence` 時に threshold 未満でも coherence が有効化される

- `tests/test_config.py`
  - 新規 `.env` 設定の読み込み

---

## Expected Deliverables

最終成果物は以下です。

- tier-aware `AlbumExecutionProfile` 実装
- `.env.example` に tier 用設定群
- `README.md` に 3 プロファイルの説明
- 回帰テスト
- 実測結果メモ

---

## Recommendation Before Coding

最初の実装では、次を厳守するのがよいです。

- `Small / Medium / Large` の 3 tier だけに限定する
- `Large` だけ `force_coherence=true`
- `Large` の worker 数は 1 から始める
- `Medium` の標準推奨は現状の `16384 / workers=2` を維持する

これなら、既存実測で安定している基準を壊さずに段階的に拡張できます。