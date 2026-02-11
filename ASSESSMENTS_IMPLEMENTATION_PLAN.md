# Assessments Implementation Plan

## Overview

This document outlines the implementation plan for **Assessments** – a new type of graded test where:
- Students submit physical (hard copy) test papers to the teacher
- AI generates feedback to guide the teacher’s marking
- Teacher marks the hard copy using AI feedback, then uploads the marked copy
- Both students and teachers have hard and soft copies
- Students receive grades in the system

---

## Workflow Summary

```
Teacher creates Assessment (question paper + answer key)
        ↓
Students hand in physical papers to teacher (outside system)
        ↓
Teacher: Manual submission (integrated in assessment)
  1. Select student → Upload UNMARKED paper (PDF/photos)
  2. AI generates feedback
  3. Teacher reviews AI feedback, marks the physical hard copy
  4. Teacher uploads MARKED copy into system
        ↓
Student & Teacher: Both have hard copy + soft copy (marked PDF) in system
```

---

## 1. Data Model Changes

### 1.1 Assignment Model

Add fields to distinguish Assessments from regular Assignments:

| Field | Type | Description |
|-------|------|-------------|
| `assignment_type` | `'assignment'` \| `'assessment'` | Default: `'assignment'` |
| `submission_mode` | `'any'` \| `'manual_only'` | For assessments: `'manual_only'` (no student online submit) |

**Location:** Assignment documents in MongoDB (no schema migration; add on create)

### 1.2 Submission Model

Add support for marked copy storage:

| Field | Type | Description |
|-------|------|-------------|
| `marked_copy_file_ids` | `list[str]` | GridFS IDs of teacher-uploaded marked copy (PDF or images) |
| `marked_copy_page_count` | `int` | Number of pages in marked copy |
| `marked_copy_uploaded_at` | `datetime` | When teacher uploaded the marked copy |

**Location:** Submission documents in MongoDB

---

## 2. Create Assessment Flow

### 2.1 Option A: Extend Create Assignment (Recommended)

**File:** `templates/teacher_create_assignment.html`

Add a new assignment type at the top of the form:

```
Assignment Type *
○ Assignment (default) – Students can submit online or teacher records manual submission
○ Assessment – Manual submission only. Students hand in papers; you upload unmarked → AI feedback → upload marked copy
```

When "Assessment" is selected:
- Automatically set `submission_mode: 'manual_only'`
- Hide "When to send feedback to student" (always teacher reviews first)
- Show info banner: "Assessment workflow: 1) Upload student's unmarked paper 2) AI generates feedback 3) Mark hard copy 4) Upload marked copy"
- Optionally hide student AI help limits (assessments = exam-style, no help during submission)

**Backend:** `app.py` – `create_assignment()` route

- Read `assignment_type` from form
- If `assessment`: set `assignment_type: 'assessment'`, `submission_mode: 'manual_only'`
- Ensure `submitted_via: 'manual'` submissions are the only allowed path for assessments

### 2.2 Option B: Separate "Create Assessment" Page

Create `teacher_create_assessment.html` and route `create_assessment`. Reuse most of `teacher_create_assignment.html` structure but:
- Simpler form (question paper + answer key only; no spreadsheet, no rubric)
- Clear labels: "Assessment" instead of "Assignment"
- Default `assignment_type: 'assessment'`, `submission_mode: 'manual_only'`

---

## 3. Manual Submission Integration

### 3.1 Current Flow

- Route: `/teacher/assignment/<assignment_id>/manual-submission`
- Teacher selects student, uploads PDF/photos → AI feedback → redirect to review

### 3.2 Assessment-Specific Flow

**File:** `templates/teacher_manual_submission.html`

- When `assignment.assignment_type == 'assessment'`:
  - Add explanatory text: "For assessments: upload the student's unmarked paper. After AI feedback, you will mark the hard copy and upload the marked copy in the review step."
  - No change to the upload step itself; it stays the same (unmarked paper)

**File:** `app.py` – `manual_submission()`

- No change to logic; create submission with `file_ids` (unmarked) as today
- Redirect to `review_submission` as today

### 3.3 Assessment List Access

**File:** `templates/teacher_assignments.html`

- Add filter/tabs: "Assignments" | "Assessments"
- Or badge on cards: "Assessment" when `assignment_type == 'assessment'`
- Ensure "Manual submission" button is prominent for assessments

**File:** `app.py` – `teacher_assignments()`

- Filter by `assignment_type` when "Assessments" tab is selected

---

## 4. Teacher Review Page – Marked Copy Upload

### 4.1 New Section on Review Page

**File:** `templates/teacher_review.html`

Add a card/section (e.g. after the submission viewer):

**"Upload Marked Copy"** (for assessments only, when `assignment.assignment_type == 'assessment'`)

