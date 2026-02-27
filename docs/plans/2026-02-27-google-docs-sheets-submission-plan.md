# Google Docs/Sheets Submission — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let students open assignment files (PDF → Google Docs, Excel → Google Sheets) in Google's editor and submit back for grading through the existing AI marking pipeline.

**Architecture:** The service account uploads template files from GridFS to the teacher's Drive submissions folder with conversion enabled, sets "anyone with link can edit" permissions, and stores the Drive file ID on a draft submission record. On submit, the backend exports the Google Doc/Sheet back to its original format (PDF/xlsx), stores it in GridFS, and feeds it into the existing grading pipeline unchanged.

**Tech Stack:** Flask, Google Drive API v3 (existing `google-api-python-client`), MongoDB/GridFS, Jinja2 templates, vanilla JS.

**Note:** This project has no automated test suite. Testing is manual. Steps reference manual verification instead of unit tests.

---

### Task 1: Add Drive conversion and export methods to `google_drive.py`

**Files:**
- Modify: `utils/google_drive.py:96-350` (DriveManager class)

**Step 1: Add `upload_and_convert` method**

Add after the `upload_content` method (after line 213) in the `DriveManager` class:

```python
def upload_and_convert(self, content_bytes: bytes, filename: str,
                       source_mime_type: str, folder_id: str = None) -> dict:
    """Upload a file to Drive and convert it to Google Docs/Sheets format.

    Args:
        content_bytes: File content
        filename: Display name for the Google Doc/Sheet
        source_mime_type: Original MIME type ('application/pdf' or
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        folder_id: Target folder ID

    Returns:
        dict with 'id' and 'link', or None on failure
    """
    try:
        file_metadata = {
            'name': filename,
            'mimeType': {
                'application/pdf': 'application/vnd.google-apps.document',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'application/vnd.google-apps.spreadsheet',
            }.get(source_mime_type, 'application/vnd.google-apps.document')
        }
        if folder_id or self.folder_id:
            file_metadata['parents'] = [folder_id or self.folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(content_bytes),
            mimetype=source_mime_type,
            resumable=True
        )

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        return {
            'id': file.get('id'),
            'link': file.get('webViewLink')
        }
    except HttpError as e:
        if e.resp.status == 403 and ('storageQuotaExceeded' in str(e) or 'Service Accounts do not have storage quota' in str(e)):
            logger.warning("Google Drive: Service account has no storage quota for upload_and_convert.")
            return None
        logger.error(f"Error in upload_and_convert: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in upload_and_convert: {e}")
        return None
```

**Step 2: Add `set_anyone_with_link_editor` method**

Add immediately after `upload_and_convert`:

```python
def set_anyone_with_link_editor(self, file_id: str) -> bool:
    """Set a file to 'anyone with the link can edit'."""
    try:
        self.service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'writer'},
            supportsAllDrives=True
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error setting permissions on {file_id}: {e}")
        return False
```

**Step 3: Add `export_as_pdf` and `export_as_xlsx` methods**

Add immediately after `set_anyone_with_link_editor`:

```python
def export_as_pdf(self, file_id: str) -> bytes:
    """Export a Google Doc as PDF bytes."""
    try:
        request = self.service.files().export_media(
            fileId=file_id, mimeType='application/pdf'
        )
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        file_content.seek(0)
        return file_content.read()
    except Exception as e:
        logger.error(f"Error exporting {file_id} as PDF: {e}")
        return None

def export_as_xlsx(self, file_id: str) -> bytes:
    """Export a Google Sheet as .xlsx bytes."""
    try:
        request = self.service.files().export_media(
            fileId=file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        file_content.seek(0)
        return file_content.read()
    except Exception as e:
        logger.error(f"Error exporting {file_id} as xlsx: {e}")
        return None
```

**Step 4: Verify manually**

Start a Python shell and confirm the new methods exist:
```bash
python -c "from utils.google_drive import DriveManager; print([m for m in dir(DriveManager) if not m.startswith('_')])"
```
Expected: list includes `upload_and_convert`, `set_anyone_with_link_editor`, `export_as_pdf`, `export_as_xlsx`

**Step 5: Commit**

```bash
git add utils/google_drive.py
git commit -m "feat: add Drive conversion and export methods for Google Docs/Sheets submission"
```

