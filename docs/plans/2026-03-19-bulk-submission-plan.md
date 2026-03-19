# Bulk Class Submission — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow teachers to upload a single PDF of an entire class's scanned work, auto-split it by student using AI, and optionally require student validation before AI marking.

**Architecture:** New bulk upload flow with background processing. Teacher uploads PDF → background thread uses Claude Haiku vision to detect student names per page → teacher reviews split summary → confirms → individual submissions created. Optional student validation via web push notifications before AI marking runs.

**Tech Stack:** Flask, MongoDB (GridFS + new `bulk_submissions` collection), Claude Haiku (vision API via Anthropic SDK), threading, web push notifications.

---

### Task 1: Database — Add bulk_submissions collection and indexes

**Files:**
- Modify: `models.py:26-97` (add indexes in `_create_indexes`)
- Modify: `utils/auth.py:37-39` (add `generate_bulk_id`)
- Modify: `utils/__init__.py` (export `generate_bulk_id`)

**Step 1: Add `generate_bulk_id` to auth.py**

In `utils/auth.py`, after line 39 (`generate_submission_id`), add:

```python
def generate_bulk_id() -> str:
    """Generate a unique bulk submission ID"""
    return f"BULK-{secrets.token_hex(8).upper()}"
```

**Step 2: Export from `utils/__init__.py`**

Add `generate_bulk_id` to the imports and `__all__` list.

**Step 3: Add indexes in `models.py`**

In `_create_indexes()`, after the submissions indexes (around line 42), add:

```python
# Bulk submissions
self.db.bulk_submissions.create_index('bulk_id', unique=True)
self.db.bulk_submissions.create_index([('assignment_id', 1), ('teacher_id', 1)])
```

**Step 4: Add BulkSubmission model class**

In `models.py`, add a `BulkSubmission` class following the same pattern as `Submission` (thin wrapper with `find_one`, `find`, `insert_one`, `update_one`):

```python
class BulkSubmission:
    @staticmethod
    def find_one(query, **kwargs):
        return db.db.bulk_submissions.find_one(query, **kwargs)

    @staticmethod
    def find(query, projection=None):
        return db.db.bulk_submissions.find(query, projection)

    @staticmethod
    def insert_one(document):
        return db.db.bulk_submissions.insert_one(document)

    @staticmethod
    def update_one(query, update):
        return db.db.bulk_submissions.update_one(query, update)
```

**Step 5: Commit**

```bash
git add models.py utils/auth.py utils/__init__.py
git commit -m "feat: add BulkSubmission model, generate_bulk_id, and indexes"
```

---

### Task 2: AI — Add page-level student name detection function

**Files:**
- Modify: `utils/ai_marking.py` (add `detect_student_names_in_pages` function)

**Step 1: Add the name detection function**

At the end of `utils/ai_marking.py`, add a new function. This function:
- Takes a list of page images/data and a list of student names
- Sends batches of 2-3 pages to Claude Haiku with vision
- Asks for student name detection per page
- Returns a list of `{page_num, name_found, confidence}` results

```python
def detect_student_names_in_pages(pages: list, student_names: list, teacher: dict = None) -> list:
    """
    Detect student names on scanned pages using Claude Haiku vision.

    Args:
        pages: list of {'type': 'image'|'pdf', 'data': bytes, 'page_num': int}
        student_names: list of student name strings to match against
        teacher: optional teacher dict for API key resolution

    Returns:
        list of {'page_num': int, 'name_detected': str|None, 'matched_student': str|None, 'confidence': 'high'|'low'}
    """
    import anthropic
    from difflib import get_close_matches

    # Resolve API key (same pattern as ocr_extract_answers)
    api_key = None
    if teacher:
        encrypted_key = teacher.get('anthropic_api_key')
        if encrypted_key:
            try:
                from utils.auth import decrypt_api_key
                api_key = decrypt_api_key(encrypted_key)
            except Exception:
                pass
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        return [{'page_num': p['page_num'], 'name_detected': None, 'matched_student': None, 'confidence': 'low'} for p in pages]

    client = anthropic.Anthropic(api_key=api_key)
    names_list = '\n'.join(f'- {name}' for name in student_names)
    results = []

    # Process pages in batches of 3
    batch_size = 3
    for i in range(0, len(pages), batch_size):
        batch = pages[i:i + batch_size]
        content = []

        for page in batch:
            if page['type'] == 'pdf':
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(page['data']).decode('utf-8')
                    }
                })
            else:
                resized = resize_image_for_ai(page['data'])
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(resized).decode('utf-8')
                    }
                })

        page_nums = [p['page_num'] for p in batch]
        content.append({
            "type": "text",
            "text": f"""Look at these {len(batch)} scanned page(s) of student work (page numbers: {page_nums}).

For EACH page, find any student name written or printed on it. The name may be handwritten, in a header, margin, or anywhere on the page.

Match found names against this class list:
{names_list}

Return JSON array with one object per page:
[{{"page_num": N, "name_detected": "RAW NAME AS WRITTEN" or null, "confidence": "high" or "low"}}]

Rules:
- "high" confidence = name clearly readable and closely matches a student on the list
- "low" confidence = name partially visible, unclear, or doesn't closely match anyone
- null name_detected = no name found on that page
- Return ONLY the JSON array, no other text."""
        })

        try:
            response = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=1024,
                messages=[{"role": "user", "content": content}]
            )

            response_text = response.content[0].text.strip()
            # Parse JSON from response (handle markdown code blocks)
            if response_text.startswith('```'):
                response_text = response_text.split('\n', 1)[1].rsplit('```', 1)[0].strip()

            import json
            batch_results = json.loads(response_text)

            for item in batch_results:
                name = item.get('name_detected')
                matched = None
                confidence = item.get('confidence', 'low')

                if name:
                    # Fuzzy match against student list
                    matches = get_close_matches(name.upper(), [n.upper() for n in student_names], n=1, cutoff=0.5)
                    if matches:
                        # Find original case version
                        idx = [n.upper() for n in student_names].index(matches[0])
                        matched = student_names[idx]
                        if matches[0] == name.upper():
                            confidence = 'high'
                    else:
                        confidence = 'low'

                results.append({
                    'page_num': item['page_num'],
                    'name_detected': name,
                    'matched_student': matched,
                    'confidence': confidence
                })
        except Exception as e:
            logger.error(f"Error detecting names in pages {page_nums}: {e}")
            for p in batch:
                results.append({
                    'page_num': p['page_num'],
                    'name_detected': None,
                    'matched_student': None,
                    'confidence': 'low'
                })

    return results
