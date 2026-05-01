# **2026年最新技術を統合したSteamサウンドトラック・メタデータ自動整備手法の構築：RTX 4090 Laptop環境におけるハルシネーション・フリーなローカルLLM活用**

## **デジタル音楽管理における構造的変容とSteamプラットフォームの現状**

2026年4月30日現在、PCゲームプラットフォームの最大手であるSteamにおけるサウンドトラックの配信形態は、技術的およびライセンス的な観点から大きな転換点を迎えている。かつて主流であった「ゲーム本体に付随する追加ダウンロードコンテンツ（DLC）」としての配布形式は、2020年初頭に導入された「サウンドトラック・アプリ」形式へと完全に移行を完了した1。この構造的変化により、ユーザーはベースとなるゲームを購入・インストールすることなく音楽のみを購入し、管理することが可能となった。また、開発者はMP3に加えて、FLACやWAVといったハイレゾ音源（無圧縮・ロスレス音源）を独立したデポ（Depot）として提供できるようになり、ユーザーは好みに応じて品質を選択できる環境が整っている2。

しかし、このような配信環境の高度化に反して、提供されるメタデータ（タグ情報）の精度には依然として著しいばらつきが存在する。Steamミュージックプレイヤーは、再生順序の決定をメタデータではなくファイル名に依存するという独自の仕様を維持しており、これが一般的なミュージックサーバーやモバイルデバイスの音楽ライブラリとの整合性を損なう要因となっている2。特に日本人ユーザーにとって、膨大な楽曲群を「五十音順」で正しくソート・表示させるための「読み仮名（Yomi）」や「ソート順（Sort Order）」の設定は、自動化が困難な領域であった。本報告書では、2026年時点の最新ハードウェアであるNVIDIA GeForce RTX 4090 Laptop GPU（16GB VRAM）を活用し、ローカル大規模言語モデル（LLM）と構造化出力技術を組み合わせることで、完全無料でハルシネーション（虚偽情報の生成）を徹底排除した日本人向けメタデータ整備手法を提示する。

### **Steamサウンドトラックの技術的制約とメタデータの重要性**

Steamで配信されるサウンドトラックは、最小要件としてアルバムカバー画像、MP3形式のオーディオファイル、および基本的なアーティスト名やトラックタイトルのメタデータを必要としている2。しかし、Steamworksの設定において、開発者が手動で入力するこれらのデータは、必ずしもオーディオファイル内部のID3タグと一致しているわけではない。Steamミュージックプレイヤーは、ファイル名の先頭に「01 \- 」のようなトラック番号が含まれていることを前提に再生順を決定するため、メタデータが欠落した状態でも「Steam内では」再生が可能である2。

一方で、ユーザーがこれらのファイルをSteam以外の環境（例えば、高性能なデジタルオーディオプレイヤーや、2026年現在普及しているAI搭載型ミュージックサーバー）に持ち出した際、メタデータの欠落は致命的な管理上の支障をきたす。特にマルチディスク構成のサウンドトラックにおいて、ディスク番号（Disc Number）やユニークなトラック番号が適切に付与されていない場合、楽曲の再生順が支離滅裂になる現象が報告されている2。また、日本語タイトルにおいては、漢字の読みが正確に付与されていない限り、多言語環境下でのソート順はUnicodeのコードポイント順に依存してしまい、日本人ユーザーが期待する検索性や組織化を実現することは不可能である5。

## **2026年におけるローカル・コンピュート・リソースの分析とLLMの選定**

本手法の実行環境として想定するNVIDIA GeForce RTX 4090 Laptop 16GBは、2026年4月現在、モバイル環境において最高峰の推論性能を誇る。デスクトップ版の24GB VRAMモデルと比較して容量的な制限はあるものの、Ada Lovelaceマイクロアーキテクチャによる16,384個のCUDAコアと、第4世代Tensorコア（512個）は、最新の混合専門家（Mixture-of-Experts: MoE）アーキテクチャを採用したLLMを動作させるのに十分なスペックを有している6。

### **ハードウェアスペックと推論効率の相関**

RTX 4090 Laptop環境における推論パフォーマンスを最大化するためには、VRAMの占有量と計算スループットのバランスを最適化する必要がある。2026年における主要な推論エンジンであるOllama 0.5.xやvLLMは、FP16から4-bit/8-bit量子化への動的な最適化をサポートしており、16GBのVRAM内で14Bから35Bクラスのモデルを安定して動作させることが可能である6。

| コンポーネント | スペック詳細 (RTX 4090 Laptop) | 2026年時点の意義 |
| :---- | :---- | :---- |
| CUDAコア数 | 16,384 | 並列演算能力による高トークンレートの維持 6 |
| Tensorコア数 | 512 | Transformer演算のハードウェア加速 6 |
| VRAM容量 | 16GB GDDR6 | 中規模MoEモデルの完全オフロードが可能 6 |
| FP32性能 | 約80 TFLOPS以上 | 複雑な構造化生成における低遅延な推論 6 |

このようなハードウェアリソースを前提とした場合、ローカルLLMはクラウドAPIを利用することなく、プライバシーを完全に保護した状態で高速にメタデータ解析を実行できる。これは、数ギガバイトに及ぶサウンドトラックの全ファイルをスキャンし、タグを付与する作業において、ネットワーク遅延や従量課金コストを排除できる大きな利点となる7。