---

### Task 2: Add `POST /api/student/open-in-drive` route

**Files:**
- Modify: `app.py` — add new route near the other student API routes (around line 1284, before `student_submit_files`)

**Step 1: Add the route**

Add before the `@app.route('/student/submit', methods=['POST'])` line (line 1284):

```python
@app.route('/api/student/open-in-drive', methods=['POST'])
@login_required
def open_in_drive():
    """Create a Google Doc/Sheet copy of the assignment template for the student."""
    try:
        data = request.get_json()
        assignment_id = data.get('assignment_id')
        if not assignment_id:
            return jsonify({'success': False, 'error': 'Missing assignment_id'}), 400

        assignment = Assignment.find_one({'assignment_id': assignment_id})
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404

        student = Student.find_one({'student_id': session['student_id']})
        teacher = Teacher.find_one({'teacher_id': assignment['teacher_id']})

        # Check teacher has Drive configured with submissions folder
        submissions_folder_id = assignment.get('drive_folders', {}).get('submissions_folder_id')
        if not teacher or not teacher.get('google_drive_folder_id') or not submissions_folder_id:
            return jsonify({'success': False, 'error': 'Google Drive is not configured for this assignment'}), 400

        # Check if student already has a Drive copy for this assignment
        existing = Submission.find_one({
            'assignment_id': assignment_id,
            'student_id': session['student_id'],
            'google_drive_file_id': {'$exists': True}
        })

        if existing and existing.get('google_drive_url'):
            return jsonify({
                'success': True,
                'url': existing['google_drive_url'],
                'already_exists': True
            })

        # Determine what to upload: spreadsheet template or question paper PDF
        from gridfs import GridFS
        from utils.google_drive import get_teacher_drive_manager

        fs = GridFS(db.db)
        marking_type = assignment.get('marking_type', 'standard')

        if marking_type == 'spreadsheet' and assignment.get('spreadsheet_student_template_id'):
            try:
                template_file = fs.get(assignment['spreadsheet_student_template_id'])
                content_bytes = template_file.read()
            except Exception:
                return jsonify({'success': False, 'error': 'Could not read spreadsheet template'}), 500
            source_mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            drive_type = 'spreadsheet'
        elif assignment.get('question_paper_id'):
            try:
                qp_file = fs.get(assignment['question_paper_id'])
                content_bytes = qp_file.read()
            except Exception:
                return jsonify({'success': False, 'error': 'Could not read question paper'}), 500
            source_mime = 'application/pdf'
            drive_type = 'document'
        else:
            return jsonify({'success': False, 'error': 'No template file available for this assignment'}), 400

        # Upload and convert
        drive_manager = get_teacher_drive_manager(teacher)
        if not drive_manager:
            return jsonify({'success': False, 'error': 'Could not connect to Google Drive'}), 500

        student_name = student.get('name', 'Student') if student else 'Student'
        student_id = session['student_id']
        filename = f"{student_id}_{student_name}_{assignment.get('title', 'Assignment')}"

        result = drive_manager.upload_and_convert(
            content_bytes=content_bytes,
            filename=filename,
            source_mime_type=source_mime,
            folder_id=submissions_folder_id
        )

        if not result:
            return jsonify({'success': False, 'error': 'Failed to create Google Drive copy. The Drive may be full or inaccessible.'}), 500

        # Set anyone-with-link editor permission
        drive_manager.set_anyone_with_link_editor(result['id'])

        # Create or update draft submission record
        if existing:
            Submission.update_one(
                {'submission_id': existing['submission_id']},
                {'$set': {
                    'google_drive_file_id': result['id'],
                    'google_drive_url': result['link'],
                    'google_drive_type': drive_type,
                    'updated_at': datetime.utcnow()
                }}
            )
        else:
            submission_id = generate_submission_id()
            Submission.insert_one({
                'submission_id': submission_id,
                'assignment_id': assignment_id,
                'student_id': session['student_id'],
                'teacher_id': assignment['teacher_id'],
                'status': 'draft',
                'google_drive_file_id': result['id'],
                'google_drive_url': result['link'],
                'google_drive_type': drive_type,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })

        return jsonify({
            'success': True,
            'url': result['link'],
            'already_exists': False
        })

    except Exception as e:
        logger.error(f"Error in open_in_drive: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
```