```

**Step 2: Add grouping function**

Below the detection function, add a function that groups pages into student splits:

```python
def group_pages_by_student(detection_results: list, student_names: list) -> tuple:
    """
    Group sequential pages by detected student names.

    Returns:
        (splits, unmatched_pages) where splits is a list of dicts with
        student_name, pages, confidence, name_found_on_page
    """
    splits = []
    unmatched_pages = []
    current_split = None

    for result in sorted(detection_results, key=lambda x: x['page_num']):
        matched = result.get('matched_student')

        if matched:
            # New student detected — start new split
            if current_split and current_split['student_name'] != matched:
                splits.append(current_split)
            if not current_split or current_split['student_name'] != matched:
                current_split = {
                    'student_name': matched,
                    'name_detected_raw': result['name_detected'],
                    'pages': [],
                    'confidence': result['confidence'],
                    'name_found_on_page': result['page_num']
                }
            current_split['pages'].append(result['page_num'])
        elif current_split:
            # No name on this page — belongs to current student
            current_split['pages'].append(result['page_num'])
        else:
            # No name and no current student — unmatched
            unmatched_pages.append(result['page_num'])

    if current_split:
        splits.append(current_split)

    return splits, unmatched_pages
```

**Step 3: Commit**

```bash
git add utils/ai_marking.py
git commit -m "feat: add AI page-level student name detection and grouping"
```

---

### Task 3: Push notifications — Add validation notification function

**Files:**
- Modify: `utils/push_notifications.py` (add `send_validation_notification`)

**Step 1: Add the function**

After `send_message_notification` (line 288), add:

```python
def send_validation_notification(db, student_id: str, assignment: dict,
                                  submission_id: str) -> bool:
    """
    Send push notification asking student to validate their bulk-uploaded submission.

    Args:
        db: Database instance
        student_id: Student's ID
        assignment: Assignment document
        submission_id: The submission to validate

    Returns:
        True if sent successfully
    """
    students_col = db.db['students']
    student = students_col.find_one({"student_id": student_id})

    if not student or not student.get('push_subscription'):
        return False

    subscription = student['push_subscription']
    if isinstance(subscription, str):
        try:
            subscription = json.loads(subscription)
        except:
            return False

    title = "Please review your submission"
    body = f"Your teacher uploaded your work for '{assignment.get('title', 'Assignment')}'. Please review and confirm your answers."
    url = f"/student/submission/{submission_id}/validate"

    result = send_push_notification(
        subscription_info=subscription,
        title=title,
        body=body,
        url=url,
        tag=f"validate-{submission_id}"
    )

    if result is None:
        students_col.update_one(
            {"student_id": student_id},
            {"$unset": {"push_subscription": ""}}
        )

    return result is True
```

**Step 2: Commit**

```bash
git add utils/push_notifications.py
git commit -m "feat: add push notification for submission validation"
```

---

### Task 4: Routes — Bulk upload and background processing

**Files:**
- Modify: `app.py` (add bulk submission upload route + background processing function)

**Step 1: Add the background processing function**

Near the manual_submission route (around line 7240), add a helper function that runs in a background thread:

```python
def _process_bulk_submission(bulk_id, assignment_id, teacher_id):
    """Background thread: analyze pages and detect student names."""
    from gridfs import GridFS
    from utils.ai_marking import detect_student_names_in_pages, group_pages_by_student
    import fitz  # PyMuPDF for PDF page extraction

    try:
        fs = GridFS(db.db)
        bulk = BulkSubmission.find_one({'bulk_id': bulk_id})
        if not bulk:
            return

        assignment = Assignment.find_one({'assignment_id': assignment_id})
        teacher = Teacher.find_one({'teacher_id': teacher_id})
        students = _get_students_for_assignment(assignment, teacher_id)
        student_names = [s['name'] for s in students]
        student_name_to_id = {s['name']: s['student_id'] for s in students}

        # Extract pages from PDF
        source_file = fs.get(ObjectId(bulk['source_file_id']))
        pdf_bytes = source_file.read()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render page to image (300 DPI for good OCR quality)
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("jpeg")
            pages.append({
                'type': 'image',
                'data': img_bytes,
                'page_num': page_num + 1
            })
        doc.close()

        BulkSubmission.update_one(
            {'bulk_id': bulk_id},
            {'$set': {'total_pages': len(pages), 'status': 'processing'}}
        )

        # Detect student names
        detection_results = detect_student_names_in_pages(pages, student_names, teacher)

        # Group pages by student
        splits, unmatched_pages = group_pages_by_student(detection_results, student_names)

        # Map student names to IDs
        splits_with_ids = []
        for split in splits:
            student_id = student_name_to_id.get(split['student_name'])
            splits_with_ids.append({
                'student_id': student_id,
                'student_name': split['student_name'],
                'student_name_detected': split['name_detected_raw'],
                'pages': split['pages'],
                'confidence': split['confidence'],
                'name_found_on_page': split['name_found_on_page']
            })

        # Find missing students (in class but not detected in PDF)
        detected_ids = {s['student_id'] for s in splits_with_ids if s['student_id']}
        missing_students = [
            {'student_id': s['student_id'], 'student_name': s['name']}
            for s in students if s['student_id'] not in detected_ids
        ]

        BulkSubmission.update_one(
            {'bulk_id': bulk_id},
            {'$set': {
                'splits': splits_with_ids,
                'unmatched_pages': unmatched_pages,
                'missing_students': missing_students,
                'status': 'ready_for_review'
            }}
        )

    except Exception as e:
        logger.error(f"Bulk submission processing error: {e}")
        BulkSubmission.update_one(
            {'bulk_id': bulk_id},
            {'$set': {'status': 'failed', 'processing_error': str(e)}}
        )
