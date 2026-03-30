# Rubric Extraction & Confirmation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When teachers upload a rubric PDF, extract structured criteria with Haiku, show an editable inline preview, and use the confirmed criteria for precise AI marking.

**Architecture:** New API endpoint extracts rubric criteria from PDF using Haiku vision. Frontend shows editable table inline below the rubric upload zone. Confirmed criteria stored as `rubric_criteria` on the assignment and used by `analyze_essay_with_rubrics` to build exact marking instructions.

**Tech Stack:** Flask, Claude Haiku (vision), MongoDB, Jinja2/Bootstrap, vanilla JS.

---

### Task 1: API — Rubric extraction endpoint

**Files:**
- Modify: `app.py` (add new route near other teacher API routes)
- Modify: `utils/ai_marking.py` (add extraction function)

**Step 1: Add `extract_rubric_criteria` function to `utils/ai_marking.py`**

Add at the end of the file (before the bulk submission functions). This function takes rubric PDF bytes and optional teacher instructions, sends to Haiku with vision, returns structured criteria.

```python
def extract_rubric_criteria(rubric_bytes: bytes, teacher: dict = None, instructions: str = None) -> dict:
    """
    Extract structured rubric criteria from a PDF using Claude Haiku vision.

    Args:
        rubric_bytes: Raw bytes of the rubric PDF
        teacher: Optional teacher dict for API key resolution
        instructions: Optional additional instructions for re-extraction

    Returns:
        dict with 'criteria': [{'name': str, 'max_marks': int, 'descriptors': str}]
    """
    import anthropic

    # Resolve API key (same pattern as ocr_extract_answers)
    api_key = None
    if teacher:
        encrypted_key = teacher.get('anthropic_api_key')
        if encrypted_key:
            try:
                api_key = decrypt_api_key(encrypted_key)
            except Exception:
                pass
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        return {'error': 'No API key available', 'criteria': []}

    client = anthropic.Anthropic(api_key=api_key)

    content = []

    # Send rubric as vision document
    content.append(build_content_block_for_file(rubric_bytes))

    prompt = """Analyze this rubric/marking scheme document and extract the grading criteria.

For EACH criterion, extract:
- The criterion name (e.g., "Content", "Language")
- The maximum marks for that criterion
- The band descriptors (all bands with their mark ranges and descriptions)

IMPORTANT:
- Only extract criteria that are SEPARATE mark components (have their own mark allocation)
- Do NOT split sub-points into separate criteria (e.g., if "Organisation of ideas" is listed as a sub-point under "Language", it is NOT a separate criterion)
- The sum of all max_marks should equal the total marks for the assessment"""

    if instructions:
        prompt += f"\n\nADDITIONAL TEACHER INSTRUCTIONS:\n{instructions}"

    prompt += """

Return ONLY valid JSON:
{
    "criteria": [
        {
            "name": "Criterion Name",
            "max_marks": 10,
            "descriptors": "Band 5 (9-10): Description...\\nBand 4 (7-8): Description...\\n..."
        }
    ],
    "total_marks": 30
}"""

    content.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=4096,
            messages=[{"role": "user", "content": content}]
        )

        response_text = response.content[0].text.strip()
        # Handle markdown code blocks
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()

        import json
        result = json.loads(response_text)
        return result
    except Exception as e:
        logger.error(f"Error extracting rubric criteria: {e}")
        return {'error': str(e), 'criteria': []}
```

**Step 2: Add the API route to `app.py`**

Add near the other teacher API routes. This accepts a rubric PDF (multipart) and optional instructions text, returns the extracted criteria JSON.

```python
@app.route('/api/teacher/extract-rubric', methods=['POST'])
@teacher_required
@limiter.limit("20 per hour")
def extract_rubric():
    """Extract structured criteria from a rubric PDF using Haiku."""
    from utils.ai_marking import extract_rubric_criteria

    teacher = Teacher.find_one({'teacher_id': session['teacher_id']})

    file = request.files.get('rubric_file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({'success': False, 'error': 'Empty file'}), 400

    instructions = request.form.get('instructions', '').strip() or None

    result = extract_rubric_criteria(file_bytes, teacher, instructions)

    if result.get('error'):
        return jsonify({'success': False, 'error': result['error']}), 500

    return jsonify({
        'success': True,
        'criteria': result.get('criteria', []),
        'total_marks': result.get('total_marks')
    })
```

**Step 3: Commit**

```bash
git add utils/ai_marking.py app.py
git commit -m "feat: add rubric extraction API using Haiku vision"
```

---

### Task 2: Frontend — Inline rubric criteria editor on create form

