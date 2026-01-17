# CURSOR AI - Complete Implementation Instructions

## Overview
You are building a school communication and assignment management system.
This file contains EVERYTHING Cursor AI needs to generate all code files.

## What's Already Done
The following files are complete and provided in this package:
- ✅ models.py (database models)
- ✅ utils/auth.py (authentication + encryption)
- ✅ utils/ai_marking.py (AI feedback service)
- ✅ utils/google_drive.py (Drive integration)
- ✅ utils/pdf_generator.py (PDF generation)
- ✅ utils/notifications.py (notifications)
- ✅ requirements.txt (dependencies)
- ✅ Configuration files (.env.example, Procfile, etc.)

## What Cursor AI Must Generate
1. app.py (main Flask application)
2. bot.py (Telegram bot)
3. bot_handler.py (helper for Flask->Telegram)
4. 14 HTML templates
5. CSS and JavaScript files

---

## STEP 1: Generate bot_handler.py

This file allows Flask to send Telegram messages.

**FULL CODE FOR bot_handler.py:**

```python
import os
import logging
from telegram import Bot
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

def send_to_teacher(telegram_id: int, student_name: str, message: str, teacher_id: str):
    if not bot:
        logger.error("Bot token not configured")
        return False
    
    try:
        formatted_message = f"📱 {student_name}: {message}"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            bot.send_message(chat_id=telegram_id, text=formatted_message)
        )
        loop.close()
        logger.info(f"Sent message from {student_name} to teacher {teacher_id}")
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

def send_notification(telegram_id: int, notification_type: str, data: dict):
    if not bot:
        return False
    
    try:
        if notification_type == 'new_submission':
            web_url = os.getenv('WEB_URL', 'http://localhost:5000')
            message = f"""
📚 New Assignment Submission

Student: {data['student_name']}
Assignment: {data['assignment_title']}
Subject: {data['subject']}
Submitted: {data['submitted_at']}

Review: {web_url}/teacher/submissions/{data['submission_id']}/review
            """
        else:
            message = f"Notification: {notification_type}"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            bot.send_message(chat_id=telegram_id, text=message, parse_mode='Markdown')
        )
        loop.close()
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False
```

Save this as `bot_handler.py` in the root directory.

---

## STEP 2: Review app.py Requirements

**Cursor AI must generate app.py with these routes:**

### Imports Required:
```python
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import os
from datetime import datetime, timedelta
from models import db, Student, Teacher, Message, Class, Assignment, Submission
from utils.auth import hash_password, verify_password, generate_assignment_id, generate_submission_id, encrypt_api_key, decrypt_api_key
from utils.ai_marking import get_teacher_ai_service, mark_submission
from utils.google_drive import get_teacher_drive_manager, upload_assignment_file
from utils.pdf_generator import generate_feedback_pdf
from utils.notifications import notify_submission_ready
import logging
```