### **2026年最新ローカルLLMの選定基準**

メタデータ整備に用いるLLMには、単なる言語理解能力だけでなく、外部ツール（API）との連携能力や、厳格な出力形式の遵守が求められる。2026年4月時点での主要モデルのベンチマーク結果を基に、以下の3モデルを本手法の核心として選定した8。

1. **Qwen3-14B**: 148億パラメータを持ちながら、16GB VRAM環境で極めて高速に動作する。多言語対応能力が非常に高く、日本語と英語が混在するゲーム楽曲の解析に最適である10。  
2. **Gemma 4 26B-A4B**: Googleの最新MoEモデルであり、有効パラメータを4Bに抑えることで85 tokens/sという驚異的な推論速度を実現している。関数呼び出し（Function Calling）の精度が高く、構造化データの生成においてハルシネーションを最小限に抑える特性を持つ11。  
3. **LLM-jp-4 8B**: 国立情報学研究所（NII）を中心としたLLM-jpコンソーシアムが開発した国産モデル。日本語の文脈理解においてGPT-4oを凌駕するスコアを記録しており、日本語特有の読み仮名生成において決定的な役割を果たす9。

これらのモデルをタスクごとに使い分ける、あるいは単一の高性能モデル（Qwen3-14B等）をOutlinesライブラリで制御することで、信頼性の高いメタデータ生成パイプラインが構築可能となる13。

## **構造化生成（Structured Generation）によるハルシネーションの物理的排除**

LLMをメタデータ整備に活用する上での最大の障壁は、存在しない曲名やアーティスト名を「もっともらしく」捏造するハルシネーション現象である。本手法では、LLMの自由な回答を許さず、数学的に定義された文法（Grammar）やスキーマ（Schema）に沿ったトークンのみを生成させる「構造化生成」を全面的に採用する14。

### **Outlinesライブラリのメカニズムと利点**

2026年現在、構造化生成の標準ライブラリとして君臨しているのが「Outlines」である。Outlinesは、LLMが次のトークンを選択する際の確率分布（ロジット）に対し、定義された文法に合致しないトークンの確率を強制的にゼロにする「ロジット・マスキング」という手法を用いる15。

具体的には、有限状態オートマトン（FSM）を用いて、現在の生成文字列から「次に生成可能な有効な文字」をリアルタイムで判定する。例えば、トラック番号を生成する際、LLMが数値以外の文字（「No.」や「番」など）を出力しようとしても、Outlinesがそれを物理的にブロックし、数値トークンのみを選択させる。このプロセスは生成完了後のパース（解析）とは異なり、生成プロセスそのものを制約するため、形式的な誤りが100%排除される17。

Outlinesの導入によるパフォーマンス向上は顕著であり、従来の「生成しては失敗し、リトライする」手法と比較して、以下のような改善が見られる17。

| 評価指標 | 従来のポストパース手法 | Outlinesによる構造化生成 |
| :---- | :---- | :---- |
| スキーマ遵守率 | 76% | 98% \- 100% 15 |
| 生成速度 | リトライにより低下 | 約5倍高速化（coalescence効果） 15 |
| 計算リソース消費 | 無駄な推論が発生 | 最小限のパスで完了 15 |
| 推論オーバーヘッド | 発生する | ほぼゼロ 14 |

### **Pydanticを用いたメタデータ・スキーマの定義**

本手法では、楽曲情報を抽出するためのデータ構造をPythonのPydanticモデルとして定義する。LLMはこのモデルに定義された型（int, str, Literal等）に従うことのみが許される13。

Python

from pydantic import BaseModel, Field  
from typing import List, Literal, Optional

class TrackMetadata(BaseModel):  
    track\_number: int \= Field(ge=1, le=99)  
    title: str \= Field(description="正規の日本語楽曲タイトル")  
    artist: str \= Field(description="アーティスト名")  
    album: str \= Field(description="アルバム名")  
    disc\_number: int \= Field(default=1)  
    genre: Optional\[str\] \= None  
    yomi\_title: str \= Field(description="楽曲タイトルの全角カタカナ読み")  
    yomi\_artist: str \= Field(description="アーティスト名の全角カタカナ読み")  
    uncertainty: bool \= Field(description="情報が不足している場合にTrueを返す")

このスキーマを用いることで、LLMは読み仮名を生成しつつ、同時に「情報が不明な場合には嘘をつかずにフラグを立てる」という高度な推論を、厳格な形式の中で実行することが可能となる17。

## **MusicBrainz APIを核とした外部データベースとの高度な連携**

ハルシネーションを排除するもう一つの柱は、LLMの内部知識に頼るのではなく、信頼できる外部の音楽データベース（MusicBrainz）を「正解（Ground Truth）」として参照することである。2026年時点のMusicBrainz APIは、Steam AppIDを介したリレーションシップを広くサポートしており、ゲーム固有のサウンドトラック情報を高精度に取得できる18。

### **Steam AppIDとMusicBrainz ID (MBID) の紐付けアルゴリズム**

Steamで購入したサウンドトラックには必ず一意のAppIDが付与されている。MusicBrainzのデータベーススキーマでは、外部サイト（URL）とのリレーションシップが定義されており、SteamのストアページURL（https://store.steampowered.com/app//）をキーにして検索することで、対応する「Release Group」や「Release」のMBIDを特定できる20。