```

**Step 2: Add the upload route**

After the helper function, add the route:

```python
@app.route('/teacher/assignment/<assignment_id>/bulk-submission', methods=['GET', 'POST'])
@teacher_required
def bulk_submission(assignment_id):
    """Upload entire class PDF for bulk splitting and submission."""
    teacher = Teacher.find_one({'teacher_id': session['teacher_id']})
    assignment = Assignment.find_one({
        'assignment_id': assignment_id,
        'teacher_id': session['teacher_id']
    })
    if not assignment:
        return redirect(url_for('teacher_assignments'))

    all_students = _get_students_for_assignment(assignment, session['teacher_id'])

    if request.method == 'GET':
        return render_template('teacher_bulk_submission.html',
                             teacher=teacher,
                             assignment=assignment,
                             student_count=len(all_students))

    # POST: upload PDF and start background processing
    from gridfs import GridFS

    file = request.files.get('pdf_file')
    if not file or not file.filename:
        return render_template('teacher_bulk_submission.html',
                             teacher=teacher,
                             assignment=assignment,
                             student_count=len(all_students),
                             error='Please upload a PDF file.')

    if not file.filename.lower().endswith('.pdf'):
        return render_template('teacher_bulk_submission.html',
                             teacher=teacher,
                             assignment=assignment,
                             student_count=len(all_students),
                             error='Only PDF files are accepted for bulk upload.')

    require_validation = request.form.get('require_validation') == 'on'

    # Store PDF in GridFS
    fs = GridFS(db.db)
    file_data = file.read()
    source_file_id = fs.put(
        file_data,
        filename=f"bulk_{assignment_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf",
        content_type='application/pdf'
    )

    bulk_id = generate_bulk_id()
    BulkSubmission.insert_one({
        'bulk_id': bulk_id,
        'assignment_id': assignment_id,
        'teacher_id': session['teacher_id'],
        'require_validation': require_validation,
        'status': 'processing',
        'created_at': datetime.utcnow(),
        'source_file_id': str(source_file_id),
        'total_pages': 0,
        'splits': [],
        'unmatched_pages': [],
        'missing_students': []
    })

    # Start background processing
    t = threading.Thread(
        target=_process_bulk_submission,
        args=(bulk_id, assignment_id, session['teacher_id']),
        daemon=True
    )
    t.start()

    return redirect(url_for('bulk_review', assignment_id=assignment_id, bulk_id=bulk_id))
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add bulk submission upload route with background processing"
```

---

### Task 5: Routes — Bulk review and confirm

**Files:**
- Modify: `app.py` (add review GET route, confirm POST route, status poll API)

**Step 1: Add the review route**

```python
@app.route('/teacher/assignment/<assignment_id>/bulk-review/<bulk_id>')
@teacher_required
def bulk_review(assignment_id, bulk_id):
    """Review AI-detected page splits for bulk submission."""
    teacher = Teacher.find_one({'teacher_id': session['teacher_id']})
    assignment = Assignment.find_one({
        'assignment_id': assignment_id,
        'teacher_id': session['teacher_id']
    })
    if not assignment:
        return redirect(url_for('teacher_assignments'))

    bulk = BulkSubmission.find_one({'bulk_id': bulk_id, 'teacher_id': session['teacher_id']})
    if not bulk:
        return redirect(url_for('teacher_assignments'))

    all_students = _get_students_for_assignment(assignment, session['teacher_id'])

    return render_template('teacher_bulk_review.html',
                         teacher=teacher,
                         assignment=assignment,
                         bulk=bulk,
                         students=all_students)
```

**Step 2: Add status polling API**

```python
@app.route('/api/teacher/bulk-status/<bulk_id>')
@teacher_required
def bulk_status(bulk_id):
    """Poll bulk submission processing status."""
    bulk = BulkSubmission.find_one(
        {'bulk_id': bulk_id, 'teacher_id': session['teacher_id']},
        {'status': 1, 'splits': 1, 'unmatched_pages': 1, 'missing_students': 1,
         'total_pages': 1, 'processing_error': 1}
    )
    if not bulk:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    return jsonify({
        'success': True,
        'status': bulk['status'],
        'total_pages': bulk.get('total_pages', 0),
        'splits': bulk.get('splits', []),
        'unmatched_pages': bulk.get('unmatched_pages', []),
        'missing_students': bulk.get('missing_students', []),
        'processing_error': bulk.get('processing_error')
    })
```

**Step 3: Add the confirm route**

This is the most complex route — it creates individual submissions per student:

```python
@app.route('/teacher/assignment/<assignment_id>/bulk-review/<bulk_id>/confirm', methods=['POST'])
@teacher_required
def bulk_confirm(assignment_id, bulk_id):
    """Confirm bulk splits and create individual submissions."""
    from gridfs import GridFS
    from utils.ai_marking import analyze_submission_images, analyze_essay_with_rubrics, ocr_extract_answers
    import fitz

    assignment = Assignment.find_one({
        'assignment_id': assignment_id,
        'teacher_id': session['teacher_id']
    })
    if not assignment:
        return jsonify({'success': False, 'error': 'Assignment not found'}), 404

    bulk = BulkSubmission.find_one({'bulk_id': bulk_id, 'teacher_id': session['teacher_id']})
    if not bulk or bulk['status'] != 'ready_for_review':
        return jsonify({'success': False, 'error': 'Bulk submission not ready'}), 400

    teacher = Teacher.find_one({'teacher_id': session['teacher_id']})

    # Get teacher's edited splits from POST body
    edited_splits = request.json.get('splits', [])
    if not edited_splits:
        return jsonify({'success': False, 'error': 'No splits provided'}), 400

    fs = GridFS(db.db)

    # Load the source PDF
    source_file = fs.get(ObjectId(bulk['source_file_id']))
    pdf_bytes = source_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    require_validation = bulk.get('require_validation', False)
    submission_ids = []

    for split in edited_splits:
        student_id = split.get('student_id')
        page_numbers = split.get('pages', [])
        if not student_id or not page_numbers:
            continue

        # Check for existing submission
        existing_sub = Submission.find_one(
            {'assignment_id': assignment_id, 'student_id': student_id},
            sort=[('submitted_at', -1), ('created_at', -1)]
        )

        if existing_sub:
            submission_id = existing_sub['submission_id']
            # Delete old files
            for old_fid in existing_sub.get('file_ids', []):
                try:
                    fs.delete(ObjectId(old_fid))
                except Exception:
                    pass
        else:
            submission_id = generate_submission_id()

        # Extract pages for this student and store in GridFS
        file_ids = []
        pages_data = []
        for idx, page_num in enumerate(sorted(page_numbers)):
            page = doc[page_num - 1]  # 0-indexed
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("jpeg")

            file_id = fs.put(
                img_bytes,
                filename=f"{submission_id}_page_{idx+1}.jpg",
                content_type='image/jpeg',
                submission_id=submission_id,
                page_num=idx + 1
            )
            file_ids.append(str(file_id))
            pages_data.append({'type': 'image', 'data': img_bytes, 'page_num': idx + 1})

        submission_doc = {
            'submission_id': submission_id,
            'assignment_id': assignment_id,
            'student_id': student_id,
            'teacher_id': assignment['teacher_id'],
            'file_ids': file_ids,
            'file_type': 'image',
            'page_count': len(file_ids),
            'status': 'submitted',
            'submitted_at': datetime.utcnow(),
            'submitted_via': 'bulk',
            'submitted_by_teacher': session['teacher_id'],
            'bulk_id': bulk_id,
            'created_at': existing_sub['created_at'] if existing_sub else datetime.utcnow()
        }

        if require_validation:
            submission_doc['pending_validation'] = True

        if existing_sub:
            Submission.update_one(
                {'submission_id': submission_id},
                {'$set': submission_doc,
                 '$unset': {'rejection_reason': '', 'rejected_at': '', 'rejected_by': ''}}
            )
        else:
            Submission.insert_one(submission_doc)

        submission_ids.append(submission_id)

        if require_validation:
            # Send validation notification
            from utils.push_notifications import send_validation_notification
            send_validation_notification(db, student_id, assignment, submission_id)
        else:
            # Run AI marking immediately in current thread (blocking)
            try:
                marking_type = assignment.get('marking_type', 'standard')
                if marking_type == 'rubric':
                    rubrics_content = None
                    if assignment.get('rubrics_id'):
                        try:
                            rubrics_file = fs.get(assignment['rubrics_id'])
                            rubrics_content = rubrics_file.read()
                        except Exception:
                            pass
                    ai_result = analyze_essay_with_rubrics(pages_data, assignment, rubrics_content, teacher)
                else:
                    answer_key_content = None
                    if assignment.get('answer_key_id'):
                        try:
                            answer_file = fs.get(assignment['answer_key_id'])
                            answer_key_content = answer_file.read()
                        except Exception:
                            pass
                    ai_result = analyze_submission_images(pages_data, assignment, answer_key_content, teacher)

                Submission.update_one(
                    {'submission_id': submission_id},
                    {'$set': {'ai_feedback': ai_result, 'status': 'ai_reviewed'}}
                )
            except Exception as e:
                logger.error(f"AI feedback error on bulk submission {submission_id}: {e}")
                Submission.update_one(
                    {'submission_id': submission_id},
                    {'$set': {'ai_feedback': {'error': str(e), 'questions': [], 'overall_feedback': f'Error: {e}'}}}
                )

    doc.close()

    # Update bulk submission status
    BulkSubmission.update_one(
        {'bulk_id': bulk_id},
        {'$set': {
            'status': 'confirmed',
            'confirmed_at': datetime.utcnow(),
            'submission_ids': submission_ids
        }}
    )

    return jsonify({
        'success': True,
        'submission_count': len(submission_ids),
        'redirect_url': url_for('teacher_submissions') + f'?assignment_id={assignment_id}'
    })
