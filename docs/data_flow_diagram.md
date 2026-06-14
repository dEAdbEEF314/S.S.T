# Data Flow Diagram (データフロー図)

S.S.T (Steam Soundtrack Tagger) の主要なデータフローとアーキテクチャを示す図です。
このシステムは「Separation of Powers（権力分立）」の思想に基づき、情報の収集、LLMによる推論、そしてシステムによる物理的な検証を独立したフェーズとして実行します。

```mermaid
flowchart TD
    %% Define Subgraphs for logical grouping
    subgraph Input ["📥 Input Phase (Scanner)"]
        SteamLib[("Steam Library (READ-ONLY)\n/steamapps/music/")]
        DB[(Local State DB\nsst_local_state.db)]
        Scanner["scanner.py\n(Identify unprocessed albums)"]
    end

    subgraph DataGathering ["🔎 Data Gathering (Identity & Metadata)"]
        SteamPICS["Steam PICS API / VDF\n(Store Tracklists)"]
        MusicBrainz["MusicBrainz API"]
        AcoustID["AcoustID API\n(Audio Fingerprinting)"]
        LocalAudio["Local MP3/FLAC/WAV\n(FFprobe duration/tags)"]
        
        IdentMBZ["mbz.py"]
        IdentAcoustID["acoustid.py"]
        IdentEmbedded["embedded.py"]
    end

    subgraph Processing ["🧠 Processing & Reasoning (LLM)"]
        Builder["builder.py\n(Create Virtual Albums)"]
        VirtualAlbums{{"Virtual Albums\n(STEAM, FINGERPRINT, MBZ_SEARCH, LOCAL)"}}
        LLM["llm.py\n(Gemini / Ollama)"]
        LLMResult{{"Audit JSON\n(Confidence, Action Map)"}}
        DuplicateResolver["processor.py\n(Smart Duplicate Resolution)"]
    end

    subgraph Execution ["⚙️ Execution & Validation"]
        Tagger["tagger.py\n(FFmpeg encode/tag)"]
        TempDir[/"Temp Buffer Dir"/]
        Validator["validator.py\n(Physical Validation)"]
    end

    subgraph Output ["📤 Output Phase (Packaging)"]
        Packager["packager.py"]
        Archive[("✅ Archive\n/output/archive/")]
        Review[("⚠️ Review\n/output/review/")]
        Discord(("Discord Webhook\n(Notifications)"))
    end

    %% Define connections
    SteamLib --> Scanner
    DB --> Scanner
    Scanner -->|AppID Queue| DataGathering

    SteamPICS --> IdentMBZ
    MusicBrainz --> IdentMBZ
    AcoustID --> IdentAcoustID
    LocalAudio --> IdentEmbedded
    LocalAudio --> IdentAcoustID

    IdentMBZ --> Builder
    IdentAcoustID --> Builder
    IdentEmbedded --> Builder

    Builder --> VirtualAlbums
    VirtualAlbums -->|Prompt Injection| LLM
    
    LLM -->|Phase 1: Confidence < 90| Review
    LLM -->|Phase 2: Timeout/Error| Review
    LLM -->|Phase 2: Success| LLMResult
    
    LLMResult --> DuplicateResolver
    DuplicateResolver -->|Final Metadata| Tagger

    LocalAudio -->|Raw Audio| Tagger
    Tagger -->|Tagged MP3s (CBR 320kbps)| TempDir
    TempDir --> Validator

    Validator -->|Pass (No Issues)| Packager
    Validator -->|Fail (Duplicates/Issues)| Packager
    Validator -.->|Downgrade Warning| Discord

    Packager -->|Status: archive| Archive
    Packager -->|Status: review| Review
    Packager -->|Update Status| DB
```

## 各コンポーネントの役割概要
1. **Input Phase**: `scanner.py` がSteamライブラリをスキャンし、DBと照合して未処理のアルバム（AppID）を特定します。
2. **Data Gathering**: 外部API（MusicBrainz, AcoustID, Steam PICS）およびローカルファイルからメタデータを収集します。
3. **Processing**: 収集したデータを最大4つの「Virtual Albums（仮想アルバム）」として規格化します。FINGERPRINTとMBZ_SEARCHの統合や足切りを行った後、LLMに投入してトラックのマッピングと同一性スコア（Confidence）を推論させます。ここで `processor.py` による重複解消ロジックも介入します。
4. **Execution & Validation**: LLMの指示に基づき `tagger.py` がFFmpegを使って一時フォルダにMP3をエンコード・タグ付けします。その後、`validator.py` が物理的にファイル群を検査し、重複やエラーがないか（フェイルセーフ）確認します。
5. **Output Phase**: 検証に合格したものは `Archive` へ、LLMの自信がなかったりValidatorに弾かれたものは `Review` へ安全に隔離されます。
