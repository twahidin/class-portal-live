# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

School communication and AI-powered learning portal built with Flask. Handles student-teacher messaging (via Telegram bot integration), AI-driven assignment marking with Claude/OpenAI/Gemini, hierarchical learning modules with mastery tracking, real-time collaborative spaces (Socket.IO), and textbook RAG-based AI tutoring.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run Flask app (development)
python app.py

# Run Telegram bot (separate process)
python bot.py

# Production (Railway)
gunicorn -w 1 --threads 100 --timeout 300 --bind 0.0.0.0:$PORT app:app
```

Flask-SocketIO requires 1 worker with threading async mode (not gthread). The 300s timeout accommodates long PDF/textbook processing.

## Required Environment Variables

- `MONGODB_URI` or `MONGO_URL` - MongoDB connection string
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `FLASK_SECRET_KEY` - 64-char hex secret for sessions
- `ADMIN_PASSWORD` - Admin login password
- `ENCRYPTION_KEY` - Fernet key for API key encryption
- `WEB_URL` - Public URL (e.g., `https://app.up.railway.app`)
- `ANTHROPIC_API_KEY` - Claude API key (global default; teachers can set per-teacher keys)

## Architecture

### Monolithic Flask App (`app.py` ~11K lines, 184 routes)

All routes live in `app.py`. There is no blueprint separation. Routes are organized by section comments:

- **Authentication routes** - `/login`, `/logout`, `/admin/login`
- **Student routes** - `/dashboard`, `/chat/<teacher_id>`, `/assignments/*`, `/submissions/*`, `/modules/*`
- **Teacher routes** - `/teacher/dashboard`, `/teacher/assignments/*`, `/teacher/submissions/*/review`, `/teacher/settings`
- **Admin routes** - `/admin/dashboard`, `/admin/import_students`, `/admin/add_teacher`
- **API routes** - `/api/send_message`, `/api/poll_messages/*`, `/api/student/question-help`, `/api/python/execute`
- **Socket.IO events** - `join_space`, `node_added`, `node_deleted`, `cursor_move`, etc.

### Auth Decorators

Three decorators defined at the top of `app.py`:
- `@login_required` - Requires student session (`session['student_id']`)
- `@teacher_required` - Requires teacher session (`session['teacher_id']`)
- `@admin_required` - Requires admin session (`session['is_admin']`)

All return JSON 401 for API/fetch requests instead of redirecting to login page.

### Database (`models.py` - MongoDB via PyMongo)

`Database` class with singleton `db` instance. `db.init_app(app)` called at startup. Auto-creates indexes. Key collections:

- `students`, `teachers`, `classes`, `teaching_groups`
- `assignments`, `submissions` (with AI feedback JSON)
- `messages` (student-teacher chat)
- `modules`, `module_resources`, `module_textbooks` (hierarchical learning tree)
- `student_module_mastery`, `student_learning_profiles`, `learning_sessions`
- `collab_spaces`, `interactives`

Models are lightweight wrappers (not an ORM) - most routes query `db.db.<collection>` directly.

### Utility Modules (`utils/`)

- **`ai_marking.py`** (~2K lines) - AI feedback generation, multi-provider support (Claude/OpenAI/Gemini), vision for handwritten submissions, rubric-based marking. Entry point: `mark_submission()`, provider resolution: `get_teacher_ai_service()`
- **`pdf_generator.py`** (~1.6K lines) - ReportLab-based PDF generation for feedback reports
- **`rag_service.py`** - Textbook RAG using Pinecone or PgVector for embeddings
- **`module_ai.py`** - Syllabus-to-module-tree generation, assessment generation
- **`agno_learning_agent.py`** - Agno framework agent for AI tutoring with RAG context
- **`excel_evaluator.py`** / **`spreadsheet_evaluator.py`** - Spreadsheet submission evaluation
- **`auth.py`** - Password hashing, Fernet encryption for teacher API keys
- **`google_drive.py`** - Google Drive integration for file uploads
- **`notifications.py`** / **`push_notifications.py`** - Telegram and web push notifications

### Frontend

- **Templates**: 48 Jinja2 templates in `templates/`, partials in `templates/partials/`
- **Static**: `static/css/style.css`, `static/js/main.js`, `static/js/drawing-canvas.js`
- **PWA**: `static/service-worker.js` + `static/manifest.json`
- **Jinja2 filter**: `|sgt` converts UTC datetimes to Singapore Time (UTC+8)

### Telegram Bot (`bot.py`)

Separate async service using `python-telegram-bot`. Communicates with the Flask app's MongoDB directly. `bot_handler.py` bridges Flask-to-Telegram for sending notifications from route handlers.

## Key Workflows

### Assignment Marking Flow
1. Teacher creates assignment with question paper, answer key, rubrics
2. Student submits (images/PDF/spreadsheet)
3. `mark_submission()` in `ai_marking.py` sends to AI provider (uses vision for images, text extraction for PDFs)
4. AI returns structured JSON feedback
5. Teacher reviews/edits, then approves
6. Student views feedback + downloadable PDF
7. If assignment is linked to a module, mastery scores update

### AI Provider Resolution
Teachers can configure their own API keys in `/teacher/settings`. `get_teacher_ai_service()` checks the teacher's stored (encrypted) key first, falls back to global `ANTHROPIC_API_KEY`.

## Deployment

Railway with Nixpacks. Auto-deploys from `main` branch. See `DEPLOYMENT.md` for full Railway setup guide. The Telegram bot runs as a separate Railway service.

## Codebase Conventions

- API endpoints return `{'success': bool, 'error': str, 'data': obj}`
- Images resized to 1200px max before sending to AI (see `resize_image_for_ai()`)
- Rate limiting: 200/day, 50/hour per IP (configurable via `RATELIMIT_STORAGE_URI`)
- Sessions expire after 8 hours
- All datetimes stored as UTC in MongoDB, converted to SGT (UTC+8) in templates via `|sgt` filter
- No automated test suite exists - testing is manual