```

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add bulk review, status polling, and confirm routes"
```

---

### Task 6: Routes — Student validation

**Files:**
- Modify: `app.py` (add student validation page + API)

**Step 1: Add the validation page route**

```python
@app.route('/student/submission/<submission_id>/validate')
@login_required
def validate_submission(submission_id):
    """Student validates their bulk-uploaded submission answers."""
    submission = Submission.find_one({
        'submission_id': submission_id,
        'student_id': session['student_id']
    })
    if not submission or not submission.get('pending_validation'):
        return redirect(url_for('dashboard'))

    assignment = Assignment.find_one({'assignment_id': submission['assignment_id']})
    if not assignment:
        return redirect(url_for('dashboard'))

    return render_template('student_validate_submission.html',
                         assignment=assignment,
                         submission=submission)
```

**Step 2: Add the validation API**

```python
@app.route('/api/student/submission/<submission_id>/validate', methods=['POST'])
@login_required
def api_validate_submission(submission_id):
    """Student confirms their validated answers, triggers AI marking."""
    from gridfs import GridFS
    from utils.ai_marking import analyze_submission_images, analyze_essay_with_rubrics

    submission = Submission.find_one({
        'submission_id': submission_id,
        'student_id': session['student_id']
    })
    if not submission or not submission.get('pending_validation'):
        return jsonify({'success': False, 'error': 'Submission not found or already validated'}), 404

    confirmed_answers = request.json.get('confirmed_answers')

    # Clear pending_validation, store confirmed answers
    update_fields = {
        'pending_validation': False,
        'validated_at': datetime.utcnow()
    }
    if confirmed_answers:
        update_fields['student_confirmed_answers'] = confirmed_answers

    Submission.update_one(
        {'submission_id': submission_id},
        {'$set': update_fields, '$unset': {'pending_validation': ''}}
    )

    # Trigger AI marking
    assignment = Assignment.find_one({'assignment_id': submission['assignment_id']})
    teacher = Teacher.find_one({'teacher_id': submission['teacher_id']})

    fs = GridFS(db.db)
    pages = []
    for i, fid in enumerate(submission.get('file_ids', [])):
        try:
            f = fs.get(ObjectId(fid))
            pages.append({'type': 'image', 'data': f.read(), 'page_num': i + 1})
        except Exception:
            pass

    try:
        marking_type = assignment.get('marking_type', 'standard')
        if marking_type == 'rubric':
            rubrics_content = None
            if assignment.get('rubrics_id'):
                try:
                    rubrics_file = fs.get(assignment['rubrics_id'])
                    rubrics_content = rubrics_file.read()
                except Exception:
                    pass
            ai_result = analyze_essay_with_rubrics(pages, assignment, rubrics_content, teacher,
                                                     student_answers=confirmed_answers)
        else:
            answer_key_content = None
            if assignment.get('answer_key_id'):
                try:
                    answer_file = fs.get(assignment['answer_key_id'])
                    answer_key_content = answer_file.read()
                except Exception:
                    pass
            ai_result = analyze_submission_images(pages, assignment, answer_key_content, teacher,
                                                    student_answers=confirmed_answers)

        Submission.update_one(
            {'submission_id': submission_id},
            {'$set': {'ai_feedback': ai_result, 'status': 'ai_reviewed'}}
        )
    except Exception as e:
        logger.error(f"AI feedback error on validated submission {submission_id}: {e}")
        Submission.update_one(
            {'submission_id': submission_id},
            {'$set': {'ai_feedback': {'error': str(e)}, 'status': 'submitted'}}
        )

    return jsonify({'success': True, 'redirect_url': url_for('dashboard')})
```

**Step 3: Add force-submit route for teachers**

