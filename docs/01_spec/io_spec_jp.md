# I/O仕様

## Scoutの出力と ingest ストレージ

### ディレクトリ構造 (S3: ingest/)
```
ingest/{AppID}/
├ appmanifest_{AppID}.acf   <-- 新規: オリジナルのマニフェストのコピー
├ [音声ファイル].flac
└ [音声ファイル].mp3
```

---

## Workerの出力と最終ストレージ

### ディレクトリ構造 (S3: archive/ または review/)
```
{archive|review}/{AppID}/
├ metadata.json            <-- 新規: UIおよび手動確認用の正解データ
├ appmanifest_{AppID}.acf   <-- 新規: 保存されたマニフェスト
└ {Disc}/
    └ {filename}.{ext}
```

### メタデータ JSON スキーマ (metadata.json)
このファイルには、処理プロセスの全記録が含まれます。
```json
{
  "app_id": 123456,
  "album_name": "Example Album",
  "status": "success | review",
  "scanned_at": "2026-01-01T00:00:00Z",
  "processed_at": "2026-01-01T00:05:00Z",
  "steam_info": {
    "developer": "...",
    "publisher": "...",
    "url": "..."
  },
  "external_info": {
    "source": "musicbrainz",
    "mbid": "...",
    "vgmdb_url": "..."
  },
  "tracks": [
    {
      "file_path": "1/01. Title.aiff",
      "original_filename": "01_original.flac",
      "title": "Title",
      "artist": "Artist",
      "confidence": 0.95
    }
  ]
}
```

---

## 重複防止ルール
Scoutは `ingest/` へのアップロード前に、`{archive|review}/{AppID}/metadata.json` の存在を確認しなければなりません。
存在する場合、`--force` フラグが指定されていない限り、そのアルバムの処理をスキップします。