**Files:**
- Modify: `templates/teacher_create_assignment.html` (add criteria table + JS)

**Step 1: Add the criteria editor HTML**

After the rubrics upload zone (after line 373, the `rubrics-help` small text), add the inline criteria editor:

```html
<!-- Rubric Criteria Editor (populated after extraction) -->
<div id="rubric-criteria-editor" class="mt-3" style="display: none;">
    <div class="card border-warning">
        <div class="card-header bg-warning bg-opacity-10 d-flex justify-content-between align-items-center">
            <h6 class="mb-0"><i class="bi bi-list-check me-2"></i>Extracted Rubric Criteria</h6>
            <span class="badge bg-info" id="criteria-total-marks"></span>
        </div>
        <div class="card-body">
            <p class="text-muted small mb-3">Review and edit the extracted criteria. The AI will mark essays using exactly these criteria.</p>
            <div id="criteria-table-container">
                <table class="table table-sm" id="criteria-table">
                    <thead>
                        <tr>
                            <th style="width: 20%">Criterion</th>
                            <th style="width: 10%">Max Marks</th>
                            <th>Band Descriptors</th>
                            <th style="width: 5%"></th>
                        </tr>
                    </thead>
                    <tbody id="criteria-tbody"></tbody>
                </table>
            </div>
            <div class="d-flex gap-2 mt-2">
                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="addCriterionRow()">
                    <i class="bi bi-plus-circle me-1"></i>Add criterion
                </button>
                <button type="button" class="btn btn-outline-primary btn-sm" onclick="showReExtractPanel()">
                    <i class="bi bi-arrow-clockwise me-1"></i>Re-extract with AI
                </button>
            </div>
            <!-- Re-extract panel -->
            <div id="re-extract-panel" class="mt-3" style="display: none;">
                <div class="input-group">
                    <input type="text" class="form-control" id="re-extract-instructions"
                           placeholder="e.g., 'Organisation is part of Language, not a separate criterion'">
                    <button type="button" class="btn btn-primary" onclick="reExtractRubric()">
                        <i class="bi bi-arrow-clockwise me-1"></i>Re-extract
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>
<!-- Hidden input to store confirmed criteria JSON -->
<input type="hidden" id="rubric_criteria" name="rubric_criteria" value="">
```

**Step 2: Add the JavaScript**

Add the JS for extraction, rendering, editing, and re-extraction. Place in the existing `<script>` block of the template:

```javascript
// === RUBRIC CRITERIA EXTRACTION ===
let extractedCriteria = [];

// Trigger extraction when rubric file is selected
function onRubricFileSelected() {
    const fileInput = document.getElementById('rubrics');
    const markingType = document.querySelector('input[name="marking_type"]:checked')?.value;
    if (!fileInput.files.length || markingType !== 'rubric') return;

    extractRubricFromFile(fileInput.files[0]);
}

async function extractRubricFromFile(file, instructions) {
    const editor = document.getElementById('rubric-criteria-editor');
    const tbody = document.getElementById('criteria-tbody');

    // Show loading state
    editor.style.display = 'block';
    tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary me-2"></div>Extracting rubric criteria with AI...</td></tr>';

    const formData = new FormData();
    formData.append('rubric_file', file);
    if (instructions) formData.append('instructions', instructions);

    try {
        const resp = await fetch('/api/teacher/extract-rubric', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();

        if (data.success && data.criteria && data.criteria.length > 0) {
            extractedCriteria = data.criteria;
            renderCriteriaTable();
            if (data.total_marks) {
                const totalMarksInput = document.getElementById('total_marks');
                if (totalMarksInput && !totalMarksInput.value) {
                    totalMarksInput.value = data.total_marks;
                }
            }
        } else {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger py-3"><i class="bi bi-exclamation-triangle me-1"></i>Could not extract criteria: ' + (data.error || 'Unknown error') + '</td></tr>';
        }
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger py-3"><i class="bi bi-exclamation-triangle me-1"></i>Error: ' + e.message + '</td></tr>';
    }
}

function renderCriteriaTable() {
    const tbody = document.getElementById('criteria-tbody');
    tbody.innerHTML = '';
    let totalMax = 0;

    extractedCriteria.forEach((c, idx) => {
        totalMax += c.max_marks || 0;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><input type="text" class="form-control form-control-sm" value="${escapeHtml(c.name)}" onchange="updateCriterion(${idx}, 'name', this.value)"></td>
            <td><input type="number" class="form-control form-control-sm" value="${c.max_marks}" min="1" onchange="updateCriterion(${idx}, 'max_marks', parseInt(this.value))"></td>
            <td><textarea class="form-control form-control-sm" rows="3" onchange="updateCriterion(${idx}, 'descriptors', this.value)">${escapeHtml(c.descriptors || '')}</textarea></td>
            <td><button type="button" class="btn btn-outline-danger btn-sm" onclick="removeCriterion(${idx})"><i class="bi bi-x"></i></button></td>
        `;
        tbody.appendChild(row);
    });

    document.getElementById('criteria-total-marks').textContent = `Total: ${totalMax} marks`;
    // Store as hidden JSON
    document.getElementById('rubric_criteria').value = JSON.stringify(extractedCriteria);
}