- Text: "After marking the hard copy, upload the scanned/photographed marked paper so students can access it."
- File input: PDF or images (multiple)
- Submit button: "Upload marked copy"
- Show status: "Marked copy uploaded" with download link if already uploaded

### 4.2 Backend for Marked Copy Upload

**New route:** `POST /teacher/review/<submission_id>/upload-marked-copy`

- Accept `multipart/form-data` with `files`
- Validate: assignment is assessment, teacher owns it
- Store files in GridFS (same pattern as manual submission)
- Update submission: `marked_copy_file_ids`, `marked_copy_page_count`, `marked_copy_uploaded_at`
- Optional: If teacher enters marks in the feedback table, save those as `final_marks` when uploading marked copy

**New route:** `GET /teacher/review/<submission_id>/view-marked-copy/<file_index>`

- Serve marked copy file from GridFS (similar to `view_submission_file`)
- Or reuse `view_submission_file` with a `?variant=marked_copy` param and `file_ids` = `marked_copy_file_ids`

### 4.3 PDF Generation

**File:** `utils/pdf_generator.py`

- When generating feedback PDF for assessments with `marked_copy_file_ids`:
  - Option A: Include marked copy as additional pages/section
  - Option B: Generate two PDFs: feedback report + marked copy
  - Recommendation: One PDF with 1) feedback table, 2) marked copy pages

---

## 5. Student View – Grades and Marked Copy

### 5.1 Submission View

**File:** `templates/submission_view.html`

- When submission has `marked_copy_file_ids`:
  - Add section: "Your marked paper"
  - View/download marked copy PDF
- Show grade (`final_marks` / `total_marks`) clearly

### 5.2 Assignments List / Dashboard

**File:** `templates/assignments_list.html`, `templates/dashboard.html`

- Assessments appear in the same list (or with an "Assessment" badge)
- Status: "Feedback received" when `status == 'reviewed'` and optional "Marked copy available"

---

## 6. Dashboard Updates

### 6.1 Teacher Dashboard

**File:** `templates/teacher_dashboard.html`

- Add action card: "Create Assessment" linking to create assessment (or create assignment with type=assessment)
- Or: Change "Create Assignment" to a dropdown: "Create Assignment" | "Create Assessment"

### 6.2 Student Dashboard

**File:** `templates/dashboard.html`

- No structural change; assessments appear as assignments with grades
- Optional: Separate "Assessments" section if desired

---

## 7. Implementation Order

| Step | Task | Files |
|------|------|-------|
| 1 | Add `assignment_type` and `submission_mode` to create assignment form and backend | `teacher_create_assignment.html`, `app.py` (create_assignment) |
| 2 | Add `marked_copy_file_ids` support to Submission; create upload endpoint | `app.py` (new route, `view_submission_file` extension) |
| 3 | Add "Upload marked copy" section to teacher review page | `teacher_review.html` |
| 4 | Block online student submission for assessments | `app.py` (submit_assignment, assignments_list) |
| 5 | Update teacher assignments list with Assessment filter/badge | `teacher_assignments.html`, `app.py` |
| 6 | Update student submission view to show marked copy and grade | `submission_view.html` |
| 7 | Update teacher dashboard with Create Assessment action | `teacher_dashboard.html` |
| 8 | Update PDF generator to include marked copy when present | `utils/pdf_generator.py` |

---

## 8. Edge Cases

- **Resubmit marked copy:** Allow teacher to replace marked copy (overwrite `marked_copy_file_ids` in GridFS)
- **Assessment + rubric:** If assessments can be rubric-based, ensure rubric flow supports marked copy upload
- **Spreadsheet assessments:** Likely not applicable; keep assessments as PDF-based (standard or rubric)

---

## 9. UI Copy Suggestions

**Create Assessment (when selected):**
> Assessments are for tests where students hand in physical papers. You will: 1) Upload each student's unmarked paper 2) AI generates feedback to guide your marking 3) Mark the hard copy 4) Upload the marked copy so both you and the student have a soft copy.

**Manual submission (assessment):**
> Upload the student's unmarked test paper. After AI feedback is generated, you will mark the physical copy and then upload the marked copy in the review step.

**Review page – Upload marked copy:**
> Upload the scanned or photographed marked paper. Students will be able to view and download it.

---

## 10. Summary

- **Assessments** are assignments with `assignment_type: 'assessment'` and `submission_mode: 'manual_only'`.
- **Manual submission** stays as today: teacher uploads unmarked paper → AI feedback → review.
- **New:** On the review page, for assessments, teacher can upload the **marked copy**.
- **Storage:** `file_ids` = unmarked; `marked_copy_file_ids` = marked.
- **Student:** Sees grade and can download marked copy.
- **Teacher:** Same, plus can replace marked copy if needed.