**Step 2: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('app.py', doraise=True); print('OK')"
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add POST /api/student/open-in-drive route"
```

---

### Task 3: Add `POST /api/student/submit-from-drive` route

**Files:**
- Modify: `app.py` — add immediately after the `open_in_drive` route

**Step 1: Add the route**

```python
@app.route('/api/student/submit-from-drive', methods=['POST'])
@login_required
def submit_from_drive():
    """Export the student's Google Doc/Sheet and submit it for marking."""
    try:
        data = request.get_json()
        assignment_id = data.get('assignment_id')
        if not assignment_id:
            return jsonify({'success': False, 'error': 'Missing assignment_id'}), 400

        assignment = Assignment.find_one({'assignment_id': assignment_id})
        if not assignment:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404

        student = Student.find_one({'student_id': session['student_id']})
        teacher = Teacher.find_one({'teacher_id': assignment['teacher_id']})

        # Find the draft submission with the Drive file
        submission = Submission.find_one({
            'assignment_id': assignment_id,
            'student_id': session['student_id'],
            'google_drive_file_id': {'$exists': True}
        })

        if not submission or not submission.get('google_drive_file_id'):
            return jsonify({'success': False, 'error': 'No Google Drive document found. Please open the assignment in Google Docs/Sheets first.'}), 400

        # Block if already submitted (unless rejected)
        if submission.get('status') in ['submitted', 'ai_reviewed', 'reviewed']:
            return jsonify({'success': False, 'error': 'Already submitted'}), 400

        # Export from Drive
        from utils.google_drive import get_teacher_drive_manager
        drive_manager = get_teacher_drive_manager(teacher)
        if not drive_manager:
            return jsonify({'success': False, 'error': 'Could not connect to Google Drive'}), 500

        drive_type = submission.get('google_drive_type', 'document')
        drive_file_id = submission['google_drive_file_id']

        if drive_type == 'spreadsheet':
            exported_bytes = drive_manager.export_as_xlsx(drive_file_id)
            file_type = 'excel'
            page_type = 'excel'
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            file_ext = 'xlsx'
        else:
            exported_bytes = drive_manager.export_as_pdf(drive_file_id)
            file_type = 'pdf'
            page_type = 'pdf'
            content_type = 'application/pdf'
            file_ext = 'pdf'

        if not exported_bytes:
            return jsonify({'success': False, 'error': 'Failed to export from Google Drive. The document may have been deleted.'}), 500

        # Store in GridFS
        from gridfs import GridFS
        from bson import ObjectId
        fs = GridFS(db.db)

        submission_id = submission['submission_id']

        # Delete old GridFS files if resubmitting
        for old_fid in submission.get('file_ids', []):
            try:
                fs.delete(ObjectId(old_fid))
            except Exception:
                pass

        file_id = fs.put(
            exported_bytes,
            filename=f"{submission_id}_page_1.{file_ext}",
            content_type=content_type,
            submission_id=submission_id,
            page_num=1
        )

        # Update submission to submitted state
        Submission.update_one(
            {'submission_id': submission_id},
            {'$set': {
                'file_ids': [str(file_id)],
                'file_type': file_type,
                'page_count': 1,
                'status': 'submitted',
                'submitted_at': datetime.utcnow(),
                'submitted_via': 'google_drive',
                'updated_at': datetime.utcnow()
            },
            '$unset': {'rejection_reason': '', 'rejected_at': '', 'rejected_by': ''}}
        )

        # Build pages list for the marking pipeline
        pages = [{
            'type': page_type,
            'data': exported_bytes,
            'page_num': 1
        }]

        # Run through existing marking pipeline
        marking_type = assignment.get('marking_type', 'standard')
        ai_result = None

        try:
            if marking_type == 'spreadsheet':
                answer_key_bytes = None
                if assignment.get('spreadsheet_answer_key_id'):
                    try:
                        ans_file = fs.get(assignment['spreadsheet_answer_key_id'])
                        answer_key_bytes = ans_file.read()
                    except Exception as e:
                        logger.warning(f"Could not read spreadsheet answer key: {e}")

                if answer_key_bytes and exported_bytes:
                    from utils.spreadsheet_evaluator import (
                        evaluate_spreadsheet_submission,
                        generate_pdf_report as generate_spreadsheet_pdf,
                        generate_commented_excel,
                    )
                    student_name = student.get('name') or 'Student'
                    result_dict = evaluate_spreadsheet_submission(
                        answer_key_bytes=answer_key_bytes,
                        student_bytes=exported_bytes,
                        student_name=student_name,
                        student_filename=f"{submission_id}.xlsx",
                    )
                    if result_dict:
                        pdf_bytes = generate_spreadsheet_pdf(result_dict)
                        excel_bytes = generate_commented_excel(exported_bytes, result_dict)
                        pdf_id = fs.put(pdf_bytes, filename=f"{submission_id}_feedback_report.pdf",
                                       content_type='application/pdf', submission_id=submission_id,
                                       file_type='spreadsheet_feedback_pdf')
                        excel_id = fs.put(excel_bytes, filename=f"{submission_id}_feedback_commented.xlsx",
                                         content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                         submission_id=submission_id, file_type='spreadsheet_feedback_excel')
                        ai_result = {
                            'spreadsheet_feedback': result_dict,
                            'marks_awarded': result_dict.get('marks_awarded'),
                            'total_marks': result_dict.get('total_marks'),
                            'percentage': result_dict.get('percentage'),
                        }
                        update_fields = {
                            'ai_feedback': ai_result,
                            'status': 'ai_reviewed',
                            'final_marks': result_dict.get('marks_awarded'),
                            'spreadsheet_feedback_pdf_id': str(pdf_id),
                            'spreadsheet_feedback_excel_id': str(excel_id),
                        }
                        if assignment.get('send_ai_feedback_immediately'):
                            update_fields['feedback_sent'] = True
                        Submission.update_one({'submission_id': submission_id}, {'$set': update_fields})
                        if update_fields.get('feedback_sent'):
                            submission_after = Submission.find_one({'submission_id': submission_id})
                            if submission_after:
                                _update_profile_and_mastery_from_assignment(session['student_id'], assignment, submission_after)
                    else:
                        ai_result = {'error': 'Spreadsheet evaluation failed'}
                else:
                    ai_result = {'error': 'Missing answer key or spreadsheet data'}

            elif marking_type == 'rubric':
                from utils.ai_marking import analyze_essay_with_rubrics
                rubrics_content = None
                if assignment.get('rubrics_id'):
                    try:
                        rubrics_file = fs.get(assignment['rubrics_id'])
                        rubrics_content = rubrics_file.read()
                    except Exception:
                        pass
                ai_result = analyze_essay_with_rubrics(pages, assignment, rubrics_content, teacher)
            else:
                from utils.ai_marking import analyze_submission_images
                answer_key_content = None
                if assignment.get('answer_key_id'):
                    try:
                        answer_file = fs.get(assignment['answer_key_id'])
                        answer_key_content = answer_file.read()
                    except Exception:
                        pass
                ai_result = analyze_submission_images(pages, assignment, answer_key_content, teacher)

            # Update with AI result for standard/rubric (spreadsheet already updated above)
            if marking_type in ('standard', 'rubric') and ai_result:
                is_413 = ai_result.get('error_code') == 'request_too_large' or (
                    ai_result.get('error') and ('413' in str(ai_result.get('error')) or 'request_too_large' in str(ai_result.get('error')).lower())
                )
                if is_413:
                    rejection_reason = "Your submission was too large to process. Please try submitting with fewer pages or smaller content."
                    Submission.update_one(
                        {'submission_id': submission_id},
                        {'$set': {'status': 'rejected', 'rejection_reason': rejection_reason,
                                  'rejected_at': datetime.utcnow(), 'rejected_by': 'system_413'}}
                    )
                    return jsonify({'success': True, 'submission_id': submission_id, 'status': 'rejected',
                                    'message': rejection_reason})
                else:
                    update_fields = {
                        'ai_feedback': ai_result,
                        'status': 'ai_reviewed',
                    }
                    if ai_result.get('total_marks') is not None:
                        update_fields['final_marks'] = ai_result.get('total_marks')
                    if assignment.get('send_ai_feedback_immediately'):
                        update_fields['feedback_sent'] = True
                    Submission.update_one({'submission_id': submission_id}, {'$set': update_fields})
                    if update_fields.get('feedback_sent'):
                        submission_after = Submission.find_one({'submission_id': submission_id})
                        if submission_after:
                            _update_profile_and_mastery_from_assignment(session['student_id'], assignment, submission_after)
        except Exception as ai_error:
            logger.error(f"AI marking error for Drive submission {submission_id}: {ai_error}", exc_info=True)
            Submission.update_one({'submission_id': submission_id}, {'$set': {'ai_feedback': {'error': str(ai_error)}}})

        # Send teacher notification
        try:
            from bot_handler import send_new_submission_notification
            send_new_submission_notification(assignment, student, submission_id)
        except Exception:
            pass

        # Upload to Google Drive submissions folder (PDF copy for teacher)
        if teacher.get('google_drive_folder_id') and assignment.get('drive_folders', {}).get('submissions_folder_id'):
            try:
                from utils.google_drive import upload_student_submission
                from utils.pdf_generator import generate_submission_pdf
                submission_pdf = generate_submission_pdf(pages, submission_id)
                if submission_pdf:
                    drive_result = upload_student_submission(
                        teacher=teacher,
                        submissions_folder_id=assignment['drive_folders']['submissions_folder_id'],
                        submission_content=submission_pdf,
                        filename=f"submission_{submission_id}.pdf",
                        student_name=student.get('name') if student else None,
                        student_id=session['student_id']
                    )
                    if drive_result:
                        Submission.update_one({'submission_id': submission_id}, {'$set': {'drive_file': drive_result}})
            except Exception as drive_error:
                logger.warning(f"Could not upload Drive submission PDF: {drive_error}")

        final_submission = Submission.find_one({'submission_id': submission_id})
        return jsonify({
            'success': True,
            'submission_id': submission_id,
            'status': final_submission.get('status', 'submitted') if final_submission else 'submitted'
        })

    except Exception as e:
        logger.error(f"Error in submit_from_drive: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
```

**Step 2: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('app.py', doraise=True); print('OK')"
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add POST /api/student/submit-from-drive route"
```

---

### Task 4: Pass Drive availability to the assignment view template

**Files:**
- Modify: `app.py:711-755` (view_assignment function)

**Step 1: Add Drive flag to template context**

In the `view_assignment` function, before the `return render_template(...)` call at line 750, add logic to check Drive availability and find any existing Drive draft:

Replace lines 748-755 with:

```python
    teacher = Teacher.find_one({'teacher_id': assignment['teacher_id']})

    # Check if Google Drive submission is available for this assignment
    drive_available = bool(
        teacher and
        teacher.get('google_drive_folder_id') and
        assignment.get('drive_folders', {}).get('submissions_folder_id')
    )

    # Check if student already has a Google Drive copy
    drive_submission = None
    if drive_available:
        drive_submission = Submission.find_one({
            'assignment_id': assignment_id,
            'student_id': session['student_id'],
            'google_drive_file_id': {'$exists': True}
        })

    return render_template('assignment_view.html',
                         student=student,
                         assignment=assignment,
                         existing_submission=existing_submission,
                         rejected_submission=rejected_submission,
                         teacher=teacher,
                         drive_available=drive_available,
                         drive_submission=drive_submission)
```

**Step 2: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('app.py', doraise=True); print('OK')"
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: pass drive_available and drive_submission to assignment view template"
```

---

### Task 5: Add Google Docs/Sheets buttons to the assignment view template

**Files:**
- Modify: `templates/assignment_view.html:100-130` (download section) and the JS section at the bottom

**Step 1: Add the Google Drive buttons for spreadsheet assignments**

In `assignment_view.html`, find the spreadsheet download section (lines 101-119). Replace the closing `</div>` and `<p>` text (lines 117-119) to add the Drive buttons:

After line 116 (`{% endif %}`) and before the closing `</div>` of `d-grid gap-2` (which is the div that starts on line 104), add a Drive button inside the button group. Specifically, replace lines 104-119:

```html
                        <div class="d-grid gap-2">
                            {% if assignment.spreadsheet_student_template_id %}
                            <a href="{{ url_for('download_student_assignment_file', assignment_id=assignment.assignment_id, file_type='spreadsheet_student_template') }}"
                               class="btn btn-success" download>
                                <i class="bi bi-download me-1"></i>Download Excel template
                            </a>
                            {% endif %}
                            {% if assignment.question_paper_id %}
                            <a href="{{ url_for('download_student_assignment_file', assignment_id=assignment.assignment_id, file_type='question_paper') }}"
                               class="btn btn-outline-primary" download>
                                <i class="bi bi-file-pdf me-1"></i>Download Question paper (PDF)
                            </a>
                            {% endif %}
                            {% if drive_available and not existing_submission %}
                            <button type="button" class="btn btn-primary" id="btn-open-drive" onclick="openInDrive()">
                                <i class="bi bi-google me-1"></i>
                                {% if drive_submission and drive_submission.google_drive_url %}
                                    Continue in Google Sheets
                                {% else %}
                                    Open in Google Sheets
                                {% endif %}
                            </button>
                            {% endif %}
                        </div>
                        <p class="text-muted small mt-2 mb-0">Complete the Excel template and upload it below, or open in Google Sheets to work online. You will receive a PDF report and a commented Excel file with feedback.</p>
```

**Step 2: Add Google Drive buttons for standard/rubric (PDF) assignments**

Find the question paper section for non-spreadsheet assignments (lines 120-130). Replace lines 120-130 with:

```html
                    {% elif assignment.question_paper_id or assignment.get('drive_file_refs', {}).get('question_paper_drive_id') %}
                    <div class="question-paper-section mt-4">
                        <h6><i class="bi bi-file-pdf me-2"></i>Question Paper</h6>
                        <div class="d-grid gap-2">
                            <a href="{{ url_for('download_student_assignment_file', assignment_id=assignment.assignment_id, file_type='question_paper') }}"
                               class="btn btn-primary" download>
                                <i class="bi bi-download me-1"></i>Download Question Paper
                            </a>
                            {% if drive_available and not existing_submission %}
                            <button type="button" class="btn btn-success" id="btn-open-drive" onclick="openInDrive()">
                                <i class="bi bi-google me-1"></i>
                                {% if drive_submission and drive_submission.google_drive_url %}
                                    Continue in Google Docs
                                {% else %}
                                    Open in Google Docs
                                {% endif %}
                            </button>
                            {% endif %}
                        </div>
                    </div>
                    {% endif %}
```

**Step 3: Add "Submit from Google Drive" button to the submission form**

In the submission form area (around line 293-298, the submit button section), add a Drive submit button. Replace lines 293-298:

```html
                        <!-- Submit Buttons -->
                        <div class="d-grid gap-2 mt-3">
                            <button type="submit" class="btn btn-success btn-lg" id="submit-btn" disabled>
                                <i class="bi bi-send-fill me-1"></i>Submit Assignment
                            </button>
                            {% if drive_available and drive_submission and drive_submission.google_drive_url %}
                            <button type="button" class="btn btn-primary btn-lg" id="submit-drive-btn" onclick="submitFromDrive()">
                                <i class="bi bi-google me-1"></i>Submit from Google {% if assignment.marking_type == 'spreadsheet' %}Sheets{% else %}Docs{% endif %}
                            </button>
                            {% endif %}
                        </div>
```

**Step 4: Commit**

```bash
git add templates/assignment_view.html
git commit -m "feat: add Google Docs/Sheets buttons to assignment view"
```

---

### Task 6: Add JavaScript handlers for the Drive buttons

**Files:**
- Modify: `templates/assignment_view.html` — JS section at the bottom of the file

**Step 1: Add `openInDrive()` and `submitFromDrive()` functions**

Find the `<script>` block in assignment_view.html (around line 1524 where `isSpreadsheetAssignment` is defined). Add the following functions inside the existing script block, near the top after the variable declarations:

```javascript
    // Google Drive integration
    const driveSubmissionUrl = {{ (drive_submission.google_drive_url|tojson) if drive_submission and drive_submission.google_drive_url else 'null' }};

    async function openInDrive() {
        const btn = document.getElementById('btn-open-drive');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Creating your copy...';

        try {
            const response = await fetch('/api/student/open-in-drive', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ assignment_id: '{{ assignment.assignment_id }}' })
            });
            const result = await response.json();

            if (result.success) {
                // Open the Google Doc/Sheet in a new tab
                window.open(result.url, '_blank');

                // Update button to "Continue in..."
                const label = isSpreadsheetAssignment ? 'Continue in Google Sheets' : 'Continue in Google Docs';
                btn.innerHTML = '<i class="bi bi-google me-1"></i>' + label;
                btn.disabled = false;
                btn.onclick = function() { window.open(result.url, '_blank'); };

                // Show the "Submit from Drive" button if not already visible
                const submitDriveBtn = document.getElementById('submit-drive-btn');
                if (!submitDriveBtn) {
                    // Dynamically add the submit button if the page didn't have it on load
                    const submitArea = document.querySelector('#submission-form .d-grid.gap-2.mt-3');
                    if (submitArea) {
                        const newBtn = document.createElement('button');
                        newBtn.type = 'button';
                        newBtn.className = 'btn btn-primary btn-lg';
                        newBtn.id = 'submit-drive-btn';
                        newBtn.onclick = submitFromDrive;
                        const typeLabel = isSpreadsheetAssignment ? 'Sheets' : 'Docs';
                        newBtn.innerHTML = '<i class="bi bi-google me-1"></i>Submit from Google ' + typeLabel;
                        submitArea.appendChild(newBtn);
                    }
                }
            } else {
                alert(result.error || 'Failed to create Google Drive copy.');
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        } catch (err) {
            console.error('Open in Drive error:', err);
            alert('Could not connect to the server. Please try again.');
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }

    async function submitFromDrive() {
        if (!confirm('Submit your work from Google ' + (isSpreadsheetAssignment ? 'Sheets' : 'Docs') + '? Make sure you have saved all your changes.')) {
            return;
        }

        const btn = document.getElementById('submit-drive-btn');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Submitting...';

        // Also disable the regular submit button to prevent double submission
        const regularBtn = document.getElementById('submit-btn');
        if (regularBtn) regularBtn.disabled = true;

        try {
            const response = await fetch('/api/student/submit-from-drive', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ assignment_id: '{{ assignment.assignment_id }}' })
            });
            const result = await response.json();

            if (result.success) {
                // Redirect to submission view
                window.location.href = '/submissions/' + result.submission_id;
            } else {
                alert(result.error || 'Submission failed. Please try again.');
                btn.innerHTML = originalHtml;
                btn.disabled = false;
                if (regularBtn) regularBtn.disabled = false;
            }
        } catch (err) {
            console.error('Submit from Drive error:', err);
            alert('Could not connect to the server. Please try again.');
            btn.innerHTML = originalHtml;
            btn.disabled = false;
            if (regularBtn) regularBtn.disabled = false;
        }
    }
