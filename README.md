# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

S.S.T は、Steamで購入したゲームサウンドトラックを自動的に識別・整列し、極めて高品質なメタデータを補完・付与してライブラリ化する、高精度なスタンドアロンCLIツールです。
Steam ストア情報、MusicBrainz、AcoustID、およびローカル音源のタグ情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整列」によって統合します。

仕様策定からアーキテクチャ設計、コード実装、全数データ分析、そしてテスト構築に至るまで、開発者と Google DeepMind の **Gemini** による濃密なペアプログラミングによって徹底的に鍛え上げられており、Steam実戦環境（全344アルバム）において **処理成功（自動アーカイブ）率 90.99% (313/344件)** という極めて高いスループットと信頼性を達成しています（残る 9.01% / 31件も、音源物理欠落・公式リスト不在・微細音声破損を正しく防御した健全なReviewです）。

---

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

### ドキュメント導線
- **現行仕様の正本**: [`docs/METADATA_SOURCE_SPEC.md`](docs/METADATA_SOURCE_SPEC.md)（設計判断・タグ優先順位は必ずこれに従います）
- **変更履歴**: [`CHANGE_HISTORY.md`](CHANGE_HISTORY.md)（時系列降順での全変更記録）
- **運用/環境**: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/configuration.md`, `docs/TEST_ENVIRONMENT.md`, `docs/error_handling.md`
- **退役・バックアップ**: `docs/archive/old/`, `docs/archive/v0.1/`（現行仕様とは異なります）

---

## 🚀 システムアーキテクチャ
S.S.T は **Steam を構造の絶対的な正本（Ground Truth）とするローカル完結型処理系** です。処理はローカルマシン上で安全に実行され、LLM はトラック生成を行わず「各ファイルをSteamスロットへ割り当てる判断者」としてのみ機能します。

### コア・パイプライン
1. **STEAM 骨格構築**: AppID から PICS / Store API 経由で公式アルバム情報とトラック一覧を取得し、正規スロット（Disc, Track, Title）を定義します。
2. **Fast-Track 先行判定（オンデマンド信号収集）**: 音源ファイル数と Steam スロット数が 1:1 完全一致する場合、重い外部 API（MusicBrainz/AcoustID）や LLM を完全バイパスして即座に決定論的確定（全体の約75%以上が瞬時に通過）。
3. **プレマッチ & 差分推論 (Differential Alignment)**: Fast-Track を満たさない複雑なアルバムでは、番号・タイトル完全一致や AcoustID で事前確定したスロットを LLM 入出力から除外し、未確定トラックと空きスロットのみを差分で 1-shot 推論。
4. **フォーマットバリアント自動統合**: FLAC + MP3 + WAV など複数フォーマットが混在する場合でも、拡張子・Stem・トラック番号・再生時間差（<1.0s）の厳格な照合により同一スロットのバリアントとして自動統合。
5. **タグ構築 & アーカイブ事前検証 (Zero-padding Normalization)**: DJ機材互換の ID3v2.3 タグを構築。トラック番号のゼロ埋め正規化（`01` と `1` の表記ブレ解消）を適用した上で、物理成果物の存在・タグ・スロット充足度を完全事前検証し、ZIP アーカイブを出力。

---

## ✨ 主な特徴と改善機能

- **STEAM First (構造の絶対的正)**: タイトル、トラック順、ディスク構造の骨格は常に Steam 公式情報を絶対基準とし、ハルシネーションによるタグ創作を原理的に排除。
- **実戦処理成功率 90.99%**: 344件の実戦バッチにおいて 313件を完全自動アーカイブ。
- **差分推論 (Differential Alignment)**: LLM トークン消費と推論時間を最小化し、トークン枯渇（Truncation）による不当な Review 落ちを防止。
- **スロットキー解決の堅牢化**: LLM が `"STEAM_SLOT_0"` などのプレフィックス付きキーを出力した場合でも、パーサーが数値を安全に抽出して解決。
- **トラック番号ゼロ埋め正規化契約**: Steam側（`1`）とタグ側（`01`）の表記ブレを `lstrip('0') or '0'` で一貫して正規化し、偽の不一致（Missing/Unexpected）を根絶。
- **音声変換警告（audio_warn）の監査分離**: Rice 符号化異常などの微細フレーム異常を検出した場合、大音量リスニング環境での安全のため Review を維持しつつ、該当トラック番号（例: `Track 03, 08`）をログ・Discord通知・ZIP内 `AUDIT_REPORT.html` に明記。
- **親ゲーム高解像度看板優先**: サントラ単体のヘッダー画像にとどまらず、親ゲームの高解像度看板画像（Header/Capsule）を優先取得し、複数サントラ時はサントラ固有看板を排他選択。
- **厳格な検証ポリシー (Review Isolation)**: 曲数不足や公式トラックリスト不在、物理破損は黙って通さず、理由・証拠付きで `output/review/` へ完全隔離。

---

## ⚙️ システムカスタマイズ (System Customization)
S.S.T は `.env` ファイルを通じて、システムの並列性能やAPIの安全性を極限までチューニングできます。

### LLM チャンク制御およびモデル設定
- **`LLM_BACKEND`**: `OLLAMA`（ローカル）または `GEMINI`（クラウドAPI）を選択。
- **`LLM_MODEL`**: 推奨ローカルモデルは `ornith:9b`。
- **`LLM_OLLAMA_NUM_CTX` / `LLM_OLLAMA_NUM_PREDICT`**: Ollama利用時のコンテキスト長（32768推奨）と出力上限（8192推奨）。
- **`LLM_ALBUM_TIER_*`**: アルバムの曲数帯（Small / Medium / Large）に応じて `num_ctx` 上限や Phase 2 並列ワーカー数を自動切り替え。

### 音声エンコードおよび並列制御
- **`MAX_ENCODING_TASKS`**: FFmpegによる音声フォーマット変換の同時実行プロセス数（SSD環境で `4` 〜 `8` 推奨）。
- **`MAX_PARALLEL_ALBUMS`**: システム全体で同時に進行するアルバム処理の基本並行数。

---

## ✅ 動作確認済み環境
- **OS**: Linux (Ubuntu 24.04 LTS 等)
- **dGPU**: NVIDIA GPU (16GB VRAM以上推奨、ローカルLLM使用時)
- **Software**: 
  - **FFmpeg**: 必須（音声変換用）。システム PATH に配置してください。
  - **Python**: 3.12 以上 (`uv` での管理を強く推奨)
  - **Ollama**: ローカルLLM推論用 (オプション)
  - **PICS Bridge API**: Steam 内部メタデータ取得用のエンドポイント ([steamcmd/api](https://github.com/steamcmd/api))

---

## 🏗️ セットアップと起動

### 1. インフラの準備と設定
```bash
# Steam PICS Bridge の起動 (Docker例)
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
```
`.env` ファイルを用意し、`STEAM_PICS_BRIDGE_URL` や LLM 関連設定（APIキー等）を記述します。

### 2. S.S.T の実行
```bash
# 依存関係の同期 (プロジェクトルートで実行)
uv sync

