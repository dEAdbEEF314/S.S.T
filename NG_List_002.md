# 今回のデバッグでも【救われなかった】アルバムリスト (NG_List_002)

前回の改修（タグによる重複排除強化・優先度付きマージ・ダウンサンプリング制限等）を適用した結果、18件のうち **1件** が正常に `ARCHIVE` へ救済され、依然として `REVIEW` 判定のまま残ったのは **17件** となりました。

## ⚠️ 依然として REVIEW 判定のまま救われなかったアルバム（計 17 件）

| AppID | アルバム名 | 最終ステータス | REVIEW（救われなかった）要因 |
| :--- | :--- | :--- | :--- |
| **[410790](https://store.steampowered.com/app/410790)** | Broforce: The Soundtrack | `REVIEW` | `[Duplicates (3)]` |
| **[467300](https://store.steampowered.com/app/467300)** | Crypt of the NecroDancer Extended Soundtrack 2 | `REVIEW` | `[Duplicates (17), Quality too low (85%)]` |
| **[870530](https://store.steampowered.com/app/870530)** | Warhammer 40,000: Gladius - Relics of War - Soundtrack | `REVIEW` | `[Track#0 x25, Duplicates (23)]` |
| **[924330](https://store.steampowered.com/app/924330)** | The Messenger Soundtrack - Disc I: The Past [8-Bit] | `REVIEW` | `[Duplicates (6)]` |
| **[972380](https://store.steampowered.com/app/972380)** | Holy Potatoes! A Spy Story?! Soundtrack | `REVIEW` | `[Duplicates (3)]` |
| **[1586580](https://store.steampowered.com/app/1586580)** | Narita Boy Soundtrack | `REVIEW` | `[Track#0 x21, Duplicates (34)]` |
| **[1816580](https://store.steampowered.com/app/1816580)** | Happy’s Humble Burger Farm: Rock the Warehouse (OST) | `REVIEW` | `` |
| **[1832390](https://store.steampowered.com/app/1832390)** | Happy’s Humble Burger Farm: Seacoast Row (OST) | `REVIEW` | `` |
| **[1832400](https://store.steampowered.com/app/1832400)** | Happy’s Humble Burger Farm: Fountain of Guts (OST) | `REVIEW` | `` |
| **[1832440](https://store.steampowered.com/app/1832440)** | Happy's Humble Burger Farm: Super Barnyard Buds (OST) | `REVIEW` | `` |
| **[1832460](https://store.steampowered.com/app/1832460)** | Happy's Humble Burger Farm: Mutual Decline (OST) | `REVIEW` | `` |
| **[1832470](https://store.steampowered.com/app/1832470)** | Happy's Humble Burger Farm: Hypnosystemic (OST) | `REVIEW` | `[Duplicates (62), LLM's decision (Low Confidence/Ratio)]` |
| **[1851920](https://store.steampowered.com/app/1851920)** | Milk outside a bag of milk outside a bag of milk Soundtrack | `REVIEW` | `[Track#0 x4, Duplicates (3)]` |
| **[2665000](https://store.steampowered.com/app/2665000)** | Super Woden GP 2 Soundtrack | `REVIEW` | `[Track#0 x20, Duplicates (19)]` |
| **[3107200](https://store.steampowered.com/app/3107200)** | Anger Foot Soundtrack | `REVIEW` | `[Duplicates (8)]` |
| **[3162910](https://store.steampowered.com/app/3162910)** | Parking Garage Rally Circuit Soundtrack | `REVIEW` | `[Track#0 x14, Duplicates (13)]` |
| **[3282950](https://store.steampowered.com/app/3282950)** | Karate Survivor Soundtrack | `REVIEW` | `[Track#0 x7, Duplicates (6)]` |

---

## 🎉 今回の改修によって正常に ARCHIVE に救済されたアルバム（計 1 件）

- **[396690](https://store.steampowered.com/app/396690)** | La-Mulana Original Sound Track -> `archive` に救済！

---

## 🔎 残った REVIEW アルバムの傾向と次ステップの考察
1. **`Track#0`（トラック番号0）問題**:
   - 残ったアルバムの多くは、元ファイルのタグ自体にトラック番号が `0`（または空）のトラックが存在し、システムバリデーターが弾いている状態です。これはローカルファイル固有の不備であり、元ファイル側のタグ（TRCK）の手動修正、あるいはプログラム側での `Track#0` 許容ロジックの導入が必要です。
2. **重複（Duplicates）が残っているケース**:
   - グループ化を強化してもなお重複が残っている場合、元のディレクトリ内に同一曲が3つ以上存在するなどの、より複雑な重複が発生している可能性があります。個別のZIP内 `metadata.json` の解析が必要です。
