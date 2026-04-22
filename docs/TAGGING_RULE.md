# SST Audio Selection and Metadata Tagging Rules

## 1. Core Philosophy
(Previous sections omitted for brevity, focusing on new rules)

---

## 3. Metadata Collection & MusicBrainz Logic

### 3.1 MusicBrainz Search & Tie-breaking
When searching for an album in MusicBrainz, the system uses the `name` field from the Steam `.acf` file to search for a **Release**.

If multiple candidates have the same top score, they are evaluated in the following order:
1.  **Format = Digital Media**: Prioritize official digital releases.
2.  **No "Bandcamp"**: Exclude Bandcamp releases to avoid non-standard metadata (High significance).
3.  **Track Count Proximity**: Match based on the actual number of files found locally.
4.  **Date Proximity**: Match against the Steam release date.

### 3.2 Confidence Levels
- **Confirmed**: Matches that satisfy both criteria (1) and (2). These are treated as high-precision truth.
- **Weak**: Matches selected based on (3) or (4). The LLM is notified that this data is for reference only and should be cross-referenced more strictly.

---

## 5. Workflow Execution & State Management

### 5.1 Local Database (SQLite)
SST maintains a local SQLite database to track the history of all processing attempts.
- **Key**: Steam `app_id`.
- **Stored Data**:
    - **Archived Albums**: Full consolidated metadata, processing date, and file paths. This serves as a reusable "Gold Standard" metadata library.
    - **Review/Skip Albums**: Record of the attempt to prevent redundant scans.
- **Skip Logic**: By default, any `app_id` already present in the database (regardless of status) is skipped in future scans unless the `--force` flag is used.
