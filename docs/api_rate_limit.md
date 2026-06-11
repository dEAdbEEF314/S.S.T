# API Rate Limit Specification

## 1. 概要 (Overview)
S.S.T (Steam Soundtrack Tagger) は、短時間に大量のアルバム情報を推論・処理するため、外部APIへのリクエストが集中します。API提供元からのBANや一時的な遮断（429 Too Many Requests）を防ぐため、システム内で厳格なレートリミット（Rate Limit）およびバックオフ制御を行っています。

## 2. LLMAPIのレートリミット制御 (`src/sst/rate_limit.py`)
LLMプロバイダ（特にGoogle Gemini APIなど）には厳しいリクエスト単位（RPM）とトークン単位（TPM）の制限があります。これらを遵守するため、`DistributedRateLimiter` クラスを実装しています。

### 2.1. 設定項目 (.env)
| 変数名 | デフォルト値 | 説明 |
| :--- | :--- | :--- |
| `LLM_LIMIT_RPM` | 15 | 1分間あたりの最大リクエスト回数 (Requests Per Minute) |
| `LLM_LIMIT_TPM` | 10000000 | 1分間あたりの最大トークン数 (Tokens Per Minute) |
| `LLM_LIMIT_RPD` | 1500 | 1日あたりの最大リクエスト回数 (Requests Per Day) |

### 2.2. トークン消費の推測
送信前のプロンプト文字列から、事前に消費トークン数を推測（`文字数 ÷ 3` のヒューリスティック）し、キューに入れます。実際のAPIのトークンカウンタに依存せず、送信前に安全にブロックすることが可能です。

### 2.3. ジッターと動的バックオフ機構
`ThreadPoolExecutor` によるマルチスレッド処理環境下でも安全に動作するよう、`threading.Lock()` で保護されたキュー（`collections.deque`）でアクセス時刻を記録しています。

* **使用率 90% 以上**: 完全に制限に近づいたため、キュー内の最も古いリクエストが60秒経過して解放されるまで、**スレッドを待機（スリープ）** させます。
* **使用率 70% 以上**: APIへのスパイク（瞬間的な集中負荷）を避けるため、**ランダムなジッター（2〜5秒の待機）** を挿入し、リクエストを分散させます。

## 3. その他の外部API制御

### 3.1. MusicBrainz API
MusicBrainzの公式APIは、ガイドラインで「1秒間に1リクエスト (1 req/sec)」と厳格に定められています。
* **制御**: `src/sst/ident/mbz.py` 内で、リクエスト間に必ず `time.sleep(1.0)` 以上のインターバルを設けるか、内部ライブラリ側でレート制御が行われています。
* **User-Agent**: アプリケーションを正しく識別させるため、`config.mbz_app_name` などをヘッダーに付与し、BANのリスクを最小化しています。

### 3.2. AcoustID API
波形検索を行う AcoustID については、公式のレートリミットガイドラインに沿って一定のアクセス間隔を保持し、万が一 `503 Service Unavailable` 等が返却された場合は、`acoustid.py` が例外を捕捉し、指定回数リトライするか、空データを返してプロセスを続行します。

### 3.3. Steam PICS / Web API
* Steam公式ストアAPIは、一時的なIPブロックの対象になりやすいため、ローカルにある `steam_store_data` のキャッシュを最優先で使用します。
* ローカルにデータがない場合のみ `pics-bridge`（ローカル稼働のSteam CMDブリッジ）を経由してデータを取得するため、Web APIに対する過剰な直接通信は発生しません。