```python
@app.route('/api/teacher/submission/<submission_id>/force-validate', methods=['POST'])
@teacher_required
def force_validate_submission(submission_id):
    """Teacher force-validates a submission, skipping student review."""
    submission = Submission.find_one({'submission_id': submission_id})
    if not submission or not submission.get('pending_validation'):
        return jsonify({'success': False, 'error': 'Not found or not pending'}), 404

    # Verify teacher owns this assignment
    assignment = Assignment.find_one({
        'assignment_id': submission['assignment_id'],
        'teacher_id': session['teacher_id']
    })
    if not assignment:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    Submission.update_one(
        {'submission_id': submission_id},
        {'$set': {'pending_validation': False, 'force_validated_by': session['teacher_id'],
                  'validated_at': datetime.utcnow()},
         '$unset': {'pending_validation': ''}}
    )

    # Trigger AI marking in background thread
    def _mark_submission():
        from gridfs import GridFS
        from utils.ai_marking import analyze_submission_images, analyze_essay_with_rubrics
        fs = GridFS(db.db)
        teacher = Teacher.find_one({'teacher_id': session['teacher_id']})
        pages = []
        for i, fid in enumerate(submission.get('file_ids', [])):
            try:
                f = fs.get(ObjectId(fid))
                pages.append({'type': 'image', 'data': f.read(), 'page_num': i + 1})
            except Exception:
                pass
        try:
            marking_type = assignment.get('marking_type', 'standard')
            if marking_type == 'rubric':
                rubrics_content = None
                if assignment.get('rubrics_id'):
                    try:
                        rubrics_file = fs.get(assignment['rubrics_id'])
                        rubrics_content = rubrics_file.read()
                    except Exception:
                        pass
                ai_result = analyze_essay_with_rubrics(pages, assignment, rubrics_content, teacher)
            else:
                answer_key_content = None
                if assignment.get('answer_key_id'):
                    try:
                        answer_file = fs.get(assignment['answer_key_id'])
                        answer_key_content = answer_file.read()
                    except Exception:
                        pass
                ai_result = analyze_submission_images(pages, assignment, answer_key_content, teacher)
            Submission.update_one(
                {'submission_id': submission_id},
                {'$set': {'ai_feedback': ai_result, 'status': 'ai_reviewed'}}
            )
        except Exception as e:
            logger.error(f"AI feedback error on force-validated {submission_id}: {e}")

    t = threading.Thread(target=_mark_submission, daemon=True)
    t.start()

    return jsonify({'success': True})
```

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add student validation and teacher force-validate routes"
```

---

### Task 7: Template — Bulk upload form

**Files:**
- Create: `templates/teacher_bulk_submission.html`

**Step 1: Create the template**

Following the pattern of `teacher_manual_submission.html`:

```html
{% extends "base.html" %}

{% block title %}Bulk Submission - Teacher Portal{% endblock %}

{% block navbar %}
{% set active_nav = 'submissions' %}
{% include 'partials/teacher_navbar.html' %}
{% endblock %}

{% block content %}
<div class="container py-4">
    <nav aria-label="breadcrumb" class="mb-3">
        <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="{{ url_for('teacher_assignments') }}">Assignments</a></li>
            <li class="breadcrumb-item"><a href="{{ url_for('assignment_summary', assignment_id=assignment.assignment_id) }}">{{ assignment.title }}</a></li>
            <li class="breadcrumb-item active">Bulk Submission</li>
        </ol>
    </nav>

    <div class="row justify-content-center">
        <div class="col-lg-8">
            <div class="card">
                <div class="card-header bg-primary text-white">
                    <h5 class="mb-0"><i class="bi bi-stack me-2"></i>Bulk class submission</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-4">
                        Upload a single PDF containing the entire class's scanned work.
                        The system will use AI to detect student names and split the pages automatically.
                        You'll review the splits before submissions are created.
                    </p>
                    <div class="alert alert-info mb-4">
                        <i class="bi bi-info-circle me-2"></i>
                        <strong>{{ student_count }} students</strong> are assigned to this assignment.
                        Make sure each student's name is visible somewhere on their pages.
                    </div>

                    {% if error %}
                    <div class="alert alert-danger mb-4">
                        <i class="bi bi-exclamation-triangle me-2"></i>{{ error }}
                    </div>
                    {% endif %}

                    <form method="post" enctype="multipart/form-data">
                        <div class="mb-4">
                            <label for="pdf_file" class="form-label fw-bold">Upload class PDF *</label>
                            <input type="file" class="form-control" id="pdf_file" name="pdf_file" accept=".pdf" required>
                            <small class="text-muted">Single PDF containing all students' work scanned in order.</small>
                        </div>

                        <div class="mb-4">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="require_validation" name="require_validation">
                                <label class="form-check-label" for="require_validation">
                                    <strong>Require student validation</strong>
                                </label>
                            </div>
                            <small class="text-muted">
                                When enabled, students will be notified to review and confirm their extracted answers before AI marking runs.
                                When disabled, AI marking runs immediately after you confirm the splits.
                            </small>
                        </div>

                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">
                                <i class="bi bi-upload me-1"></i>Upload & Process
                            </button>
                            <a href="{{ url_for('assignment_summary', assignment_id=assignment.assignment_id) }}" class="btn btn-outline-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 2: Commit**

```bash
git add templates/teacher_bulk_submission.html
git commit -m "feat: add bulk submission upload template"
```

---

### Task 8: Template — Bulk review page

**Files:**
- Create: `templates/teacher_bulk_review.html`

**Step 1: Create the template**

This is the most complex template. It shows a processing spinner (polls status), then the split review table with edit capability:

