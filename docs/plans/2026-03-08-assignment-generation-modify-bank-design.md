# Assignment Generation, Modify & Assessment Bank — Design

**Date**: 2026-03-08
**Status**: Approved

## Overview

Replace the current "Create Assignment" / "Create Assessment" buttons with a single dropdown offering four actions: Create, Generate, Modify, and Assessment Bank. This adds AI-powered assignment generation from the LO bank, AI-assisted modification of existing papers, and a reusable assignment bank.

## Navigation — Dropdown Menu

The teacher assignments page (`/teacher/assignments`) shows a single dropdown button:

| Item | Enabled When | Disabled Tooltip |
|------|-------------|-----------------|
| **Create** | Always | — |
| **Generate** | Teacher has >= 1 module tree | "Create a module tree first" |
| **Modify** | Always | — |
| **Assessment Bank** | Bank has >= 1 assignment | "No assignments in bank yet. Save assignments from the summary page or enable auto-save in Settings." |

## Feature 1: Generate (from LO Bank)

Build an assignment by selecting LOs and specifying a question mix. AI selects from the bank or generates questions on-the-fly.

### Step 1 — Configure Spec

- Select module tree from dropdown
- Select LOs via checkboxes on leaf nodes
- Set question mix table:
  - Rows: question types (MCQ, Short Answer, Open-Ended)
  - Columns: difficulty (Easy, Medium, Hard)
  - Cells: count of questions desired
- Total marks auto-calculated or manually set

### Step 2 — AI Selects / Generates Questions

- If LO bank has matching questions → auto-select best matches
- If LO bank is empty or insufficient → AI generates questions from LO titles/descriptions
- Mixed mode: bank questions first, AI fills gaps

### Step 3 — Review & Swap

- Editable list of selected questions
- Each shows: question text, answer, type, difficulty, LO tag
- Swap button per question → shows alternatives from bank for that LO
- Add/remove questions manually

### Step 4 — AI Review

- AI checks overall balance: difficulty curve, LO coverage, mark allocation
- Suggests adjustments (e.g. "no hard questions for LO 2.3", "uneven mark distribution")
- Teacher accepts/rejects each suggestion

### Step 5 — Output

Two options:
- **Download PDF** — LaTeX-friendly formatted paper + answer key
- **Assign to Students** — creates a full assignment (question paper PDF + answer key auto-generated), routes to class/group selection, supports AI marking on submission

## Feature 2: Modify (AI-Assisted)

Upload an existing PDF assignment and ask AI to adjust it.

### Step 1 — Upload

- Upload a PDF (or select from Assessment Bank — no upload needed)
- AI extracts questions from the PDF

### Step 2 — Choose Adjustment Type

- **Adjust difficulty** — keep same question types, make harder/easier
- **Adjust values only** — change numbers/data/scenarios in questions
- **Both** — adjust difficulty and values

### Step 3 — Editable Preview

- AI generates modified version
- Shows question-by-question editable web form
- Teacher tweaks individual questions as needed

### Step 4 — Output

Same as Generate:
- Download PDF
- OR assign to students (creates full assignment)
- Modified assignment auto-saved to Assessment Bank

## Feature 3: Assessment Bank

A curated library of reusable assignments.

### Population Methods

**Method 1 — Manual sync:**
- "Save to Assessment Bank" button on each assignment's summary page

**Method 2 — Auto-save toggle (Settings):**
- Toggle: "Automatically save new assignments to Assessment Bank"
- On enable: confirmation prompt — "Also add your X existing assignments to the bank?"
  - Yes → backfills all existing assignments
  - No → only new assignments going forward

### Bank UI

- List view: title, subject, date created, question count, difficulty summary
- Actions per assignment:
  - **Reassign** — opens assignment creation pre-filled, teacher picks target class/group
  - **Modify** — feeds into Modify flow (content already available, no PDF upload needed)
  - **Download PDF**
  - **Delete from bank**

### Data Model

Assessment bank entries are stored as a flag on existing assignment documents:

- `assignment.in_assessment_bank`: Boolean (default false)
- `assignment.bank_added_at`: DateTime

This avoids duplicating data — bank entries are just assignments with the flag set.

## Technical Notes

### New Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/teacher/assignments/generate` | GET/POST | Generate assignment from LO bank |
| `/teacher/assignments/generate/select-questions` | POST | AI selects/generates questions |
| `/teacher/assignments/generate/review` | POST | AI reviews balance |
| `/teacher/assignments/modify` | GET/POST | Modify flow |
| `/teacher/assignments/modify/process` | POST | AI processes modifications |
| `/teacher/assignments/bank` | GET | Assessment Bank listing |
| `/teacher/assignments/bank/sync` | POST | Add assignment to bank |
| `/teacher/assignments/bank/<id>/remove` | POST | Remove from bank |
| `/teacher/settings` (update) | POST | Auto-save toggle + backfill |

### PDF Generation

For Generate/Modify output PDFs:
- Use ReportLab (already in codebase) for PDF generation
- LaTeX-friendly: use math-compatible fonts, proper equation rendering
- Generate both question paper and answer key as separate PDFs
- Store as GridFS files when creating full assignments

### AI Provider

Uses teacher's configured AI provider (same as existing `get_teacher_ai_service()` pattern).

## Implementation Priority

1. **Dropdown navigation** — replace buttons, add greyed-out states
2. **Assessment Bank** — simplest feature, just a flag + listing page
3. **Generate** — core feature, depends on LO bank
4. **Modify** — PDF upload + AI modification
