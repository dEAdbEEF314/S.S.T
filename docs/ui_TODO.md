# UI Implementation TODO List

## 1. Reported UI Deficiencies (To Be Verified)
- [x] **UI Refresh Issue**: Added manual Refresh button to bypass cache/polling delays.
- [x] **Visibility of Controls**: Enhanced Checkbox visibility and improved Action icons (SearchCode) prominence in AlbumRow.
- [x] **Constant Visibility**: Album Titles and App IDs are now brighter and clearly visible without hover.

## 2. Functionality Issues
- [ ] **Missing Audio in ZIP**: Added detailed logging to Worker and improved tag writing for AIFF. Needs verification in production test environment.
  - *Status*: Code improved, awaiting Act-7 production test results.

## 3. Advanced Features to Finalize
- [ ] **Bulk Delete**: Logic confirmed, UI controls improved.
- [x] **Metadata Inspector**: Redesigned as a 2-column layout with summary and formatted JSON view.
- [ ] **Reprocess (Retry)**: UI triggers are active.
- [ ] **Manual Approval**: UI triggers are active.

## 4. Technical Debt / Fixes
- [x] **File Format Enforcement**: Worker logic updated to handle AIFF/MP3 priority and tagging correctly.
- [x] **Filename Sanitization**: Implemented in both Worker uploads and UI ZIP downloads.