```html
{% extends "base.html" %}

{% block title %}Review Bulk Submission - Teacher Portal{% endblock %}

{% block navbar %}
{% set active_nav = 'submissions' %}
{% include 'partials/teacher_navbar.html' %}
{% endblock %}

{% block content %}
<div class="container py-4">
    <nav aria-label="breadcrumb" class="mb-3">
        <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="{{ url_for('teacher_assignments') }}">Assignments</a></li>
            <li class="breadcrumb-item"><a href="{{ url_for('assignment_summary', assignment_id=assignment.assignment_id) }}">{{ assignment.title }}</a></li>
            <li class="breadcrumb-item active">Review Bulk Submission</li>
        </ol>
    </nav>

    <!-- Processing state -->
    <div id="processing-state" {% if bulk.status != 'processing' %}style="display:none"{% endif %}>
        <div class="card">
            <div class="card-body text-center py-5">
                <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Processing...</span>
                </div>
                <h4>Analyzing pages...</h4>
                <p class="text-muted" id="processing-status">Detecting student names using AI. This may take a minute or two.</p>
                <p class="text-muted"><small>Pages detected: <span id="page-count">0</span></small></p>
            </div>
        </div>
    </div>

    <!-- Error state -->
    <div id="error-state" style="display:none">
        <div class="alert alert-danger">
            <h5><i class="bi bi-exclamation-triangle me-2"></i>Processing failed</h5>
            <p id="error-message"></p>
            <a href="{{ url_for('bulk_submission', assignment_id=assignment.assignment_id) }}" class="btn btn-outline-danger">Try again</a>
        </div>
    </div>

    <!-- Review state -->
    <div id="review-state" {% if bulk.status != 'ready_for_review' %}style="display:none"{% endif %}>
        <div class="card mb-4">
            <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="bi bi-check-circle me-2"></i>Review detected splits</h5>
                <span class="badge bg-white text-success" id="total-pages-badge">{{ bulk.total_pages }} pages</span>
            </div>
            <div class="card-body">
                <p class="text-muted mb-3">
                    Review the AI-detected student assignments below. You can reassign pages using the dropdowns.
                    {% if bulk.require_validation %}
                    <span class="badge bg-info">Student validation enabled</span>
                    {% endif %}
                </p>

                <!-- Summary stats -->
                <div class="row mb-4" id="stats-row">
                    <div class="col-md-3">
                        <div class="border rounded p-3 text-center">
                            <div class="fs-3 fw-bold text-success" id="matched-count">0</div>
                            <small class="text-muted">Students matched</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border rounded p-3 text-center">
                            <div class="fs-3 fw-bold text-warning" id="low-confidence-count">0</div>
                            <small class="text-muted">Low confidence</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border rounded p-3 text-center">
                            <div class="fs-3 fw-bold text-danger" id="unmatched-count">0</div>
                            <small class="text-muted">Unmatched pages</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border rounded p-3 text-center">
                            <div class="fs-3 fw-bold text-secondary" id="missing-count">0</div>
                            <small class="text-muted">Missing students</small>
                        </div>
                    </div>
                </div>

                <!-- Splits table -->
                <div class="table-responsive">
                    <table class="table table-hover" id="splits-table">
                        <thead>
                            <tr>
                                <th>Student</th>
                                <th>Pages</th>
                                <th>Confidence</th>
                                <th>Name detected</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="splits-tbody"></tbody>
                    </table>
                </div>

                <!-- Unmatched pages section -->
                <div id="unmatched-section" style="display:none" class="mt-4">
                    <h6 class="text-danger"><i class="bi bi-question-circle me-1"></i>Unmatched pages</h6>
                    <div id="unmatched-list" class="mb-3"></div>
                </div>

                <!-- Missing students section -->
                <div id="missing-section" style="display:none" class="mt-4">
                    <h6 class="text-secondary"><i class="bi bi-person-x me-1"></i>Students not found in PDF</h6>
                    <div id="missing-list" class="mb-3"></div>
                </div>

                <hr>
                <div class="d-flex gap-2">
                    <button class="btn btn-success btn-lg" id="confirm-btn" onclick="confirmSplits()">
                        <i class="bi bi-check-lg me-1"></i>Confirm & Create Submissions
                    </button>
                    <a href="{{ url_for('bulk_submission', assignment_id=assignment.assignment_id) }}" class="btn btn-outline-secondary">
                        Start over
                    </a>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
.confidence-high { color: #198754; font-weight: 600; }
.confidence-low { color: #dc3545; font-weight: 600; }
.split-row.low-confidence { background-color: #fff3cd; }
</style>

<script>
const bulkId = '{{ bulk.bulk_id }}';
const assignmentId = '{{ assignment.assignment_id }}';
const students = {{ students | tojson }};
let currentSplits = [];

// Build student options HTML for dropdowns
function studentOptions(selectedId) {
    let html = '<option value="">-- Unassigned --</option>';
    for (const s of students) {
        const sel = s.student_id === selectedId ? 'selected' : '';
        html += `<option value="${s.student_id}" ${sel}>${s.name} (${s.student_id})</option>`;
    }
    return html;
}

// Poll for processing completion
{% if bulk.status == 'processing' %}
const pollInterval = setInterval(async () => {
    try {
        const resp = await fetch(`/api/teacher/bulk-status/${bulkId}`);
        const data = await resp.json();

        if (!data.success) return;

        document.getElementById('page-count').textContent = data.total_pages || '...';

        if (data.status === 'ready_for_review') {
            clearInterval(pollInterval);
            document.getElementById('processing-state').style.display = 'none';
            document.getElementById('review-state').style.display = 'block';
            renderSplits(data);
        } else if (data.status === 'failed') {
            clearInterval(pollInterval);
            document.getElementById('processing-state').style.display = 'none';
            document.getElementById('error-state').style.display = 'block';
            document.getElementById('error-message').textContent = data.processing_error || 'Unknown error';
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
}, 3000);
{% else if bulk.status == 'ready_for_review' %}
// Already ready — render immediately
document.addEventListener('DOMContentLoaded', () => {
    renderSplits({{ bulk | tojson }});
});
{% endif %}

function renderSplits(data) {
    currentSplits = data.splits || [];
    const tbody = document.getElementById('splits-tbody');
    const unmatched = data.unmatched_pages || [];
    const missing = data.missing_students || [];

    // Stats
    document.getElementById('total-pages-badge').textContent = `${data.total_pages} pages`;
    document.getElementById('matched-count').textContent = currentSplits.filter(s => s.confidence === 'high').length;
    document.getElementById('low-confidence-count').textContent = currentSplits.filter(s => s.confidence === 'low').length;
    document.getElementById('unmatched-count').textContent = unmatched.length;
    document.getElementById('missing-count').textContent = missing.length;

    // Render splits table
    tbody.innerHTML = '';
    currentSplits.forEach((split, idx) => {
        const row = document.createElement('tr');
        row.className = `split-row ${split.confidence === 'low' ? 'low-confidence' : ''}`;
        row.innerHTML = `
            <td>
                <select class="form-select form-select-sm split-student" data-idx="${idx}">
                    ${studentOptions(split.student_id)}
                </select>
            </td>
            <td>${split.pages.join(', ')}</td>
            <td><span class="confidence-${split.confidence}">${split.confidence}</span></td>
            <td><small class="text-muted">${split.student_name_detected || '-'}</small></td>
            <td>
                <button class="btn btn-sm btn-outline-danger" onclick="removeSplit(${idx})" title="Remove">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });

    // Unmatched pages
    if (unmatched.length > 0) {
        document.getElementById('unmatched-section').style.display = 'block';
        const list = document.getElementById('unmatched-list');
        list.innerHTML = unmatched.map(p => `
            <div class="d-inline-flex align-items-center gap-2 me-3 mb-2">
                <span class="badge bg-danger">Page ${p}</span>
                <select class="form-select form-select-sm unmatched-assign" data-page="${p}" style="width:200px">
                    ${studentOptions('')}
                </select>
            </div>
        `).join('');
    }

    // Missing students
    if (missing.length > 0) {
        document.getElementById('missing-section').style.display = 'block';
        document.getElementById('missing-list').innerHTML = missing.map(m =>
            `<span class="badge bg-secondary me-1">${m.student_name}</span>`
        ).join('');
    }
}

function removeSplit(idx) {
    currentSplits.splice(idx, 1);
    renderSplits({
        splits: currentSplits,
        total_pages: parseInt(document.getElementById('total-pages-badge').textContent),
        unmatched_pages: [],
        missing_students: []
    });
}