具体的な検索プロセスは、以下のAPIリクエストを通じて行われる。

1. **URL検索**: https://musicbrainz.org/ws/2/url?resource=https://store.steampowered.com/app//\&inc=release-group-rels  
2. **エンティティ特定**: 取得したJSON応答から、release-groupリレーションを抽出し、該当するMBIDを取得する21。  
3. **詳細データ取得**: MBIDを用いて、トラックリスト、アーティスト、レーベル、リリース日などのフルメタデータを取得する18。

MusicBrainz APIの利用に際しては、非商用利用であれば無料であるが、「1秒間に1リクエスト」という厳格なレート制限が存在する18。これを遵守するために、Pythonのratelimitデコレータや、一時的なエラー（503 Service Unavailable）に対する指数関数的バックオフの実装が必須となる25。

### **音響指紋（Acoustic Fingerprinting）による補完と名寄せ**

ファイル名が壊れている、あるいはMusicBrainzにAppIDのリレーションシップが登録されていない場合でも、オーディオデータの波形そのものから情報を特定する「音響指紋」技術が有効である。2026年現在の最新版Chromaprint (fpcalc 1.6.0) は、RTX 4090 Laptopのマルチコア性能を活かし、数秒で楽曲の指紋を生成できる28。

音響指紋に基づく特定フロー：

1. **指紋生成**: fpcalc \-json \[audio\_file\] を実行し、楽曲の持続時間と指紋データを取得する28。  
2. **AcoustID検索**: 生成されたデータをAcoustID APIに送信し、MusicBrainzのRecording ID（MBID）を検索する31。  
3. **メタデータ統合**: 取得した Recording ID を MusicBrainz API でルックアップし、アルバム名やトラック番号を逆引きする30。

この音響指紋による特定プロセスは、特に海外で人気のある日本のJRPGやアクションゲームのサウンドトラックにおいて、ユーザーコミュニティによって精力的にデータが蓄積されているため、極めて高い成功率を誇る30。

## **日本人向けメタデータの最適化：SudachiPyとID3v2.4規格の適用**

日本人ユーザーにとっての理想的な音楽ライブラリとは、全ての楽曲が「あいうえお順」に並び、アーティスト名やアルバム名が適切に正規化されている状態である。これを実現するためには、高度な日本語形態素解析と、音楽ファイルの国際規格（ID3v2.4）への正しい理解が必要となる。

### **SudachiPyとUniDicによる「読み仮名」の自動抽出**

2026年時点において、日本語の形態素解析エンジンとして最も信頼されているのが「SudachiPy」である33。従来のMeCab等と比較して、SudachiPyは「正規化形式（Normalized Form）」の出力をサポートしており、歴史的仮名遣いや異体字の揺れを修正した上で、正確な読み仮名を取得できる34。

メタデータ生成パイプラインにおけるSudachiPyの役割：

1. **テキスト正規化**: LLMが得た漢字タイトルに対し、normalized\_form()を適用して表記を統一する34。  
2. **読みの抽出**: 形態素ごとに「読み（Reading）」を取得し、全角カタカナのソート文字列を生成する33。  
3. **LLMによる文脈補正**: 同一の漢字で複数の読みが存在する場合（例：「楽曲」を「がっきょく」と読むか「たのしみ」と読むか）、LLMが楽曲のジャンルやアーティストの傾向から適切な読みを選択する。

SudachiPyの辞書には、70MB程度の「Core」版に加え、固有名詞に強い「Full」版が存在する。RTX 4090 Laptopの十分なシステムメモリ（32GB〜64GBを想定）を活用すれば、Full版をメモリ上にロードし、極めて高速に処理を完遂できる33。

### **ID3v2.4ソートタグ（TSOT/TSOP/TSOA）の書き込み**

取得した読み仮名は、オーディオファイルのメタデータ規格であるID3v2.4で定義された「ソート順」用フレームに格納する。これにより、日本語を理解できない海外製のプレイヤーであっても、提供されたソート文字列（カタカナ）に基づいて正しい順番で楽曲を表示できるようになる5。

| ID3フレーム | フィールド名 | 格納する内容の例 |
| :---- | :---- | :---- |
| TIT2 | 曲名 (Title) | 英雄の帰還 |
| TSOT | タイトル・ソート順 | エイユウノキカン |
| TPE1 | アーティスト (Artist) | 音楽 太郎 |
| TSOP | アーティスト・ソート順 | オンガクタロウ |
| TALB | アルバム (Album) | 伝説の戦記 オリジナルサウンドトラック |
| TSOA | アルバム・ソート順 | デンセツノセンキオリジナルサウントトラツク |

ID3v2.4は、以前のv2.3と比較してUTF-8エンコーディングが正式にサポートされており、日本語の文字化けリスクが大幅に低減されている36。また、タグの末尾に「フッター」を付加することで、ファイル全体を読み込むことなくタグ情報を高速にスキャンできるため、モバイルデバイスでのパフォーマンスも向上する36。

## **Pythonによるメタデータ自動整備パイプラインの実装**