```

**Step 2: Commit**

```bash
git add templates/assignment_view.html
git commit -m "feat: add JS handlers for Google Docs/Sheets open and submit"
```

---

### Task 7: Manual end-to-end testing

**Prerequisites:**
- A teacher account with `google_drive_folder_id` set in the database
- A published assignment with a PDF question paper (for Google Docs flow)
- A published spreadsheet assignment with an Excel template (for Google Sheets flow)
- The service account has editor access to the teacher's Drive folder

**Test 1: Standard/Rubric assignment → Google Docs**
1. Log in as student
2. Navigate to a standard assignment with a PDF question paper
3. Verify "Open in Google Docs" button appears
4. Click it — verify a new tab opens with a Google Doc containing the question paper content
5. Type some answers in the Google Doc
6. Return to the portal — button should now say "Continue in Google Docs"
7. Verify "Submit from Google Docs" button is visible
8. Click "Submit from Google Docs" — confirm the dialog, wait for AI marking
9. Verify redirect to submission view with feedback

**Test 2: Spreadsheet assignment → Google Sheets**
1. Navigate to a spreadsheet assignment
2. Verify "Open in Google Sheets" button appears
3. Click it — verify a Google Sheet opens with the template content
4. Fill in some cells
5. Return to portal, click "Submit from Google Sheets"
6. Verify spreadsheet evaluation runs and feedback PDF is generated

**Test 3: Edge cases**
1. Visit assignment without Drive configured — verify no Drive buttons appear
2. Open the same assignment again — verify "Continue in..." button reuses the same doc
3. Verify the regular file upload still works alongside the Drive buttons

**Step 1: Commit all changes**

```bash
git add -A
git commit -m "feat: complete Google Docs/Sheets submission flow"
```