async function confirmSplits() {
    const btn = document.getElementById('confirm-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Creating submissions...';

    // Collect final splits from dropdowns
    const finalSplits = [];
    document.querySelectorAll('.split-student').forEach((select, idx) => {
        if (select.value && currentSplits[idx]) {
            finalSplits.push({
                student_id: select.value,
                pages: currentSplits[idx].pages
            });
        }
    });

    // Add any assigned unmatched pages
    document.querySelectorAll('.unmatched-assign').forEach(select => {
        if (select.value) {
            const pageNum = parseInt(select.dataset.page);
            // Find if student already has a split
            const existing = finalSplits.find(s => s.student_id === select.value);
            if (existing) {
                existing.pages.push(pageNum);
                existing.pages.sort((a, b) => a - b);
            } else {
                finalSplits.push({ student_id: select.value, pages: [pageNum] });
            }
        }
    });

    try {
        const resp = await fetch(`/teacher/assignment/${assignmentId}/bulk-review/${bulkId}/confirm`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ splits: finalSplits })
        });
        const data = await resp.json();

        if (data.success) {
            window.location.href = data.redirect_url;
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Confirm & Create Submissions';
        }
    } catch (e) {
        alert('Network error: ' + e.message);
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Confirm & Create Submissions';
    }
}
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add templates/teacher_bulk_review.html
git commit -m "feat: add bulk review template with split editing and confirmation"
```

---

### Task 9: Template — Student validation page

**Files:**
- Create: `templates/student_validate_submission.html`

**Step 1: Create the template**

Reuses the OCR review pattern from `assignment_view.html` (two-panel layout):

```html
{% extends "base.html" %}

{% block title %}Validate Submission{% endblock %}

{% block navbar %}
{% include 'partials/student_navbar.html' %}
{% endblock %}

{% block content %}
<div class="container-fluid py-3">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
            <h4 class="mb-1">Review your submission</h4>
            <p class="text-muted mb-0">{{ assignment.title }} — Please review the extracted answers and confirm.</p>
        </div>
        <div class="d-flex gap-2">
            <button class="btn btn-outline-warning" onclick="reportIssue()">
                <i class="bi bi-flag me-1"></i>Report issue
            </button>
            <button class="btn btn-success btn-lg" id="confirm-btn" onclick="confirmValidation()">
                <i class="bi bi-check-lg me-1"></i>Confirm answers
            </button>
        </div>
    </div>

    <div class="row" style="height: calc(100vh - 160px);">
        <!-- Left: page images -->
        <div class="col-md-5" style="overflow-y: auto; border-right: 1px solid #dee2e6; height: 100%;">
            <h6 class="sticky-top bg-white py-2">Your scanned pages</h6>
            <div id="page-images">
                <div class="text-center py-4">
                    <div class="spinner-border text-primary"></div>
                    <p class="text-muted mt-2">Loading pages...</p>
                </div>
            </div>
        </div>

        <!-- Right: extracted answers -->
        <div class="col-md-7" style="overflow-y: auto; height: 100%;">
            <h6 class="sticky-top bg-white py-2">Extracted answers <small class="text-muted">(you can edit before confirming)</small></h6>
            <div id="answers-panel">
                <div class="text-center py-4">
                    <div class="spinner-border text-primary"></div>
                    <p class="text-muted mt-2">Extracting answers with OCR...</p>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
const submissionId = '{{ submission.submission_id }}';
const assignmentId = '{{ assignment.assignment_id }}';
const fileCount = {{ submission.file_ids | length }};

// Load page images
async function loadPages() {
    const container = document.getElementById('page-images');
    let html = '';
    for (let i = 0; i < fileCount; i++) {
        html += `<img src="/student/submission/${submissionId}/file/${i}"
                      class="img-fluid rounded border mb-3"
                      alt="Page ${i + 1}"
                      style="width: 100%;">`;
    }
    container.innerHTML = html;
}

// Run OCR to extract answers
async function loadOcrAnswers() {
    try {
        const resp = await fetch(`/api/student/bulk-ocr-preview/${submissionId}`);
        const data = await resp.json();

        if (!data.success) {
            document.getElementById('answers-panel').innerHTML =
                `<div class="alert alert-warning">Could not extract answers: ${data.error}</div>`;
            return;
        }

        const result = data.ocr_result;
        const panel = document.getElementById('answers-panel');

        if (result.essay_text) {
            // Essay type
            panel.innerHTML = `
                <div class="mb-3">
                    <label class="form-label fw-bold">Your essay</label>
                    <textarea class="form-control answer-field" data-type="essay" rows="15">${result.essay_text}</textarea>
                </div>`;
        } else if (result.questions) {
            // Question-based
            let html = '';
            result.questions.forEach((q, idx) => {
                const isBlank = !q.answer || q.answer.trim() === '';
                html += `
                    <div class="card mb-3 ${isBlank ? 'border-warning' : ''}">
                        <div class="card-body">
                            <div class="d-flex justify-content-between">
                                <label class="form-label fw-bold">Question ${q.question_number || idx + 1}</label>
                                ${isBlank ? '<span class="badge bg-warning text-dark">Blank</span>' : ''}
                            </div>
                            <textarea class="form-control answer-field"
                                      data-question="${q.question_number || idx + 1}"
                                      rows="3">${q.answer || ''}</textarea>
                        </div>
                    </div>`;
            });
            panel.innerHTML = html;
        }
    } catch (e) {
        document.getElementById('answers-panel').innerHTML =
            `<div class="alert alert-danger">Error loading answers: ${e.message}</div>`;
    }
}

async function confirmValidation() {
    const btn = document.getElementById('confirm-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Submitting...';

    // Collect answers
    const answers = {};
    document.querySelectorAll('.answer-field').forEach(field => {
        if (field.dataset.type === 'essay') {
            answers.essay_text = field.value;
        } else {
            answers[field.dataset.question] = field.value;
        }
    });

    try {
        const resp = await fetch(`/api/student/submission/${submissionId}/validate`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ confirmed_answers: answers })
        });
        const data = await resp.json();

        if (data.success) {
            window.location.href = data.redirect_url || '/dashboard';
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Confirm answers';
        }
    } catch (e) {
        alert('Network error: ' + e.message);
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Confirm answers';
    }
}

function reportIssue() {
    if (confirm('This will flag the submission for your teacher to review. The pages assigned to you may be incorrect. Continue?')) {
        fetch(`/api/student/submission/${submissionId}/report-issue`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        }).then(() => {
            alert('Issue reported. Your teacher will review this.');
            window.location.href = '/dashboard';
        });
    }
}