### Flask Setup:
```python
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this')
app.config['MONGODB_URI'] = os.getenv('MONGODB_URI')
db.init_app(app)
limiter = Limiter(app=app, key_func=get_remote_address)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

### Decorators:
```python
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher_id' not in session:
            return redirect(url_for('teacher_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated_function
```

### Route Groups:

**1. Authentication (5 routes)**
- `GET/POST /login` - Student login
- `GET /logout`
- `GET/POST /admin/login`
- `GET/POST /teacher/login`
- `GET /teacher/logout`

**2. Student Dashboard & Chat (5 routes)**
- `GET /` - Redirect
- `GET /dashboard` - Show teachers
- `GET /chat/<teacher_id>` - Chat interface
- `POST /api/send_message` - Send message
- `GET /api/poll_messages/<teacher_id>` - Poll messages

**3. Assignments - Student (7 routes)**
- `GET /assignments` - List subjects
- `GET /assignments/subject/<subject>` - Assignments for subject
- `GET /assignments/<id>` - View assignment
- `POST /assignments/<id>/save` - Save draft
- `POST /assignments/<id>/feedback` - Get AI feedback
- `POST /assignments/<id>/submit` - Submit
- `GET /submissions` - Student's submissions
- `GET /submissions/<id>` - View submission

**4. Teacher Routes (10 routes)**
- `GET /teacher/dashboard`
- `GET /teacher/assignments`
- `GET/POST /teacher/assignments/create`
- `GET/POST /teacher/assignments/<id>/edit`
- `POST /teacher/assignments/<id>/delete`
- `GET /teacher/submissions`
- `GET /teacher/submissions/<id>/review`
- `POST /teacher/submissions/<id>/approve`
- `GET/POST /teacher/settings`

**5. Admin Routes (5 routes)**
- `GET /admin/dashboard`
- `POST /admin/import_students`
- `POST /admin/add_teacher`
- `POST /admin/assign_teacher`

**Total: ~35 routes**

**Cursor AI:** Generate complete app.py with all these routes implemented. Use try/except for error handling, return proper JSON for APIs, render templates for HTML pages.

---

## STEP 3: Generate bot.py

**Cursor AI must generate bot.py with:**

### Structure:
```python
import os
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from models import db, Student, Teacher, Message, Submission
from datetime import datetime
import asyncio
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)

# Handler functions
async def start(update, context):
    # Welcome message + show Telegram ID

async def verify_teacher(update, context):
    # /verify <teacher_id>
    # Link Telegram ID to teacher account

async def list_students(update, context):
    # /students
    # Show teacher's students

async def list_submissions(update, context):
    # /submissions
    # Show pending submissions

async def handle_teacher_reply(update, context):
    # Process replies to student messages
    # Extract student name from quoted message
    # Save to database

async def help_command(update, context):
    # Show help

def main():
    # Initialize MongoDB
    # Create application
    # Add handlers
    # Run polling

if __name__ == '__main__':
    main()
```

**Cursor AI:** Generate complete bot.py following this structure.

---

## STEP 4: Generate HTML Templates

**Create 14 templates using Bootstrap 5.**

### base.html (Foundation)
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}School Portal{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    {% block content %}{% endblock %}
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/main.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

### Templates List:
1. login.html - Form with student_id, password
2. dashboard.html - Grid of teacher cards
3. chat.html - Messages + input
4. assignments_list.html - Subjects list
5. assignment_view.html - Questions + answer form
6. submission_view.html - Show feedback
7. teacher_login.html - Teacher login
8. teacher_dashboard.html - Stats + pending list
9. teacher_assignments.html - Created assignments
10. teacher_create_assignment.html - Multi-question form
11. teacher_review.html - Side-by-side review
12. teacher_settings.html - API key form
13. admin_login.html - Admin form
14. admin_dashboard.html - Import/manage

**Cursor AI:** Generate all 14 templates extending from base.html. Use Bootstrap forms, cards, tables.

---

## STEP 5: Generate CSS

**Create static/css/style.css with:**
- Primary color: #667eea
- Card layouts
- Message bubbles
- Responsive design
- Smooth transitions

---

## STEP 6: Generate JavaScript

**Create static/js/main.js with:**
- Message polling function
- Form validation
- API helpers
- Notification display

---

## Testing Procedure

1. Run app.py and bot.py locally
2. Login as student (S001/student123)
3. Send message to teacher
4. Teacher replies in Telegram
5. Student sees reply
6. Student views assignments
7. Complete workflow test

---

## Database Schema Quick Reference

**Students:** student_id, name, class, password_hash, teachers[]  
**Teachers:** teacher_id, name, telegram_id, subjects[], classes[], anthropic_api_key, google_drive_folder_id  
**Messages:** student_id, teacher_id, message, from_student, timestamp, read  
**Assignments:** assignment_id, teacher_id, subject, title, questions[], total_marks  
**Submissions:** submission_id, assignment_id, student_id, answers{}, status, ai_feedback{}, teacher_review{}

---

## Environment Variables

```
MONGODB_URI=mongodb+srv://...
TELEGRAM_BOT_TOKEN=123456:ABC...
FLASK_SECRET_KEY=64_char_hex
ADMIN_PASSWORD=your_password
ENCRYPTION_KEY=fernet_key
ANTHROPIC_API_KEY=sk-ant-...
WEB_URL=https://your-app.up.railway.app
```

---

## Success Checklist

- [ ] All routes return 200
- [ ] Student can login
- [ ] Messages send/receive
- [ ] Assignments visible
- [ ] AI feedback works
- [ ] Teacher review works
- [ ] No console errors
- [ ] Mobile responsive
- [ ] Ready for Railway

---

**CURSOR AI: Generate all files now. Start with bot_handler.py, then app.py, then bot.py, then all templates, then CSS/JS. Use the complete utility files already provided in utils/. Follow Bootstrap 5 conventions. Include error handling. Make it production-ready.**
