# S.S.T 監査・中間成果物仕様

## 目的

S.S.T は Steam の公式スロット構造を正本として、物理出力と判断根拠を後から再検証できる状態で保存する。Archive は「LLM がそう判断した」だけでは成立せず、最終ファイル、タグ、Steam slot、件数を再走査した preflight を通過しなければならない。

## 判定と監査

- Steam に存在する `Unknown` / `Unknown (Unused)` は正規タイトルとして扱う。
- Steam の同一 slot が通常タイトルなのに、最終タグだけ `Unknown` の場合は異常 Unknown とする。
- 同一 Steam slot に複数形式の候補がある場合は、形式違い候補として品質 tier の高い1ファイルへ統合する。
- 同一 slot の最終重複は、形式違い候補の統合後にも残った場合だけ構造異常とする。
- LLMが同じslotへ異なる論理タイトルを割り当てた場合、Steamタイトルまたは決定論的証拠で支持できない候補を割当から外し、`contradictory_slot_assignments` と未割当理由へ記録してReviewとする。
- ファイル名またはローカルtrack番号だけでSteam slotを確定しない。ローカルdiscが不一致でも、正規化タイトルが一意なSteam slotと一致し、形式と再生時間がバリアント条件を満たす場合に限り統合する。
- 変換後のファイル参照パスはtrack間で一意でなければならない。slot違いの同名入力は衝突しないステージ名に変換し、metadata参照とZIP実体を1:1で検証する。
- Review 理由は `primary_review_cause` と `secondary_review_causes` に分けて保存する。
- 未割当ファイルは、slot 不一致、候補過剰、LLM 未割当、変換失敗などの上流理由を保持する。
- identity JSONは一般repairを行わない。`chosen_mbz_id`直前の余分なquoteが1個だけあり、それを除くとJSON object全体がparseできる厳密な既知ケースのみ修復し、repair code/fieldを構造化ログと`llm_log.json`へ残す。他fieldの破損・複数箇所・truncationは従来どおりretry/Reviewとする。

各処理結果の監査情報には、Steam期待slot数、最終採用slot数、重複slot数、正規Unknown数、異常Unknown数、入力数、採用数、未割当数、Archive preflight問題を含める。
`TRACKS_ADOPTED.adopted_file_count` は採用済みslot数（採用dictのrecord数）と一致させ、variant配列内のキー数を誤って合算しない。slot矛盾・ファイルパス重複・最終実体不足はArchive preflightのReview理由に含める。

copyの最終失敗はFFmpeg変換へ渡さず、通常バッチ完了後の一回限りの居残り再試行へ送る。再試行後も失敗したAppIDは`Deferred Copy Recovery Exhausted (N)`でReview確定する。`metadata.json.audit`には遅延copy件数・回復件数・最終失敗件数を保存し、最終失敗の詳細ログは全件保持する。

Fast-Trackの`llm_log.json.alignment_res.slots`は`<disc>_<track>`をslot keyとして使う。ディスクを省略した曲番だけのkeyは、複数ディスクで曲番が再利用されると割当を誤集約するため使用しない。
`metadata.json.audit.format_selection`にはslotごとの候補format件数と優先順位、最良候補format、採用source format、および両者の一致判定を保存する。入力ファイル名・パスは記録せず、採用形式の事後監査に必要な最小情報に限定する。不一致は監査HTMLで明示し、採用形式を確認できない場合は未検証として区別する。

Archive前には、最終TIT2を同じ`(disc, track)` slotの正本titleと照合する。通常routeの正本はSteam、`MBZ_STEAM_VERIFIED`は検証済みMBZ tracklistとし、正規化はHTML unescape・Unicode NFKC・空白正規化・casefoldに限定する。不一致は`Official Title Mismatch (N)`としてReviewにする。title comparisonは音声contentの同定と区別する。

最終trackの`field_provenance`には、タグ各fieldの実採用sourceを保存し、`audit.field_provenance`およびZIP内HTMLに集計する。sourceは来歴であり正答保証ではない。欠落sourceは`NOT_RECORDED`/`UNKNOWN`として残し、推測で埋めない。source mapはID3 tag値から分離する。

## LLM

LLM 応答の `done_reason=length` / `max_tokens` は成功扱いにしない。再試行し、各試行の所要時間、終了理由、prompt/eval token 数、切り詰めフラグを `llm_log.json` に保存する。JSON はオブジェクトであることを検証し、配列や壊れた応答を downstream に渡さない。

チャンクサイズは固定値ではなく、実行 tier、推定 prompt、track あたり出力 token、安全率から制御する。チャンクが大きすぎる場合は縮小し、整列を安全側へ倒す。

## SST_WORKING_DIR

- 通常の INFO 実行: `final_<AppID>_*`、`buffer_<AppID>_*`、`early_review_<AppID>_*` を処理終了時に削除する。
- `--dev` 実行: 中間成果物を保持する。
- `LOG_LEVEL=DEBUG`: 中間成果物を保持する。
- `--force` かつ保持モード: 既存成果物を事前削除しない。
- `--force` かつ通常モード: 対象 AppID の既存試行だけを事前削除する。
- 専用 cleaner の明示実行は、保持モードとは独立した手動操作である。

