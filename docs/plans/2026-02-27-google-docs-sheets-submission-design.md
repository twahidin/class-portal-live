# Google Docs/Sheets Submission — Design

## Summary

Allow students to open assignment files (PDF question papers, Excel templates) directly in Google Docs/Sheets, work on them in Google's editor, and submit back through the portal for grading. The exported files feed into the existing AI marking and spreadsheet evaluation pipelines unchanged.

## Flow

### Teacher creates assignment (unchanged)
- Uploads PDF question paper and/or Excel template as usual
- Must have Google Drive source folder configured in teacher settings

### Student views assignment
- If teacher has Drive configured, new buttons appear:
  - **"Open in Google Docs"** for PDF-based assignments (standard, rubric)
  - **"Open in Google Sheets"** for spreadsheet assignments
- First click: API uploads the template from GridFS to teacher's Drive submissions folder, converts to Google Doc/Sheet, sets "anyone with link can edit", returns URL
- Subsequent visits: button changes to **"Continue in Google Docs/Sheets"** (reuses same copy)
- One copy per student per assignment

### Student submits
- New **"Submit from Google Docs/Sheets"** button alongside existing file upload
- Backend exports Google Doc → PDF / Google Sheet → .xlsx via Drive API
- Stores exported file in GridFS (identical to normal upload)
- Runs existing grading pipeline: AI marking for PDFs, spreadsheet evaluator for .xlsx

### Teacher reviews (unchanged)
- Same review screen, same feedback flow
- Submission looks identical to a file upload

## Decisions

| Decision | Choice |
|---|---|
| File storage | Teacher's Drive submissions folder |
| Access model | Anyone with link can edit (no Google login required) |
| Grading | Export back to original format, reuse existing pipelines |
| Drive requirement | Only when teacher has Drive configured |
| One copy per student | Yes — revisiting reopens the same doc |

## Codebase Changes

### `utils/google_drive.py` — New DriveManager methods

- `upload_and_convert_to_google_doc(content_bytes, filename, folder_id)` — Upload PDF, convert to Google Doc, return file ID + web link
- `upload_and_convert_to_google_sheet(content_bytes, filename, folder_id)` — Upload .xlsx, convert to Google Sheet, return file ID + web link
- `set_anyone_with_link_editor(file_id)` — Set permission so anyone with the link can edit
- `export_google_doc_as_pdf(file_id)` — Export Google Doc back to PDF bytes
- `export_google_sheet_as_xlsx(file_id)` — Export Google Sheet back to .xlsx bytes

### `app.py` — 2 new API routes

**`POST /api/student/open-in-drive`**
- Input: `{ assignment_id }`
- Auth: `@login_required`
- Logic:
  1. Look up assignment + teacher
  2. Check teacher has Drive configured (submissions folder exists)
  3. Check if student already has a Drive copy for this assignment (lookup submission doc with `google_drive_file_id`)
  4. If not: fetch template from GridFS, upload+convert to Drive, set permissions, create/update submission doc with `google_drive_file_id` and `google_drive_url`
  5. Return `{ success: true, url: "https://docs.google.com/..." }`

**`POST /api/student/submit-from-drive`**
- Input: `{ assignment_id }`
- Auth: `@login_required`
- Logic:
  1. Look up submission doc with `google_drive_file_id`
  2. Export: Google Doc → PDF bytes, or Google Sheet → .xlsx bytes
  3. Store in GridFS as `file_ids`
  4. Set `file_type` to `pdf` or `excel`
  5. Continue into existing marking flow (call `analyze_submission_images()` or `evaluate_spreadsheet_submission()`)
  6. Return standard submission response

### `templates/assignment_view.html` — UI additions

- New button group below existing download section:
  - "Open in Google Docs" / "Open in Google Sheets" (or "Continue in..." if already opened)
  - "Submit from Google Docs/Sheets" (enabled only after opening)
- Loading spinner while Drive copy is being created
- Link opens in new tab

### Submission document — New fields

```python
{
  # ... existing fields ...
  'google_drive_file_id': str,   # Drive file ID of the student's copy
  'google_drive_url': str,       # Web link to the Google Doc/Sheet
  'google_drive_type': str,      # 'document' or 'spreadsheet'
  'submitted_via': 'google_drive',  # Reuses existing field with new value
}
```

## Edge Cases

- **Teacher doesn't have Drive configured**: Buttons don't appear. Normal upload flow only.
- **Drive API error during copy**: Show error toast, student falls back to normal upload.
- **Student submits empty doc**: AI marking handles this (flags as incomplete).
- **Student opens doc but never submits**: Draft copy stays in Drive. No submission created until they click submit.
- **Multiple submissions**: On resubmit, export again from the same Google Doc/Sheet. Previous submission files remain in GridFS.
- **Drive quota exceeded**: Service account quota error caught and shown as user-friendly message.
