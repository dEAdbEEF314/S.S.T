# UI Implementation TODO List

## 1. Reported UI Deficiencies (To Be Verified)
- [ ] **UI Refresh Issue**: The browser does not reflect the latest "List View" changes despite rebuilding. (Possibly cache or mounting delay).
- [ ] **Visibility of Controls**: Ensure the "Bulk Delete" checkboxes and "Metadata Inspect" (SearchCode icon) are clearly visible and accessible in the list row.
- [ ] **Constant Visibility**: Ensure Album Titles and other key metadata are always visible without hover (Requirement from List View migration).

## 2. Functionality Issues
- [ ] **Missing Audio in ZIP**: Although ZIP streaming logic is updated, the actual audio files (.aiff/.mp3) are missing from S3 `archive/` prefix.
  - *Cause*: Worker service is likely failing to upload audio files or using an incorrect path.
  - *Action*: Debug Worker's `upload_result` and `FFmpeg` conversion steps.

## 3. Advanced Features to Finalize
- [ ] **Bulk Delete**: Test end-to-end deletion of multiple prefixes in S3.
- [ ] **Metadata Inspector**: Verify the overlay/modal displays formatted JSON correctly.
- [ ] **Reprocess (Retry)**: Verify that moving an album to `ingest/` and re-triggering Prefect works.
- [ ] **Manual Approval**: Verify that moving from `review/` to `archive/` works.

## 4. Technical Debt / Fixes
- [ ] **File Format Enforcement**: Strictly follow the priority: AIFF (from Lossless) > Original MP3 > Converted MP3 (320kbps).
- [ ] **Filename Sanitization**: Ensure downloaded ZIP filenames are safe for all OSs.
- [ ] **Storage Sync**: Re-run processing for the initial 5 albums once Worker upload is fixed.