ここまでの技術要素を統合し、実用的かつ完全無料な自動整備ツールを構築する。このシステムは、ローカルで動作するLLMサーバー（Ollama等）と通信し、MusicBrainz APIを呼び出しながら、最終的にオーディオファイルを更新する一連の流れを自動化する。

### **段階的実行プロセスと例外処理**

システムは、以下のステップで楽曲の同定とタグ付けを実行する。各ステップにおいてLLMはOutlinesによる制約付き出力を維持し、情報の不確実性が高い場合は処理を中断して人間に判断を仰ぐ「ヒューマン・イン・ザ・ループ」の構造を取る17。

1. **ファイルスキャニング**: Steamのインストールディレクトリ（steamapps/music）からオーディオファイルを抽出し、メタデータとAppIDを収集する2。  
2. **LLMによる検索クエリ生成**: ファイル名や既存の部分的タグから、MusicBrainz APIで最もヒットしやすい検索クエリ（Lucene構文）をLLMに生成させる。  
   * 例: recording:"Title" AND artist:"Artist" AND release:"Album" 19  
3. **MusicBrainz API連携**: 生成されたクエリで検索を実行し、候補となるMBIDのリストを取得する18。  
4. **名寄せ（Entity Resolution）**: 取得した複数の候補の中から、LLMが「最も確度の高いもの」を選択する。この際、レーベンシュタイン距離等の文字列類似度を計算し、推論の補助材料として入力する39。  
5. **メタデータ変換と書き込み**: 特定されたMBIDから完全な情報を取得し、SudachiPyで読み仮名を生成した後、mutagen等のライブラリを用いてオーディオファイルにID3v2.4タグを書き込む36。

### **レート制限とスロットリングの数学的モデル**

API利用における「良き市民（Good Citizen）」であるために、リクエストの間隔を厳密に制御する。MusicBrainzが要求する1秒1リクエスト制限に対し、安全マージンを含めた制御を以下のようなリーキーバケット（Leaky Bucket）アルゴリズムで表現する24。

楽曲数を ![][image1] 、API呼び出し1回あたりの期待待ち時間を ![][image2] とすると、全処理時間は次のように近似される。

![][image3]  
ここで ![][image4] はLLMによるクエリ生成時間、 ![][image5] はAPIの応答時間である。RTX 4090 Laptopでは ![][image4] が極めて短いため、ボトルネックは純粋にAPIのレート制限（1.0秒）に収束する。1,000曲のサウンドトラックを処理する場合でも、約1,000秒（16.6分）程度で完了し、バックグラウンド処理としては十分に実用的な速度である6。

## **不確実性の管理とユーザーインターフェースの役割**

LLMと外部データベースを組み合わせても、100%の自動化が不可能なケース（例：MusicBrainzにデータが存在しない最新作、あるいは限定盤）が存在する。このような「エッジケース」を適切に処理することが、システム全体の信頼性を担保する上で不可欠である。

### **確信度スコアリングと「I don't know」の強制**

Outlinesを用いたPydanticモデルの定義において、LLMに「自身の回答に対する確信度（Confidence Score）」を0.0から1.0の範囲で出力させる。同時に、情報の不一致を検出した場合には、特定のユニオン型（Union Type）を用いて「Match Not Found」というステータスを明示的に返させる17。

このアプローチにより、LLMが「何らかの曲名を無理やり当てはめる」というハルシネーションを構造的に防止できる。確信度が一定値（例：0.85）を下回る場合は、ファイルを隔離フォルダに移動し、後述する人間による検証フェーズへと回す17。

### **2026年のローカルAI UI：LM StudioとBeets-Webの統合**

ユーザーが最終的なメタデータを確認・修正するためのインターフェースとして、2026年現在広く普及している「LM Studio」のローカルサーバー機能や、オープンソースの音楽管理ツール「beets」のWebUIを活用する7。

特に「beets」はプラグインシステムが充実しており、MusicBrainz、AcoustID、さらにはDiscogsやSpotifyからのデータ取得を統合的に管理できる43。本手法で構築したLLMベースのクエリ生成エンジンをbeetsのプラグインとして実装することで、コマンドラインとWebブラウザの両方から、AIが推奨するメタデータの承認・修正が可能となる42。

## **結論と今後の展望：AIエージェントによる音楽ライブラリの自律的組織化**

本報告書で詳述した手法は、2026年時点のハイエンド・モバイルハードウェアであるRTX 4090 Laptopの性能を最大限に引き出し、ローカルLLMと構造化生成、そして外部データベースを高度に融合させたものである。このシステムの構築により、Steamで購入したサウンドトラックは、もはや「単なるファイルの集まり」ではなく、日本人ユーザーが求める高い検索性と美的秩序を備えた「完成された音楽ライブラリ」へと昇華される。

### **本手法の革新性と社会的意義**

本手法の最大の革新性は、LLMの推論能力を「文法の檻（Outlines）」に閉じ込めることで、ハルシネーションというAI最大の弱点を克服し、かつて人間が手動で行っていた高度な名寄せ作業と読み仮名付与を、完全無料で自動化した点にある。これは、個人の音楽体験の質を向上させるだけでなく、MusicBrainzのようなオープンなデータベースへの修正フィードバックを加速させ、音楽文化全体のデジタルアーカイブ化に寄与するものである46。

### **2026年以降の進化：マルチモーダル解析とエージェント・スウォーム**