# 単体テストの実行 (166件全PASSを確認)
uv run pytest tests/

# 10件のアルバムをテスト実行
uv run python -m sst.main --limit 10

# 全未処理アルバムを一括実行 (開発ログ・中間ファイル保持モード)
uv run python -m sst.main --all --dev --yes

# 特定の AppID を指定して強制再実行
uv run python -m sst.main --appid 1568690,1702020 --force --dev --yes
```

---

## 🏷️ タグ仕様 (ID3v2.3 準拠)
DJ機材（CDJ等）との完全互換性を確保するため、以下のID3v2.3仕様を厳格に順守します：
- **エンコーディング**: UTF-16 with BOM (encoding=1)（TLAN除く）
- **TIT2**: 公式トラック名（改変・誤削除なし）
- **TPE1**: アーティスト名（AcoustID / MusicBrainz 優先）
- **TPE2**: アルバムアーティスト（Steam `開発元, パブリッシャー` 固定）
- **TALB**: アルバムタイトル
- **TRCK / TPOS**: トラック連番（`01` 等）および ディスク番号（`1/1` 等）
- **TYER**: リリース年（TDRCは不使用）
- **APIC**: Type 3 (Front Cover) 固定の高解像度アートワーク
- **COMM**: `既存コメント, 親ゲーム名, 親ゲームURL, [Steamジャンルタグ1/ タグ2/ ...]`

---

## ⚠️ レビューと監査レポート
- **成果物の完全性保証**: 確証が得られないアルバムや微小音声警告を含むアルバムは `output/review/` 配下に隔離保存されます。
- **監査レポート (`AUDIT_REPORT.html`)**: 各アルバムの ZIP 内に同梱。判定理由、各ソース（Steam / MBZ / AcoustID / Local）の突合結果、処理経路（Route）バッジ、および音声警告対象トラック番号が明記されます。
- **Discord 通知**: 処理完了時にステータス（ARCHIVE / REVIEW）、確信度スコア、処理経路、音声警告詳細がリッチ通知されます。

---

## ❤️ 最後に
もし、このシステムがあなたの役に立ち、気に入っていただけたなら、**明日あなたの周りで見かける「誰か困っている人」を、ほんの少しだけ助けてあげてください。** それがこのシステムへの一番の対価です。

---
---

# S.S.T (Steam Soundtrack Tagger) - English

S.S.T is a high-precision, standalone CLI tool that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata from the Steam store, MusicBrainz, AcoustID, and local audio files using LLM-assisted "Factual Metadata Alignment."

Jointly architected, implemented, and verified through intensive pair programming between the developer and Google DeepMind's **Gemini**, S.S.T achieves an outstanding **90.99% automated archive success rate (313 out of 344 albums)** across full real-world Steam soundtrack runs. The remaining 9.01% (31 albums) are healthy, legitimate Review quarantine cases (missing tracks, missing official store lists, or corrupt frames).

---

## 📝 Documentation Map
- **Authoritative Spec**: [`docs/METADATA_SOURCE_SPEC.md`](docs/METADATA_SOURCE_SPEC.md) (All field precedence and contracts)
- **Change History**: [`CHANGE_HISTORY.md`](CHANGE_HISTORY.md) (Reverse-chronological log of all modifications)
- **Deployment & Config**: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/configuration.md`, `docs/TEST_ENVIRONMENT.md`