// Init
loadPages();
loadOcrAnswers();
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add templates/student_validate_submission.html
git commit -m "feat: add student validation template with OCR answer editing"
```

---

### Task 10: Routes — Supporting APIs for validation page

**Files:**
- Modify: `app.py` (add OCR preview for existing submission, report issue API)

**Step 1: Add OCR preview for bulk submissions**

This endpoint runs OCR on an already-stored submission's files (unlike the existing `/api/student/ocr-preview` which works on uploaded files):

```python
@app.route('/api/student/bulk-ocr-preview/<submission_id>')
@login_required
def bulk_ocr_preview(submission_id):
    """Run OCR on an existing submission's stored files for validation."""
    from gridfs import GridFS
    from utils.ai_marking import ocr_extract_answers

    submission = Submission.find_one({
        'submission_id': submission_id,
        'student_id': session['student_id'],
        'pending_validation': True
    })
    if not submission:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    assignment = Assignment.find_one({'assignment_id': submission['assignment_id']})
    teacher = Teacher.find_one({'teacher_id': submission['teacher_id']})

    fs = GridFS(db.db)
    pages = []
    for i, fid in enumerate(submission.get('file_ids', [])):
        try:
            f = fs.get(ObjectId(fid))
            file_data = f.read()
            pages.append({'type': 'image', 'data': file_data, 'page_num': i + 1})
        except Exception:
            pass

    if not pages:
        return jsonify({'success': False, 'error': 'No files found'}), 404

    # Load question paper for context if available
    question_paper_content = None
    if assignment.get('question_paper_id'):
        try:
            qp_file = fs.get(assignment['question_paper_id'])
            question_paper_content = qp_file.read()
        except Exception:
            pass

    try:
        result = ocr_extract_answers(pages, assignment, teacher, question_paper_content)
        return jsonify({'success': True, 'ocr_result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Step 2: Add report issue API**

```python
@app.route('/api/student/submission/<submission_id>/report-issue', methods=['POST'])
@login_required
def report_submission_issue(submission_id):
    """Student reports an issue with their bulk-uploaded submission."""
    submission = Submission.find_one({
        'submission_id': submission_id,
        'student_id': session['student_id']
    })
    if not submission:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    Submission.update_one(
        {'submission_id': submission_id},
        {'$set': {'issue_reported': True, 'issue_reported_at': datetime.utcnow()}}
    )
    return jsonify({'success': True})
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add bulk OCR preview and report issue APIs"
```

---

### Task 11: Navigation — Add bulk submission button and dashboard banner

**Files:**
- Modify: `templates/teacher_submissions.html:17-21` (add bulk submission button next to manual)
- Modify: `app.py` (student dashboard — add pending validation count)

**Step 1: Add bulk submission button to teacher submissions page**

In `templates/teacher_submissions.html`, change the manual submission button area (lines 17-21) to include both buttons:

```html
{% if selected_assignment %}
<div class="d-flex gap-2">
    <a href="{{ url_for('manual_submission', assignment_id=selected_assignment.assignment_id) }}" class="btn btn-primary">
        <i class="bi bi-file-earmark-plus me-1"></i>Manual submission
    </a>
    <a href="{{ url_for('bulk_submission', assignment_id=selected_assignment.assignment_id) }}" class="btn btn-outline-primary">
        <i class="bi bi-stack me-1"></i>Bulk submission
    </a>
</div>
{% endif %}
```

**Step 2: Add pending validation banner to student dashboard**

In `app.py`, in the `dashboard()` function (around line 402), add a query for pending validations and pass it to the template:

```python
pending_validations = list(Submission.find({
    'student_id': session['student_id'],
    'pending_validation': True
}))
```

Pass `pending_validations=pending_validations` to the template render call.

In the student dashboard template, add a banner at the top of the content area:

```html
{% if pending_validations %}
<div class="alert alert-info mb-4">
    <i class="bi bi-clipboard-check me-2"></i>
    <strong>{{ pending_validations|length }} submission(s) need your review.</strong>
    {% for pv in pending_validations %}
    <a href="{{ url_for('validate_submission', submission_id=pv.submission_id) }}" class="btn btn-sm btn-info ms-2">
        Review
    </a>
    {% endfor %}
</div>
{% endif %}
```

**Step 3: Commit**

```bash
git add templates/teacher_submissions.html templates/dashboard.html app.py
git commit -m "feat: add bulk submission button and pending validation banner"
```

---

### Task 12: Dependencies — Add PyMuPDF

**Files:**
- Modify: `requirements.txt` (add PyMuPDF)

**Step 1: Add PyMuPDF to requirements**

Add `PyMuPDF` to `requirements.txt`. This is used for extracting individual pages from the uploaded class PDF.

```
PyMuPDF
```

**Step 2: Install locally**

```bash
pip install PyMuPDF
```

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add PyMuPDF dependency for PDF page extraction"
```

---

### Task 13: Manual testing

**Test 1: Upload flow**
1. Go to teacher submissions, select an assignment
2. Click "Bulk submission" button
3. Upload a multi-page PDF with student names visible
4. Verify redirect to review page with processing spinner
5. Wait for processing to complete — verify splits table appears

**Test 2: Review and confirm (no validation)**
1. On the review page, check student assignments are correct
2. Reassign any incorrect splits using dropdowns
3. Click "Confirm & Create Submissions"
4. Verify individual submissions appear in the submissions list
5. Verify AI feedback was generated for each

**Test 3: Review and confirm (with validation)**
1. Upload with "require student validation" toggled on
2. Confirm splits
3. Verify submissions are created with `pending_validation: true`
4. Check student dashboard shows validation banner
5. As student, click review — verify pages and OCR answers appear
6. Edit an answer, click confirm
7. Verify AI marking runs and submission moves to `ai_reviewed`

**Test 4: Force validate**
1. Upload with validation enabled
2. As teacher, force-validate a submission
3. Verify AI marking runs

**Test 5: Edge cases**
1. Upload a PDF where some students can't be detected — verify unmatched pages section
2. Upload with a student missing from PDF — verify "missing students" section
3. Report issue as student — verify flag is set

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Database model + indexes | `models.py`, `utils/auth.py`, `utils/__init__.py` |
| 2 | AI name detection + grouping | `utils/ai_marking.py` |
| 3 | Push notification function | `utils/push_notifications.py` |
| 4 | Upload route + background processing | `app.py` |
| 5 | Review + confirm routes | `app.py` |
| 6 | Student validation routes | `app.py` |
| 7 | Upload template | `templates/teacher_bulk_submission.html` |
| 8 | Review template | `templates/teacher_bulk_review.html` |
| 9 | Student validation template | `templates/student_validate_submission.html` |
| 10 | Supporting APIs | `app.py` |
| 11 | Navigation + dashboard banner | `templates/teacher_submissions.html`, `templates/dashboard.html`, `app.py` |
| 12 | Dependencies | `requirements.txt` |
| 13 | Manual testing | — |