2026年後半から2027年にかけて、LLMの進化はさらに加速し、テキストだけでなく音声や画像を直接理解するマルチモーダルモデル（Gemma 4のバリエーションやLLaMA 4など）がローカル環境でも主流になると予測される8。これにより、アルバムアートの色彩からジャンルを推定したり、楽曲の盛り上がり（BPMやエネルギー感）を解析してメタデータに反映したりといった、より感性的な整理が可能となる。

また、「Kimi K2.6」に見られるような「エージェント・スウォーム（Agent Swarm）」アーキテクチャの導入により、複数の特化型AIが「検索担当」「読み仮名担当」「タグ書き込み担当」として協調動作し、並列的に数万曲規模のライブラリを自律的に整備する未来が現実のものとなりつつある11。

RTX 4090 Laptop 16GBという環境は、そのような次世代のAI体験を先取りするための十分な「土壌」であり、本報告書で提示した手法はその出発点に過ぎない。技術の進歩を適切に音楽管理の実務に統合し続けることで、デジタルの海に埋もれた素晴らしいゲーム音楽たちが、常に最適な形でユーザーの元に届けられる環境が維持されるのである。

#### **引用文献**

1. Steamworks Development :: Steam Soundtrack Updates, 4月 30, 2026にアクセス、 [https://steamcommunity.com/groups/steamworks/announcements/detail/1691596648440131992](https://steamcommunity.com/groups/steamworks/announcements/detail/1691596648440131992)  
2. Game Soundtracks on Steam (Steamworks Documentation), 4月 30, 2026にアクセス、 [https://partner.steamgames.com/doc/store/application/soundtrackapp](https://partner.steamgames.com/doc/store/application/soundtrackapp)  
3. Guide: How to Play your Own Music Files with Steam's Built in Music Player \[2025\] \- Reddit, 4月 30, 2026にアクセス、 [https://www.reddit.com/r/Steam/comments/1jkowr3/guide\_how\_to\_play\_your\_own\_music\_files\_with/](https://www.reddit.com/r/Steam/comments/1jkowr3/guide_how_to_play_your_own_music_files_with/)  
4. How To Add Music to Steam Music 2026 (Step By Step) \- YouTube, 4月 30, 2026にアクセス、 [https://www.youtube.com/watch?v=ohGBY7jUW6I](https://www.youtube.com/watch?v=ohGBY7jUW6I)  
5. Use ID3 TSOT/TSOA/TSOP tags for name-based sorting if available · Issue \#200 \- GitHub, 4月 30, 2026にアクセス、 [https://github.com/AdrienPoupa/VinylMusicPlayer/issues/200](https://github.com/AdrienPoupa/VinylMusicPlayer/issues/200)  
6. Benchmarking LLMs on NVIDIA RTX 4090 GPU Server with Ollama \- Database Mart, 4月 30, 2026にアクセス、 [https://www.databasemart.com/blog/ollama-gpu-benchmark-rtx4090](https://www.databasemart.com/blog/ollama-gpu-benchmark-rtx4090)  
7. No Internet? No Problem. Create Your Own AI Assistant with Local LLM 20 Frameworks (2026) | by Karthikeyan Rathinam, 4月 30, 2026にアクセス、 [https://karthikeyanrathinam.medium.com/no-internet-no-problem-create-your-own-ai-assistant-with-local-llm-20-frameworks-2026-75aea74d024f](https://karthikeyanrathinam.medium.com/no-internet-no-problem-create-your-own-ai-assistant-with-local-llm-20-frameworks-2026-75aea74d024f)  
8. Top 7 open source LLMs for 2026 \- NetApp Instaclustr, 4月 30, 2026にアクセス、 [https://www.instaclustr.com/education/open-source-ai/top-7-open-source-llms-for-2026/](https://www.instaclustr.com/education/open-source-ai/top-7-open-source-llms-for-2026/)  
9. Release of New Japanese LLMs, 4月 30, 2026にアクセス、 [https://www.nii.ac.jp/en/news/release/2026/0403.html](https://www.nii.ac.jp/en/news/release/2026/0403.html)  
10. Ultimate Guide \- The Best Open Source LLM for Japanese in 2026 \- SiliconFlow, 4月 30, 2026にアクセス、 [https://www.siliconflow.com/articles/en/best-open-source-LLM-for-Japanese](https://www.siliconflow.com/articles/en/best-open-source-LLM-for-Japanese)  
11. Top 5 Local LLM Tools and Models in 2026 \- Pinggy, 4月 30, 2026にアクセス、 [https://pinggy.io/blog/top\_5\_local\_llm\_tools\_and\_models/](https://pinggy.io/blog/top_5_local_llm_tools_and_models/)  
12. The Best Open-Source LLMs in 2026 \- BentoML, 4月 30, 2026にアクセス、 [https://www.bentoml.com/blog/navigating-the-world-of-open-source-large-language-models](https://www.bentoml.com/blog/navigating-the-world-of-open-source-large-language-models)  
13. dottxt-ai/outlines: Structured Outputs · GitHub \- GitHub, 4月 30, 2026にアクセス、 [https://github.com/dottxt-ai/outlines](https://github.com/dottxt-ai/outlines)  
14. Welcome to Outlines\!, 4月 30, 2026にアクセス、 [https://dottxt-ai.github.io/outlines/latest/](https://dottxt-ai.github.io/outlines/latest/)  
15. Generate structured output from LLMs with Dottxt Outlines in AWS | Artificial Intelligence, 4月 30, 2026にアクセス、 [https://aws.amazon.com/blogs/machine-learning/generate-structured-output-from-llms-with-dottxt-outlines-in-aws/](https://aws.amazon.com/blogs/machine-learning/generate-structured-output-from-llms-with-dottxt-outlines-in-aws/)  
16. Welcome to Outlines\!, 4月 30, 2026にアクセス、 [https://dottxt-ai.github.io/outlines/welcome/](https://dottxt-ai.github.io/outlines/welcome/)  
17. LLM Structured Outputs: Schema Validation for Real Pipelines (2026) | Collin Wilkins, 4月 30, 2026にアクセス、 [https://collinwilkins.com/articles/structured-output](https://collinwilkins.com/articles/structured-output)  
18. MusicBrainz API, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_API](https://musicbrainz.org/doc/MusicBrainz_API)  
19. MusicBrainz API / Search, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_API/Search](https://musicbrainz.org/doc/MusicBrainz_API/Search)  
20. MusicBrainz Database / Schema, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_Database/Schema](https://musicbrainz.org/doc/MusicBrainz_Database/Schema)  
21. When searching for a url, url entities should have \["relation-list"\] as an array of IRelation instead of .relations · Issue \#1136 · Borewit/musicbrainz-api \- GitHub, 4月 30, 2026にアクセス、 [https://github.com/Borewit/musicbrainz-api/issues/1136](https://github.com/Borewit/musicbrainz-api/issues/1136)  
22. Search Server \- MusicBrainz, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/Search\_Server](https://musicbrainz.org/doc/Search_Server)  
23. MusicBrainz API / Examples, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_API/Examples](https://musicbrainz.org/doc/MusicBrainz_API/Examples)  
24. MusicBrainz API / Rate Limiting, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_API/Rate\_Limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)  
25. ratelimit · PyPI, 4月 30, 2026にアクセス、 [https://pypi.org/project/ratelimit/](https://pypi.org/project/ratelimit/)  
26. Implementing Effective API Rate Limiting in Python | by PI | Neural Engineer \- Medium, 4月 30, 2026にアクセス、 [https://medium.com/neural-engineer/implementing-effective-api-rate-limiting-in-python-6147fdd7d516](https://medium.com/neural-engineer/implementing-effective-api-rate-limiting-in-python-6147fdd7d516)  
27. API — musicbrainzngs 0.7 documentation, 4月 30, 2026にアクセス、 [https://python-musicbrainzngs.readthedocs.io/en/v0.7/api/](https://python-musicbrainzngs.readthedocs.io/en/v0.7/api/)  
28. Chromaprint \- AcoustID, 4月 30, 2026にアクセス、 [https://acoustid.org/chromaprint](https://acoustid.org/chromaprint)  
29. acoustid/chromaprint: C library for generating audio fingerprints used by AcoustID \- GitHub, 4月 30, 2026にアクセス、 [https://github.com/acoustid/chromaprint](https://github.com/acoustid/chromaprint)  
30. AcoustID: Open source audio identification services, 4月 30, 2026にアクセス、 [https://acoustid.biz/](https://acoustid.biz/)  
31. Welcome to AcoustID\! | AcoustID, 4月 30, 2026にアクセス、 [https://acoustid.org/](https://acoustid.org/)  
32. pyacoustid \- PyPI, 4月 30, 2026にアクセス、 [https://pypi.org/project/pyacoustid/](https://pypi.org/project/pyacoustid/)  
33. SudachiPy · PyPI, 4月 30, 2026にアクセス、 [https://pypi.org/project/SudachiPy/](https://pypi.org/project/SudachiPy/)  
34. How to Improve Retrieval Quality for Japanese Text with Sudachi, Milvus/Zilliz, and AWS Bedrock \- Medium, 4月 30, 2026にアクセス、 [https://medium.com/@zilliz\_learn/how-to-improve-retrieval-quality-for-japanese-text-with-sudachi-milvus-zilliz-and-aws-bedrock-d1141832414f](https://medium.com/@zilliz_learn/how-to-improve-retrieval-quality-for-japanese-text-with-sudachi-milvus-zilliz-and-aws-bedrock-d1141832414f)  
35. SudachiDict-core \- PyPI, 4月 30, 2026にアクセス、 [https://pypi.org/project/SudachiDict-core/](https://pypi.org/project/SudachiDict-core/)  
36. id3v2.4.0-changes \- ID3.org, 4月 30, 2026にアクセス、 [https://id3.org/id3v2.4.0-changes](https://id3.org/id3v2.4.0-changes)  
37. ID3 tag version 2.4.0 \- Main Structure — Mutagen Specs 1.0 documentation, 4月 30, 2026にアクセス、 [https://mutagen-specs.readthedocs.io/en/latest/id3/id3v2.4.0-structure.html](https://mutagen-specs.readthedocs.io/en/latest/id3/id3v2.4.0-structure.html)  
38. Indexed Search Syntax \- MusicBrainz, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/Indexed\_Search\_Syntax](https://musicbrainz.org/doc/Indexed_Search_Syntax)  
39. Levenshtein distance \- Wikipedia, 4月 30, 2026にアクセス、 [https://en.wikipedia.org/wiki/Levenshtein\_distance](https://en.wikipedia.org/wiki/Levenshtein_distance)  
40. Levenshtein Distance: A Comprehensive Guide \- DigitalOcean, 4月 30, 2026にアクセス、 [https://www.digitalocean.com/community/tutorials/levenshtein-distance-python](https://www.digitalocean.com/community/tutorials/levenshtein-distance-python)  
41. ID3 tag version 2.4.0 \- Native Frames — Mutagen Specs 1.0 documentation, 4月 30, 2026にアクセス、 [https://mutagen-specs.readthedocs.io/en/latest/id3/id3v2.4.0-frames.html](https://mutagen-specs.readthedocs.io/en/latest/id3/id3v2.4.0-frames.html)  
42. MusicBrainz vs Beets vs manual metadata vs... : r/Lidarr \- Reddit, 4月 30, 2026にアクセス、 [https://www.reddit.com/r/Lidarr/comments/1sov2wo/musicbrainz\_vs\_beets\_vs\_manual\_metadata\_vs/](https://www.reddit.com/r/Lidarr/comments/1sov2wo/musicbrainz_vs_beets_vs_manual_metadata_vs/)  
43. beetbox/beets: music library manager and MusicBrainz tagger \- GitHub, 4月 30, 2026にアクセス、 [https://github.com/beetbox/beets](https://github.com/beetbox/beets)  
44. MusicBrainz Plugin \- beets, 4月 30, 2026にアクセス、 [https://beets.readthedocs.io/en/stable/plugins/musicbrainz.html](https://beets.readthedocs.io/en/stable/plugins/musicbrainz.html)  
45. Beets MusicBrainz Genres Plugin Released \- MetaBrainz Community Discourse, 4月 30, 2026にアクセス、 [https://community.metabrainz.org/t/beets-musicbrainz-genres-plugin-released/734611](https://community.metabrainz.org/t/beets-musicbrainz-genres-plugin-released/734611)  
46. ListenBrainz / MBIDMappingDocumentation \- MusicBrainz, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/ListenBrainz/MBIDMappingDocumentation](https://musicbrainz.org/doc/ListenBrainz/MBIDMappingDocumentation)  
47. MusicBrainz Enabled Applications, 4月 30, 2026にアクセス、 [https://musicbrainz.org/doc/MusicBrainz\_Enabled\_Applications](https://musicbrainz.org/doc/MusicBrainz_Enabled_Applications)  
48. Downloading Artist's External links from Musicbrainz \- MetaBrainz Community Discourse, 4月 30, 2026にアクセス、 [https://community.metabrainz.org/t/downloading-artists-external-links-from-musicbrainz/525818](https://community.metabrainz.org/t/downloading-artists-external-links-from-musicbrainz/525818)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAYCAYAAAD3Va0xAAABB0lEQVR4Xu2SMYrCUBCGRwUFsXAVQbb0AlYL1oKNlRcQLDyC9RZrYyeIhZ0HkC20UtzazjsIHkT/P5OQ94ZnWlnIBx8kM8m8mUlEct5GGTYdi346uv8wsSBV0QJn+IBbWHPySaE/eIVt0XdeshctcoM9PxWxgWMbtJREH2In7OripyN+YcMGLXX4FV+zELUsRA/MZCTpQ1PRQoM0LS3Yde6DsABPS+iIjraClTjGbtl1JjxpZ2JcNruaif4eSz8dhmO5HZFk6Sf4CQ9+Ogy/RrJoFxZhsW/4Y3JBOBaXaeFYLHQX7ToTLnNigzH8CHPRg14umr99H67hEQ7jmIVL51gFm8j5rzwB+MckAWoCKAIAAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACcAAAAZCAYAAACy0zfoAAAB6ElEQVR4Xu2WyytFURTGl7xKhCSScg0URXmkGCqSgVIMDNAdSAYGXimZMZGJgcIEkYkYKEUGSpkbSCYmZ+6P4Pvae7vrnHuvS/fRVeerX2evtffZZ+299uOIhAoV6n9pFHyAzxSwzaN5JXd6AjPKLgTb4AE0KH8PeFN2TnQKKpVdC27BLihR/hpwpeysKyL+2aGmxaSxN+CnfRTwZVX8INOoxZQyuGDQnWA14Mu5uK4YXF6KgXlBZz6IG4DB3Qcr8kFcgwwuGvBnWp74N9w+GFF2QnGnehK/UzOtDlCg7FdJ8c1k55sWz8M6Zbt2paBL+aki6+Mz6HOBVYN6cCDxp4NPjNyT5CltAzvgBjSBMnBo68bEv8MZwAUYB8eg3/o3xWSHVya1KKbPc7Au/tmUYom/Qx281iLfLUUmxYz8BJSDYfCs6qP2yaBdG2oDVIk5T3nLDIF2W0dFJcWs/VbsZNaWl8GlqpuzT2Zg3pYrwJnEZoQBbkkscC6Ln5bRn8SUcG1Sd9amOBNTtkxfiy272R0EA2BCTEa6xSwFDuTdtuUNlJbYoUvBi5gZYqqXQKP194FWW74WM4gVMUtkT8z1uACaxfTHvx/O5Jp5JT2xI+4yiulIlBK2cX86rNcL3aXUiYPTOzpUWvoCcCVOdplBVXQAAAAASUVORK5CYII=>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEgAAAAZCAYAAACSP2gVAAADHklEQVR4Xu2Y24uOURTGl/P5nBwu+CTFhXNcSSkUUg7hij4lh0Q5XUhSDuVwoRAKiRsXpFAORSnlD5DcSE25cOGP4Pm19jbr2zNjJjNNfb73qaf59lr7Xe/aa6+19n7HrEKFChUqVGh2bBR/ir+6IXPe+yOthQ/irjAeJF4U34nTg3yp+CWMWwYPxHFhPFl8KV4Vhwb5JPFJGLcEataYJWCneUktK+SM7xWy/x4smpKKoLwIUBm4ReLxQtaSoM8QoApdgOC0lcIKDpoyAXpTKvoII8QZ4oBS0SygJxGgeiGPeCE+LoU9wB7xjvl9ak2haxpwgrVZxxMsYr44tRT2AA/FU+IccWChawp0df+J4L7EfSiDhc5Nf6eJK9PvCGzxzDdxtTiyUW2DxXnilDSm/AgicrjQGm1ib4m1393Q5Tk8iw+1pIuYKK4wtxmBLeTdgqxps67Li0VcFl+LM5Nsm/nlkfLZJ64XD1tjj1kgnhQ/iWfN7WTg7DNxu3hLXG7u7CHxinhevGluH9DDHpl/Ht0VZ5n7sDfNOWHuw3Nr9IENwnc26IY42tzWUXNbPIOtDhhiHb+5MvkEqf2ZabbbfEH3zV/AQteaN/SDaQ67y4KGp3EGWcP9Kt65CMbX9Bu7181Ll/dgP8/fKo4XN4vf03zecynNwweyHx8ICjqqIPtAWedDB3tkGPOwRS9kPgHCVq/B5THvZsZna+9Z6PcHXQYLqBcyHKdh0/QviKOCriZuCmNA4H+IT82fHRZ0vD/6EE9hNppgRxA8bL01t7WqUf1vwKFr5hGvJ1nMGHbnnPlOkLYRLJa+EkG53Q5jekjedVKfrIngBDwTxmQdFVBmDD6Q5fiw2HwTYo9hHj5GWwBbvcJs8aN5Mz6SZGRGzhjq/JU4wXxXIjpbMOnNDmYcENeZlyPBKD+ByFxOwozT5s0ZH2LG4EPd3AcCQY/bEPSUJg0eW2OSbKy5rV6DXY6nQD45MnIPiCgXUILAxpMNG9nxzsD8+A58iPN5Pv53AuAzG1eesASw9LffgKM7zJvi3wLUsiBAW8Rj1kcnRH/jN5VmeAD+k5dBAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAD4AAAAZCAYAAABpaJ3KAAACtklEQVR4Xu2Xy6uNURiHX/d7TiQy0DZQjFxORKgzcJsojBiQYqAkJcclpJigUJIUEhNyGxgoA6VkYMBIJia7DAz8Efwe73p9a69zkWOfwd7ne+pXa73r+9Ze672sb22zmpqampruY7v0Q/r5F/HMW3+lO3gn7cv6E6RL0htpYWbvlb5k/Y7ngTQ768+TXknXpcmZfa70LOt3NA1rjSrsNU/t1YWd/r3C1rGwGVI7hzRn46VDVkjHC1tXQR2z8TEHm26Wxm6Hw4yNvy4HOozp0vjSOBzUPBvfX9jbwUPzc2K04av0z4HjRG/awBO9HXBfaJTGUYC1fy2NwzHU9zsYJy2RJqb+BmlZNfwH3l1l1d1gjrRYOmd+FwjWWev9IeZdKU0p7PzOIvM1wAxpfmqvt9Z5Wf/t1Gb+fGxQ8FTThk5zNnpEOiMdkDaZf9fzRU6THplfg++ab/ikdDPpdHquTzosPU59nL4ntSm1ranNRl+msRvSCfP6PWWezsfMszS/WHHjxI5jL0jXpKnZ+G8m2cA7eahMzd3STOmKVdHhB4go7JS+pTZRv2z+PItnAbPSGNHbIt2XLibbIfPNA5lBEJZKH62KcvR3mWcen93l5hFfm56BT9JZ8/cIBJny3zSkHanNplh8XIBuSd+lF+ZZEZnQIz1N7RwWuNncSXl59Zs7Aafm/w0iIwPmZO4c5vgsvTfPtraRR/igebqtMU/NO9L5NAZkBRmFoz4kG5EOeJ60jUgGlBDgyKhVeCJdTe2GVQHIwTkbUzsy4qj5OkYMi2SxEWEWRQpTd1xvcQSfrICU5YdxFvYF5s8G2Ej/beZ/eYHDKA48avd5auNENs4c0Gc+dwnvxFU7/l2GI0cMNRN1GpDuJZyi5VeBfnmhYD42GTVMJsXZkTOYvZw/IDgB75SlUDMm+QVmMG+bGlPhiQAAAABJRU5ErkJggg==>