---

## 🚀 System Architecture & Pipeline
1. **Steam Skeleton**: Constructs the canonical structure (Disc, Track, Title) directly from Steam PICS and Store API.
2. **Fast-Track Gate (On-demand Signals)**: If track counts and numbers match 1:1, deterministically finalizes without LLM inference (~75%+ pass rate).
3. **Differential Alignment**: Pre-matches deterministic tracks (AcoustID, exact numbers/titles) and prompts the LLM only for remaining unaligned slots.
4. **Format Variant Consolidation**: Automatically groups FLAC, MP3, and WAV files for the same track under one slot based on 4-way matching (extension, stem, track number, duration delta <1.0s).
5. **Tagging & Preflight Check (Zero-padding Normalization)**: Applies strict ID3v2.3 tagging, normalizes zero-padded track numbers (`01` vs `1`), and performs an artifact preflight check before archive packaging.

---

## ✨ Key Capabilities
- **STEAM as Truth**: Canonical track titles and numbering follow Steam strictly to eliminate hallucinations.
- **90.99% Real-world Throughput**: Proven on 344 diverse Steam soundtracks.
- **Zero-padding Normalization**: Resolves discrepancies between Steam (`1`) and local tags (`01`) across validation and preflight checks.
- **Audio Warning Separation**: Quarantines Rice-encoding or decode-warning tracks to Review while explicitly listing the affected track numbers (e.g., `Track 03, 08`) in logs, Discord alerts, and `AUDIT_REPORT.html`.
- **High-Resolution Cover Art Priority**: Prioritizes parent game header/capsule images and resolves multi-soundtrack exclusivity.

---

## 🏗️ Setup & Execution
```bash
# Install dependencies
uv sync

# Run all automated tests (166 passed)
uv run pytest tests/

# Process 10 albums
uv run python -m sst.main --limit 10

# Process all unprocessed albums with debug preservation
uv run python -m sst.main --all --dev --yes
```

---

## ❤️ A Final Request
If you find this system useful, **please help someone in need tomorrow, even in a small way.** That is the best way to "pay" for this software.
