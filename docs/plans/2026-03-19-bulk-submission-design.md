# Bulk Class Submission — Design

**Date**: 2026-03-19
**Status**: Approved

## Problem

Teachers currently upload manual submissions one student at a time. For a class of 30+ students, this is tedious. Teachers want to scan the entire class's work into a single PDF and have the system split and process it automatically.

## Solution

A bulk upload flow where the teacher uploads one PDF containing the entire class's scanned work. AI detects student names on pages, groups pages per student, and the teacher reviews/corrects before confirming. Optionally, students validate their extracted answers before AI marking runs.

## Requirements (Agreed)

- Single PDF upload of entire class stack
- AI flexibly detects student names (no cover page assumed)
- Summary table review with confidence levels; teacher corrects mistakes
- Best-guess with flags for low-confidence matches
- Teacher can optionally require student validation per upload
- If validation enabled: students get web push notification, see OCR-extracted answers, can edit before confirming; AI marking runs after confirmation
- If validation disabled: AI marking runs immediately (like current manual flow)
- Background processing for the AI split analysis

## Data Model

### New collection: `bulk_submissions`

```python
{
    'bulk_id': 'BULK-XXXXXXXX',
    'assignment_id': str,
    'teacher_id': str,
    'require_validation': bool,
    'status': 'processing' | 'ready_for_review' | 'confirmed' | 'failed',
    'created_at': datetime,

    # Uploaded PDF in GridFS
    'source_file_id': str,
    'total_pages': int,

    # AI split results (populated after processing)
    'splits': [
        {
            'student_id': str | None,
            'student_name_detected': str,
            'pages': [1, 2, 3],
            'confidence': 'high' | 'low',
            'name_found_on_page': 1
        }
    ],
    'unmatched_pages': [int],
    'processing_error': str,

    # After teacher confirms
    'confirmed_at': datetime,
    'submission_ids': [str]
}
```

### Existing `submissions` collection — new optional fields

- `bulk_id` — links back to the bulk job
- `pending_validation` — `true` when waiting for student to validate

## Routes

| Method | Route | Auth | Purpose |
|--------|-------|------|---------|
| GET | `/teacher/assignment/<id>/bulk-submission` | teacher | Upload form |
| POST | `/teacher/assignment/<id>/bulk-submission` | teacher | Process upload, start background job |
| GET | `/teacher/assignment/<id>/bulk-review/<bulk_id>` | teacher | Review split results |
| POST | `/teacher/assignment/<id>/bulk-review/<bulk_id>/confirm` | teacher | Confirm splits, create submissions |
| GET | `/student/submission/<id>/validate` | student | Validation page |
| POST | `/api/student/submission/<id>/validate` | student | Submit validated answers |

## AI Page Analysis

- Each page sent to Claude Haiku with vision
- Prompt includes class student list for fuzzy matching
- Pages processed in order; name detection starts a new student section
- Batch 2-3 pages per API call to reduce calls
- Fuzzy matching (Levenshtein) for misspellings, reordered names, partial names

### Edge cases

| Scenario | Handling |
|----------|----------|
| No name on page | Assigned to current student section |
| No name on any page | Unmatched, teacher fixes |
| Same name twice | Second starts new section, teacher reviews |
| Name not in class list | Low confidence, best fuzzy match suggested |
| Student missing from PDF | Shown as "Missing" in review table |
| Blank page | Attached to current section, flagged |

## Student Validation Flow

When `require_validation` is enabled:

1. Submissions created with `pending_validation: true`
2. Web push notification sent to each student
3. Student opens validation page: left panel (page images), right panel (OCR-extracted answers, editable)
4. Student confirms → `pending_validation` cleared, AI marking triggers
5. Teacher can force-submit stragglers (skips validation, uses OCR answers as-is)
6. Student can "Report issue" if pages aren't theirs

### State flow

```
confirmed (teacher) → pending_validation → validated (student) → ai_reviewed
```

## Templates

- `teacher_bulk_submission.html` — upload form
- `teacher_bulk_review.html` — split review table with confidence badges
- `student_validate_submission.html` — validation page (reuses OCR review pattern)

## Out of Scope

- Multi-PDF upload
- Email notifications
- Auto-retry failed AI analysis
- Page reordering within a student's section
