# WSL Path Conversion Specification

## 1. 概要 (Overview)
S.S.T (Steam Soundtrack Tagger) は、Linux環境（主にWindows Subsystem for Linux 2 / WSL2）上で動作することを前提に構築されています。しかし、対象となる「Steamライブラリ」および「Steamの設定ファイル (VDF)」の多くは、ホストであるWindowsOS側のファイルシステム（NTFS等）に依存し、Windows形式のパス文字列 (`C:\Program Files (x86)\Steam` など) がハードコードされています。

そのため、WSL環境からWindows側のファイルにシームレスにアクセスするための自動パス変換ロジック（WSL Path Conversion）が実装されています。

## 2. 実装モジュール
パス変換ロジックは `src/sst/utils.py` の `windows_to_wsl_path` および `ensure_wsl_path` 関数として提供されています。

## 3. 変換ルール (Conversion Rules)

`windows_to_wsl_path(win_path: str) -> Path` は以下のステップでパスを正規化します。

1. **既存WSLパスのバイパス**:
   入力されたパスが既に `/` で始まっている場合、WSLのネイティブパスまたは既に変換済みと判断し、そのまま `Path` オブジェクトとして返却します。
2. **ドライブレターのパースと置換 (Drive Letter Mapping)**:
   入力パスがWindowsのドライブレター（例: `C:\`, `D:\`, `F:\`）から始まる場合、正規表現 (`^([a-zA-Z]):\\?(.*)`) を用いてドライブレターと残りのパスに分離します。
   * ドライブレターを小文字に変換します（例: `C` -> `c`）。
   * `\mnt\` マウントポイントに結合します。
   * 残りのパスのバックスラッシュ (`\`) をすべてフォワードスラッシュ (`/`) に置換します。
   * **例**: `F:\SteamLibrary\steamapps\music` -> `/mnt/f/SteamLibrary/steamapps/music`
3. **ドライブレターを持たない相対パス等の処理**:
   ドライブレターにマッチしない場合は、単にバックスラッシュをフォワードスラッシュに置換して返却します。

## 4. 主な利用箇所 (Use Cases)

### `steam_vdf.py` における `libraryfolders.vdf` の解析
Steamは複数ドライブへのゲームインストールをサポートしており、その一覧は `libraryfolders.vdf` に保存されています。
S.S.Tは起動時にこのVDFをパースし、キー `"path"` の値（Windows形式）を抽出します。抽出直後に `ensure_wsl_path()` を通すことで、WSL環境の `scanner.py` がエラーなく直接 `/mnt/.../steamapps/music` ディレクトリを走査できるようになります。

これにより、ユーザーは「Windows側でSteamを運用しつつ、WSL側でS.S.Tを稼働させる」という一般的な開発・利用スタイルにおいて、一切のパスの手動調整やシンボリックリンクの手動作成を行う必要がなくなります。