function updateCriterion(idx, field, value) {
    extractedCriteria[idx][field] = value;
    renderCriteriaTable();
}

function removeCriterion(idx) {
    extractedCriteria.splice(idx, 1);
    renderCriteriaTable();
}

function addCriterionRow() {
    extractedCriteria.push({ name: '', max_marks: 0, descriptors: '' });
    renderCriteriaTable();
}

function showReExtractPanel() {
    document.getElementById('re-extract-panel').style.display = 'block';
    document.getElementById('re-extract-instructions').focus();
}

function reExtractRubric() {
    const instructions = document.getElementById('re-extract-instructions').value;
    const fileInput = document.getElementById('rubrics');
    if (!fileInput.files.length) {
        alert('Please upload a rubric PDF first.');
        return;
    }
    extractRubricFromFile(fileInput.files[0], instructions);
    document.getElementById('re-extract-panel').style.display = 'none';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

**Step 3: Hook into the existing `handleFileSelect` function**

Find the existing `handleFileSelect` function in the template and add a call to trigger extraction when rubrics are uploaded. After the file select handling:

```javascript
// In the existing handleFileSelect function or as a change listener
document.getElementById('rubrics').addEventListener('change', function() {
    onRubricFileSelected();
});
```

**Step 4: Commit**

```bash
git add templates/teacher_create_assignment.html
git commit -m "feat: add inline rubric criteria editor to assignment creation form"
```

---

### Task 3: Backend — Save rubric_criteria on assignment create/edit

**Files:**
- Modify: `app.py` (update create_assignment and edit_assignment routes)

**Step 1: Update assignment creation to save rubric_criteria**

In the `create_assignment()` route, after the assignment document is built (around line 9090), add parsing of the hidden `rubric_criteria` field:

```python
# Parse rubric criteria if provided (teacher-confirmed structured criteria)
rubric_criteria_json = request.form.get('rubric_criteria') or data.get('rubric_criteria')
rubric_criteria = None
if rubric_criteria_json:
    try:
        import json
        rubric_criteria = json.loads(rubric_criteria_json)
        if not isinstance(rubric_criteria, list):
            rubric_criteria = None
    except (json.JSONDecodeError, TypeError):
        rubric_criteria = None
```

Then add `'rubric_criteria': rubric_criteria` to the assignment document dict.

**Step 2: Update assignment editing to save rubric_criteria**

In the `edit_assignment()` route, add the same parsing and include in `update_data`:

```python
rubric_criteria_json = request.form.get('rubric_criteria')
if rubric_criteria_json:
    try:
        import json
        rubric_criteria = json.loads(rubric_criteria_json)
        if isinstance(rubric_criteria, list):
            update_data['rubric_criteria'] = rubric_criteria
    except (json.JSONDecodeError, TypeError):
        pass
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: save teacher-confirmed rubric_criteria on assignment create/edit"
```

---

### Task 4: AI Marking — Use structured criteria in system prompt

**Files:**
- Modify: `utils/ai_marking.py` (update `analyze_essay_with_rubrics` function around lines 1730-1829)

**Step 1: Update the system prompt construction**

Replace lines 1733-1748 (the rubric text section) and the JSON example (lines 1788-1810) to use structured criteria when available:

```python
# Get rubrics — prefer structured criteria, fall back to text
rubric_criteria = assignment.get('rubric_criteria')
rubrics_text = assignment.get('rubrics_text', '')

if rubric_criteria and isinstance(rubric_criteria, list) and len(rubric_criteria) > 0:
    # Teacher-confirmed structured criteria — build precise instructions
    criteria_text = "GRADING CRITERIA (teacher-confirmed — use EXACTLY these criteria and marks):\n"
    criteria_json_example = []
    for i, c in enumerate(rubric_criteria):
        criteria_text += f"\n{i+1}. {c['name']} ({c['max_marks']} marks):\n"
        if c.get('descriptors'):
            for line in c['descriptors'].split('\n'):
                if line.strip():
                    criteria_text += f"   {line.strip()}\n"
        criteria_json_example.append({
            "name": c['name'],
            "max_marks": c['max_marks'],
            "marks_awarded": "number",
            "reasoning": "...",
            "afi": "..."
        })
    criteria_text += "\nIMPORTANT: Do NOT add, rename, split, or merge criteria. Mark ONLY against these criteria with the exact mark allocations shown."
    rubric_prompt_section = criteria_text
else:
    # Fall back to rubrics text or defaults
    rubric_prompt_section = f"""{"GRADING RUBRICS:" if rubrics_text else "Use standard essay rubrics:"}
{rubrics_text if rubrics_text else '''
Default criteria:
- Content (10 marks): Relevance, ideas, engagement with topic
- Language (10 marks): Grammar, vocabulary, sentence structure
- Organisation (10 marks): Paragraphing, coherence, flow
'''}"""
    criteria_json_example = None
```

Then in the system prompt, replace the hardcoded rubric section with `{rubric_prompt_section}`.

And update the JSON example section — if `criteria_json_example` is set, use it instead of the hardcoded 3-criteria example. Otherwise keep the default example.

```python
# Build JSON example criteria section
if criteria_json_example:
    import json
    criteria_example_str = json.dumps(criteria_json_example, indent=8)
else:
    criteria_example_str = """[
        {
            "name": "Content",
            "max_marks": 10,
            "marks_awarded": 7,
            "reasoning": "Clear explanation...",
            "afi": "Specific suggestions..."
        }
    ]"""
```

Use `{criteria_example_str}` in the JSON format example within the system prompt.

**Step 2: Commit**

```bash
git add utils/ai_marking.py
git commit -m "feat: use teacher-confirmed rubric criteria in essay marking prompt"
```

---

### Task 5: Frontend — Edit template rubric criteria editor

**Files:**
- Modify: `templates/teacher_edit_assignment.html` (add same criteria editor)

**Step 1: Add criteria editor HTML after the rubrics upload zone (after line 420)**

Same HTML as Task 2 but also pre-populate from existing `assignment.rubric_criteria` if it exists:

```html
<!-- Same rubric criteria editor HTML as create form -->
<!-- Plus initialization script: -->
<script>
{% if assignment.rubric_criteria %}
extractedCriteria = {{ assignment.rubric_criteria | tojson }};
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('rubric-criteria-editor').style.display = 'block';
    renderCriteriaTable();
});
{% endif %}
</script>
```

**Step 2: Add the same JavaScript functions as Task 2**

Copy the JS functions (extractRubricFromFile, renderCriteriaTable, etc.) to the edit template, or if there's a shared script block, reference it.

**Step 3: Commit**

```bash
git add templates/teacher_edit_assignment.html
git commit -m "feat: add rubric criteria editor to assignment edit form"
```

---

### Task 6: Manual testing

**Test 1: New rubric assignment**
1. Create a new assignment with marking type "Rubric"
2. Upload the Express Continuous Writing Band Descriptors PDF
3. Verify criteria table appears with exactly 2 criteria: Content /10, Language /20
4. Edit a criterion name, verify it updates
5. Remove a criterion, add it back
6. Submit the assignment
7. Verify `rubric_criteria` is saved in MongoDB

**Test 2: Re-extract**
1. Upload a rubric PDF that extracts incorrectly (e.g., 3 criteria instead of 2)
2. Click "Re-extract with AI"
3. Type "Organisation is part of Language, not a separate criterion"
4. Verify it re-extracts with 2 criteria

**Test 3: Marking uses correct criteria**
1. Submit a student essay to the rubric assignment
2. Verify AI feedback has exactly the teacher-confirmed criteria
3. Verify marks add up to the correct total

**Test 4: Edit existing assignment**
1. Edit an existing rubric assignment
2. Verify existing criteria are pre-populated in the table
3. Make changes, save, verify updated in DB

**Test 5: Backward compatibility**
1. Mark a submission for an old rubric assignment (no `rubric_criteria`)
2. Verify it still works with the rubrics_text fallback

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Extraction API + Haiku function | `app.py`, `utils/ai_marking.py` |
| 2 | Inline criteria editor on create form | `templates/teacher_create_assignment.html` |
| 3 | Save rubric_criteria on create/edit | `app.py` |
| 4 | Use structured criteria in marking prompt | `utils/ai_marking.py` |
| 5 | Criteria editor on edit form | `templates/teacher_edit_assignment.html` |
| 6 | Manual testing | — |
