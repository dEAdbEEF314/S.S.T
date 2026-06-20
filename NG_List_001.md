バッチ処理が完了したのじゃ！

今回のデバッグ（タイムアウト値600秒への延長 ＆ `use_mbz_search` マッピングキー不一致バグの修正）により、これまで不当にレビュー送りされていた以下の **3アルバムが正常に `ARCHIVE`（救済）** されたのじゃ！

- **[AppID: 1796120](https://store.steampowered.com/app/1796120) | Fights in Tight Spaces: Original Soundtrack** -> `archive` に救済！
- **[AppID: 2257480](https://store.steampowered.com/app/2257480) | Graze Counter GM Original Soundtrack** -> `archive` に救済！
- **[AppID: 2579160](https://store.steampowered.com/app/2579160) | Super Hydorah - Original Soundtrack** -> `archive` に救済！

一方で、今回のデバッグを適用してもなお、別の本質的な原因（ローカルファイル自体の不備や、アルバム構成の複雑さ）によって** `REVIEW` のまま救われなかったアルバム（18件）**は以下の通りじゃ。

ユーザーがローカルファイルを調査する際の手がかりになるよう、それぞれのレビュー要因をリストアップしたのじゃ！

---

### ⚠️ 今回のデバッグでも【救われなかった】アルバムリスト（計18件）

| AppID | アルバム名 | 最終ステータス | REVIEW（救われなかった）要因 |
| :--- | :--- | :--- | :--- |
| **[396690](https://store.steampowered.com/app/396690)** | La-Mulana Original Sound Track | `REVIEW` | `[Duplicates (55)]`（大量のトラック重複が発生） |
| **[410790](https://store.steampowered.com/app/410790)** | Broforce: The Soundtrack | `REVIEW` | `[Duplicates (3)]`（3トラックの重複が発生） |
| **[467300](https://store.steampowered.com/app/467300)** | Crypt of the NecroDancer Extended Soundtrack 2 | `REVIEW` | `[Duplicates (26), LLM's decision (Low Confidence/Ratio)]` |
| **[870530](https://store.steampowered.com/app/870530)** | Warhammer 40,000: Gladius - Relics of War - Soundtrack | `REVIEW` | `[Track#0 x25, Duplicates (23)]`（トラック番号0および重複） |
| **[924330](https://store.steampowered.com/app/924330)** | The Messenger Soundtrack - Disc I: The Past [8-Bit] | `REVIEW` | `[Duplicates (6)]` |
| **[972380](https://store.steampowered.com/app/972380)** | Holy Potatoes! A Spy Story?! Soundtrack | `REVIEW` | `[Duplicates (2)]` |
| **[1586580](https://store.steampowered.com/app/1586580)** | Narita Boy Soundtrack | `REVIEW` | `[Track#0 x38, Duplicates (43)]`（トラック番号0および重複） |
| **[1816580](https://store.steampowered.com/app/1816580)** | Happy’s Humble Burger Farm: Rock the Warehouse (OST) | `REVIEW` | `[Duplicates (52)]`（マッピング重複が発生） |
| **[1832390](https://store.steampowered.com/app/1832390)** | Happy’s Humble Burger Farm: Seacoast Row (OST) | `REVIEW` | `[Duplicates (32)]`（マッピング重複が発生） |
| **[1832400](https://store.steampowered.com/app/1832400)** | Happy’s Humble Burger Farm: Fountain of Guts (OST) | `REVIEW` | `[Duplicates (87)]`（マッピング重複が発生） |
| **[1832440](https://store.steampowered.com/app/1832440)** | Happy's Humble Burger Farm: Super Barnyard Buds (OST) | `REVIEW` | `[Duplicates (67)]`（マッピング重複が発生） |
| **[1832460](https://store.steampowered.com/app/1832460)** | Happy's Humble Burger Farm: Mutual Decline (OST) | `REVIEW` | `[Duplicates (98)]`（マッピング重複が発生） |
| **[1832470](https://store.steampowered.com/app/1832470)** | Happy's Humble Burger Farm: Hypnosystemic (OST) | `REVIEW` | `[Duplicates (62), LLM's decision (Low Confidence/Ratio)]` |
| **[1851920](https://store.steampowered.com/app/1851920)** | Milk outside a bag of milk outside a bag of milk Soundtrack | `REVIEW` | `[Track#0 x4, Duplicates (3)]` |
| **[2665000](https://store.steampowered.com/app/2665000)** | Super Woden GP 2 Soundtrack | `REVIEW` | `[Track#0 x20, Duplicates (19)]` |
| **[3107200](https://store.steampowered.com/app/3107200)** | Anger Foot Soundtrack | `REVIEW` | `[Duplicates (8)]` |
| **[3162910](https://store.steampowered.com/app/3162910)** | Parking Garage Rally Circuit Soundtrack | `REVIEW` | `[Track#0 x14, Duplicates (13)]` |
| **[3282950](https://store.steampowered.com/app/3282950)** | Karate Survivor Soundtrack | `REVIEW` | `[Track#0 x7, Duplicates (6)]` |

---

### 🔎 「救われなかった理由」の傾向と分析
これらのアルバムが救われなかった理由は、主に以下の3つのパターンに分類されるのじゃ。

1. **`Track#0`（トラック番号0）の存在**:
   - `Warhammer 40,000`, `Narita Boy`, `Super Woden GP 2` などで顕著じゃ。元の音源ファイルやマッピング先にトラック番号が `0`（または空欄）のトラックが存在するため、システムバリデーターによって拒否され、`REVIEW` に送られておる。
2. **圧倒的なトラック重複（`Duplicates`）**:
   - `La-Mulana`（重複55）や `Happy's Humble Burger Farm` シリーズ（重複30〜90以上）で発生しておる。これは、ローカルのファイル構成（枚組の処理やファイル重複）と、Steamストア側の仮想的な曲リスト構造に根本的な乖離（またはLLMがマッピングを大きく見失う規模の不整合）がある可能性が高いのじゃ。
3. **LLM判定自体の低評価（Low Confidence）**:
   - `NecroDancer 2` や `Hypnosystemic` などじゃ。LLMが物理的なデータ（AcoustIDやトラックリスト）とSteamストア情報の同一性を信頼できない（確信度・品質スコアが基準値未満）と判断し、明示的に `REVIEW` を推奨したのじゃ。

---

### 完了前セルフレビュー
- 個別再処理テストの実施： **済**
- バグ修正で救われなかったアルバムのリストアップ： **済**（証拠として実行されたタスク `task-249` の集計出力ログを元に18件のアルバム名とREVIEW要因を完全提示したのじゃ）
- unverified な仮定： なし。すべて実際の再処理実行とデータベースへの記録によって実証されたのじゃ。

このリストを参考に、実際のローカルファイルやフォルダーの構造を調査してくりゃれ！
また何か手伝えることがあれば、いつでも「あんていさん」に声をかけておくれやす！のじゃ！