保持時は AppID、パス、保持理由をログへ出力する。中間成果物は機密情報を含み得るため、共有フォルダへ無制限に置かず、確認後に専用 cleaner で削除する。

## バッチ診断HTML

- Fast-Track件数は実行routeの正本である`processing_route == "FAST_TRACK"`のみを数える。メッセージやconfidence reasonの文言からrouteを推定しない。`STEAM_TRUST`はvalidator昇格経路であり、実行route件数へ混ぜない。
- Archiveの事後監査はSteam期待slotと最終slotの集合を直接比較し、件数が等しくてもmissing/unexpected slotがあれば報告する。最終重複、slot_key欠落・重複、track 0、Steam根拠のないUnknown、Fallback/LOCALも確認する。
- Steamの同一slot titleが`Unknown`で始まる場合、そのslotの`Unknown`タグは正規として扱う。Steam側slotが存在しない、または通常タイトルなのに最終タグだけがUnknownの場合は異常とする。
- Review原因は物理I/O、音声品質警告、早期Review、構造不整合、未割当、信頼度・その他を独立に分類する複数ラベルとする。原因は重複し得るため、分類件数の合計ではなくReviewアルバム実数も併記する。物理I/O分類はHTMLに表示し、ログイベントのAppIDと時刻を処理結果の`processed_at`へ照合する。結果時刻より後のイベントや6時間より古いイベントは、その結果の原因に帰属させない。
- 未割当ファイルは余剰ボーナストラックと断定しない。上流の未割当理由を保持し、構造不整合やI/Oとの重複を隠さない。
- バッチ診断HTMLは監査補助であり、`ResultValidator`や各ZIPの`AUDIT_REPORT.html`を置き換えない。件数一致だけで完全性を主張せず、Steam slot・採用ファイル・物理パッケージの根拠を併記する。

## AppID別 AUDIT_REPORT.html の構造差分

- ZIP内の `AUDIT_REPORT.html` はSteam曲リストの行数と、正規化後の一意な`(disc, track)` slot数を分けて表示する。
- 同一slotへ正規化されるSteam複数行は、行位置・曲名・LLM割当ファイル数・最終採用タイトルを併記する。Steam行位置、Steam track番号、正規化slotを混同しない。
- 最終トラック数だけから特定のSteam行が欠落したと断定しない。欠落・余分なslotは一意キー集合で比較し、同じキー内に複数タイトルがある場合は曖昧さとして人間の確認を促す。
- LLMの信頼度やMusicBrainz候補件数は構造差分を上書きしない。レポートは証拠を可視化するものであり、自動採番・Steam構造の置換・Review条件の緩和は行わない。
- Review候補音源は採用トラックと分けて `review_candidates/` に格納する。slot競合、Steam未割当、コピー/変換/タグ処理失敗を分類し、元basename、関連slot、理由、変換状態、ZIP内パスを `review_manifest.json` と `AUDIT_REPORT.html` の双方に記録する。
- 候補音源は通常トラックと同じ品質tierで変換する。変換後の拡張子は実際の出力形式に合わせ、basenameは維持する。変換に失敗した場合は読み出し可能なら元ファイルを退避し、元ファイルも読めない場合は格納失敗と例外型を記録する。Review候補は採用slot数・最終タグ検証に加算しない。

## 回帰テスト方針

Steam の正規 Unknown、通常タイトルに対する異常 Unknown、形式違い候補、重複 slot、LLM 切り詰め、Archiveの相殺slot不整合、複数Review原因、I/O分類、明示route計数、INFO/DEBUG/`--dev` のcleanupを合成fixtureで検証する。既存の実データレポートはテストfixtureとして使わず、レポートとDB metadataの契約を検証する。

## 外部正解によるroute別完全性測定

Archive完了率・confidence・Steam slot一致を音源内容の正答率とみなしてはならない。別の人手または独立fingerprint検証を正解ラベルとし、route×statusの層ごとに再現可能なsampleを作り、`scripts/completeness_audit.py`で結果を集計する。

```bash
uv run python scripts/completeness_audit.py sample --db data/sst_local_state.db --per-stratum 5 --tracks-per-album 3 --seed 20261010 --out .agents/skills/sst-batch-analyzer/scratch/completeness_audit_sample.json
uv run python scripts/completeness_audit.py analyze --input .agents/skills/sst-batch-analyzer/scratch/completeness_audit_sample.json --out .agents/skills/sst-batch-analyzer/scratch/completeness_audit_results.json
```

sample manifestではアルバム正体、slot構造、主要metadataをアルバム単位で、sample音源とtagged titleの一致をtrack単位で人手によりtrue/false/null評価する。アルバムのsample audio全件一致はtrack labelsから自動導出し、重複入力させない。nullは未測定として分母から外し、正解扱いにしない。集計はroute合算とroute/status層別の成功数・失敗数・未評価数およびWilson 95%区間を出す。seed・母集団・route/status層のsample数を保存し、sample対象のZIP member以外のhost path・username・raw logは出力しない。未記入ラベルの段階では正答率を出さず、sample計画だけを報告する。

LLM request統計は`logs/SST_DEBUG_*.log`全体からAppIDと時刻を読み、各AppIDの最新`PROCESS_START`からDBの`processed_at`までに限定する。最新ログ1本の件数を母集団全体のLLM利用数として扱わず、相関できないAppID数も併記する。
