# Rubric Extraction & Confirmation — Design

**Date**: 2026-03-30
**Status**: Approved

## Problem

When teachers upload rubric PDFs, the AI marking system misinterprets the criteria structure. For example, a rubric with 2 criteria (Content /10, Language /20) gets marked with 3 criteria because the AI splits "Organisation of ideas" (a sub-point of Language) into a separate criterion. There's no teacher confirmation step.

## Solution

When a teacher uploads a rubric PDF during assignment creation/editing, use Claude Haiku (vision) to extract structured criteria. Show the result inline as an editable table. Teacher can edit directly, add/remove criteria, or re-extract with additional instructions. The confirmed structured criteria drive the marking prompt — no more AI interpretation.

## Flow

1. Teacher uploads rubric PDF on create/edit form
2. JS sends PDF to `/api/teacher/extract-rubric`
3. Haiku extracts structured criteria via vision
4. Editable table appears inline below file input (name, max marks, descriptors per row)
5. Teacher can:
   - Edit fields directly
   - Add/remove criteria rows
   - Re-extract with additional prompt instructions
6. On form submit, `rubric_criteria` JSON saved on assignment
7. `analyze_essay_with_rubrics` uses structured criteria in system prompt

## API

### `POST /api/teacher/extract-rubric`

**Input:** rubric PDF (multipart) + optional `instructions` (string for re-extract context)

**Output:**
```json
{
  "success": true,
  "criteria": [
    {
      "name": "Content",
      "max_marks": 10,
      "descriptors": "Band 5 (9-10): All aspects fully addressed...\nBand 4 (7-8): ..."
    },
    {
      "name": "Language",
      "max_marks": 20,
      "descriptors": "Band 5 (17-20): Coherent and cohesive...\nBand 4 (13-16): ..."
    }
  ]
}
```

Uses Haiku with vision. Rate limited.

## Data Model

New field on `assignments`:
```python
'rubric_criteria': [
    {'name': str, 'max_marks': int, 'descriptors': str}
]
```

Existing fields unchanged (`rubrics_id`, `rubrics_text`, `rubrics_name` remain for backward compatibility and vision reference during marking).

## Marking Prompt Change

When `rubric_criteria` exists, replace loose rubric text in system prompt with:
```
GRADING CRITERIA (teacher-confirmed — use EXACTLY these criteria and marks):
1. Content (10 marks):
   Band 5 (9-10): All aspects fully addressed...
   Band 4 (7-8): ...
2. Language (20 marks):
   Band 5 (17-20): Coherent and cohesive...
   Band 4 (13-16): ...

IMPORTANT: Do NOT add, rename, split, or merge criteria. Mark ONLY against these criteria with the exact mark allocations shown.
```

Falls back to current behavior (rubrics_text + PDF vision) if `rubric_criteria` is not set.

## UI

Inline on create/edit form below the rubric file input:
- Table with columns: Criterion, Max Marks, Band Descriptors
- Each row editable (text inputs / textareas)
- "Add criterion" and remove (X) buttons per row
- "Re-extract with AI" button with text input for additional instructions
- Loading spinner during extraction

## Files Changed

- `app.py` — new `/api/teacher/extract-rubric` route, update create/edit to save `rubric_criteria`
- `utils/ai_marking.py` — update `analyze_essay_with_rubrics` to use structured criteria
- `templates/teacher_create_assignment.html` — inline criteria table UI
- `templates/teacher_edit_assignment.html` — same UI for editing

## Out of Scope

- Rubric template library (reusable across assignments)
- Auto-calculating total marks from criteria sum
