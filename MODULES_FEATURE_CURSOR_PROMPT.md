# CURSOR AI - My Modules Feature Implementation Guide

## Overview
This document provides complete implementation instructions for adding a **"My Modules"** feature to the existing School Portal. This feature enables:
1. **Teachers** to create hierarchical learning modules from syllabi/schemes of work
2. **Students** to navigate 3D module visualizations and learn interactively
3. **AI-powered** automatic module generation and mastery tracking
4. **Real-time mastery scoring** that propagates from leaf nodes to the center module

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MY MODULES SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TEACHER VIEW                        STUDENT VIEW                   │
│  ┌─────────────────┐                ┌─────────────────┐            │
│  │ Upload Syllabus │                │ 3D Module Space │            │
│  │ (PDF/Word)      │                │ (Three.js)      │            │
│  └────────┬────────┘                └────────┬────────┘            │
│           │                                  │                      │
│           ▼                                  ▼                      │
│  ┌─────────────────┐                ┌─────────────────┐            │
│  │ AI Module Gen   │                │ Click Module    │            │
│  │ (Claude Opus)   │                │ to Learn        │            │
│  └────────┬────────┘                └────────┬────────┘            │
│           │                                  │                      │
│           ▼                                  ▼                      │
│  ┌─────────────────┐                ┌─────────────────┐            │
│  │ 3D Editor View  │                │ Learning Page   │            │
│  │ Add Resources   │                │ - Chat AI       │            │
│  │ - YouTube       │                │ - Writing Board │            │
│  │ - PDFs          │                │ - Resources     │            │
│  │ - Interactive   │                │ - Progress      │            │
│  └────────┬────────┘                └────────┬────────┘            │
│           │                                  │                      │
│           ▼                                  ▼                      │
│  ┌─────────────────┐                ┌─────────────────┐            │
│  │ Class Mastery   │◄───────────────│ Student Mastery │            │
│  │ Dashboard       │                │ Profile (AI)    │            │
│  └─────────────────┘                └─────────────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Models (Add to models.py)

### New Collections

```python
# Add these new model classes to models.py

class Module:
    """
    Represents a learning module node in the hierarchical structure.
    The center module is the "year module" (parent_id = None).
    """
    @staticmethod
    def find_one(query):
        return db.db.modules.find_one(query)

    @staticmethod
    def find(query):
        return db.db.modules.find(query)

    @staticmethod
    def insert_one(document):
        return db.db.modules.insert_one(document).inserted_id

    @staticmethod
    def update_one(query, update):
        return db.db.modules.update_one(query, update)

    @staticmethod
    def delete_one(query):
        return db.db.modules.delete_one(query)

    @staticmethod
    def delete_many(query):
        return db.db.modules.delete_many(query)

    @staticmethod
    def count(query):
        return db.db.modules.count_documents(query)

    @staticmethod
    def aggregate(pipeline):
        return db.db.modules.aggregate(pipeline)


class ModuleResource:
    """Resources attached to leaf modules (YouTube, PDF, interactive, etc.)"""
    @staticmethod
    def find_one(query):
        return db.db.module_resources.find_one(query)

    @staticmethod
    def find(query):
        return db.db.module_resources.find(query)

    @staticmethod
    def insert_one(document):
        return db.db.module_resources.insert_one(document).inserted_id

    @staticmethod
    def update_one(query, update):
        return db.db.module_resources.update_one(query, update)

    @staticmethod
    def delete_one(query):
        return db.db.module_resources.delete_one(query)

    @staticmethod
    def delete_many(query):
        return db.db.module_resources.delete_many(query)


class StudentModuleMastery:
    """
    Tracks individual student's mastery of each module.
    Mastery score: 0-100 percentage
    """
    @staticmethod
    def find_one(query):
        return db.db.student_module_mastery.find_one(query)

    @staticmethod
    def find(query):
        return db.db.student_module_mastery.find(query)

    @staticmethod
    def insert_one(document):
        return db.db.student_module_mastery.insert_one(document).inserted_id

    @staticmethod
    def update_one(query, update, upsert=False):
        return db.db.student_module_mastery.update_one(query, update, upsert=upsert)

    @staticmethod
    def delete_many(query):
        return db.db.student_module_mastery.delete_many(query)

    @staticmethod
    def aggregate(pipeline):
        return db.db.student_module_mastery.aggregate(pipeline)


class StudentLearningProfile:
    """
    AI-built profile tracking student's learning patterns, strengths, weaknesses.
    Updated by the learning chat agent after each interaction.
    """
    @staticmethod
    def find_one(query):
        return db.db.student_learning_profiles.find_one(query)

    @staticmethod
    def find(query):
        return db.db.student_learning_profiles.find(query)

    @staticmethod
    def insert_one(document):
        return db.db.student_learning_profiles.insert_one(document).inserted_id

    @staticmethod
    def update_one(query, update, upsert=False):
        return db.db.student_learning_profiles.update_one(query, update, upsert=upsert)


class LearningSession:
    """
    Records each learning session - chat history, assessments, time spent.
    """
    @staticmethod
    def find_one(query):
        return db.db.learning_sessions.find_one(query)

    @staticmethod
    def find(query):
        return db.db.learning_sessions.find(query)

    @staticmethod
    def insert_one(document):
        return db.db.learning_sessions.insert_one(document).inserted_id

    @staticmethod
    def update_one(query, update):
        return db.db.learning_sessions.update_one(query, update)
```

### Document Schemas

```javascript
// Module Document Schema
{
    "_id": ObjectId,
    "module_id": "MOD-XXXX",           // Unique identifier
    "teacher_id": "T001",               // Owner teacher
    "subject": "Mathematics",
    "year_level": "Secondary 3",
    "title": "Algebra & Functions",     // Module name
    "description": "...",
    "parent_id": null,                  // null = root/center module
    "children_ids": ["MOD-0002", ...],  // Child module IDs
    "depth": 0,                         // 0 = center, 1 = first ring, etc.
    "is_leaf": false,                   // true = can have resources
    "position": {                       // 3D coordinates for visualization
        "x": 0,
        "y": 0,
        "z": 0,
        "angle": 0,                     // Angle from parent (radians)
        "distance": 0                   // Distance from parent
    },
    "color": "#667eea",                 // Module color in 3D view
    "icon": "bi-calculator",            // Bootstrap icon
    "learning_objectives": [...],       // AI-generated objectives
    "prerequisites": ["MOD-0001"],      // Required modules before this
    "estimated_hours": 5,
    "created_at": ISODate,
    "updated_at": ISODate,
    "status": "published"               // draft/published
}

// Module Resource Schema
{
    "_id": ObjectId,
    "resource_id": "RES-XXXX",
    "module_id": "MOD-0005",
    "teacher_id": "T001",
    "type": "youtube",                  // youtube/pdf/interactive/document/link
    "title": "Introduction to Quadratics",
    "url": "https://youtube.com/...",
    "content": null,                    // For uploaded files (base64 or GridFS ref)
    "description": "...",
    "order": 1,                         // Display order
    "duration_minutes": 15,
    "created_at": ISODate
}

// Student Module Mastery Schema
{
    "_id": ObjectId,
    "student_id": "S001",
    "module_id": "MOD-0005",
    "mastery_score": 85,                // 0-100
    "status": "in_progress",            // not_started/in_progress/mastered
    "time_spent_minutes": 45,
    "assessments_completed": 3,
    "assessments_passed": 2,
    "last_activity": ISODate,
    "created_at": ISODate,
    "updated_at": ISODate
}

// Student Learning Profile Schema (AI-maintained)
{
    "_id": ObjectId,
    "student_id": "S001",
    "subject": "Mathematics",
    "strengths": [
        {"topic": "Linear Equations", "confidence": 0.9},
        {"topic": "Algebra", "confidence": 0.85}
    ],
    "weaknesses": [
        {"topic": "Quadratic Factorization", "confidence": 0.4, "notes": "Struggles with negative coefficients"}
    ],
    "learning_style": "visual",         // AI-detected
    "preferred_pace": "moderate",
    "common_mistakes": [
        {"pattern": "Sign errors in expansion", "frequency": 5}
    ],
    "recommendations": [
        "Practice factorization with negative numbers",
        "Use visual aids for quadratic graphs"
    ],
    "total_sessions": 15,
    "total_time_minutes": 450,
    "last_updated": ISODate
}

// Learning Session Schema
{
    "_id": ObjectId,
    "session_id": "SES-XXXX",
    "student_id": "S001",
    "module_id": "MOD-0005",
    "started_at": ISODate,
    "ended_at": ISODate,
    "chat_history": [
        {"role": "student", "content": "...", "timestamp": ISODate},
        {"role": "assistant", "content": "...", "timestamp": ISODate}
    ],
    "assessments": [
        {
            "question": "...",
            "student_answer": "...",
            "is_correct": true,
            "feedback": "...",
            "timestamp": ISODate
        }
    ],
    "writing_submissions": [
        {
            "image_data": "base64...",
            "ai_analysis": "...",
            "timestamp": ISODate
        }
    ],
    "resources_viewed": ["RES-0001", "RES-0002"],
    "mastery_before": 60,
    "mastery_after": 75
}
```

### Add Indexes (in models.py _create_indexes)

```python
def _create_indexes(self):
    # ... existing indexes ...

    # Module indexes
    self.db.modules.create_index('module_id', unique=True)
    self.db.modules.create_index('teacher_id')
    self.db.modules.create_index('parent_id')
    self.db.modules.create_index([('teacher_id', 1), ('subject', 1)])

    # Resource indexes
    self.db.module_resources.create_index('resource_id', unique=True)
    self.db.module_resources.create_index('module_id')

    # Mastery indexes
    self.db.student_module_mastery.create_index([('student_id', 1), ('module_id', 1)], unique=True)
    self.db.student_module_mastery.create_index('module_id')

    # Profile indexes
    self.db.student_learning_profiles.create_index([('student_id', 1), ('subject', 1)], unique=True)

    # Session indexes
    self.db.learning_sessions.create_index('session_id', unique=True)
    self.db.learning_sessions.create_index([('student_id', 1), ('module_id', 1)])
    self.db.learning_sessions.create_index('started_at')
```

---

## New Utility File: utils/module_ai.py

Create this file for AI-powered module generation and learning assessment.

```python
"""
AI-powered module generation and learning assessment utilities.
Uses Anthropic Claude API for:
1. Generating module structure from syllabus documents
2. Assessing student mastery through chat
3. Building student learning profiles
"""

import os
import logging
import base64
import json
import re
from anthropic import Anthropic
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

def get_claude_client():
    """Get Anthropic client"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    return Anthropic(api_key=api_key)

def generate_modules_from_syllabus(
    file_content: bytes,
    file_type: str,
    subject: str,
    year_level: str,
    teacher_id: str
) -> Dict[str, Any]:
    """
    Generate hierarchical module structure from uploaded syllabus/scheme of work.

    Args:
        file_content: PDF or Word document bytes
        file_type: 'pdf' or 'docx'
        subject: Subject name
        year_level: e.g., "Secondary 3"
        teacher_id: Owner teacher ID

    Returns:
        Dictionary with module tree structure
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    try:
        content = []

        # Add document for vision analysis
        file_b64 = base64.standard_b64encode(file_content).decode('utf-8')

        if file_type == 'pdf':
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": file_b64
                }
            })
        else:
            # For Word docs, we'd need to convert - simplified here
            content.append({
                "type": "text",
                "text": f"[Document content for {subject}]"
            })

        system_prompt = f"""You are an expert curriculum designer. Analyze this syllabus/scheme of work and create a hierarchical module structure for {subject} ({year_level}).

STRUCTURE RULES:
1. The ROOT module represents the entire year/course
2. First level children are major topics/units (e.g., "Algebra", "Geometry")
3. Second level are sub-topics (e.g., "Linear Equations", "Quadratic Equations")
4. Third level (leaves) are specific learning objectives that can be assessed
5. Maximum depth: 4 levels (root + 3 levels)
6. Each leaf module should be learnable in 1-2 hours
7. Include estimated hours for each module
8. Generate learning objectives for each module

VISUALIZATION:
- Assign colors that group related topics
- Calculate positions for 3D radial layout (parent at center, children around it)

Respond ONLY with valid JSON:
{{
    "root": {{
        "title": "Mathematics Year 3",
        "description": "Complete mathematics curriculum for Secondary 3",
        "estimated_hours": 150,
        "color": "#667eea",
        "children": [
            {{
                "title": "Algebra",
                "description": "...",
                "estimated_hours": 40,
                "color": "#764ba2",
                "learning_objectives": ["Understand algebraic expressions", "..."],
                "children": [
                    {{
                        "title": "Linear Equations",
                        "description": "...",
                        "estimated_hours": 10,
                        "color": "#8b5cf6",
                        "learning_objectives": ["..."],
                        "children": [
                            {{
                                "title": "Solving One-Variable Equations",
                                "description": "...",
                                "estimated_hours": 2,
                                "color": "#a78bfa",
                                "learning_objectives": ["..."],
                                "is_leaf": true
                            }}
                        ]
                    }}
                ]
            }}
        ]
    }},
    "total_modules": 25,
    "total_hours": 150
}}"""

        content.append({
            "type": "text",
            "text": f"""
Subject: {subject}
Year Level: {year_level}

Analyze this document and create a comprehensive module hierarchy.
Ensure all topics from the syllabus are covered.
Respond with JSON:"""
        })

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": content}]
        )

        response_text = message.content[0].text

        # Parse JSON
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())

        return {'error': 'Could not parse module structure'}

    except Exception as e:
        logger.error(f"Error generating modules: {e}")
        return {'error': str(e)}


def assess_student_understanding(
    student_message: str,
    module: Dict,
    chat_history: List[Dict],
    student_profile: Optional[Dict] = None,
    writing_image: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    AI learning agent that assesses student understanding and provides teaching.

    Args:
        student_message: Student's chat message or question
        module: Current module being studied
        chat_history: Previous messages in this session
        student_profile: Student's learning profile (strengths/weaknesses)
        writing_image: Optional image of student's handwritten work

    Returns:
        Dictionary with response, assessment, and profile updates
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    try:
        # Build context
        profile_context = ""
        if student_profile:
            strengths = ", ".join([s['topic'] for s in student_profile.get('strengths', [])])
            weaknesses = ", ".join([w['topic'] for w in student_profile.get('weaknesses', [])])
            profile_context = f"""
STUDENT PROFILE:
- Strengths: {strengths or 'Not yet identified'}
- Areas needing work: {weaknesses or 'Not yet identified'}
- Learning style: {student_profile.get('learning_style', 'Unknown')}
- Common mistakes: {', '.join([m['pattern'] for m in student_profile.get('common_mistakes', [])])}
"""

        system_prompt = f"""You are an expert, patient tutor helping a student learn.

CURRENT MODULE: {module.get('title', 'Unknown')}
LEARNING OBJECTIVES: {', '.join(module.get('learning_objectives', []))}
{profile_context}

YOUR ROLE:
1. TEACH: Explain concepts clearly, use examples, adapt to student's level
2. ASSESS: Ask questions to check understanding, identify misconceptions
3. ENCOURAGE: Be supportive, celebrate progress, build confidence
4. ADAPT: Use the student's learning profile to personalize teaching

ASSESSMENT GUIDELINES:
- After teaching a concept, ask a question to assess understanding
- If student answers correctly: Award mastery points, move to next concept
- If student struggles: Provide hints, break down the problem, try different explanations
- Note any patterns in mistakes for profile updates

RESPONSE FORMAT - Respond with JSON:
{{
    "response": "Your teaching response to the student (use markdown for formatting, include examples)",
    "response_type": "teaching" or "assessment" or "feedback" or "encouragement",
    "assessment": {{
        "question_asked": "The assessment question if any",
        "student_answer_correct": true/false/null,
        "mastery_change": 0 to 10 (points to add) or -5 to 0 (points to subtract for mistakes),
        "concept_assessed": "Specific concept tested"
    }},
    "profile_updates": {{
        "new_strength": null or {{"topic": "...", "confidence": 0.8}},
        "new_weakness": null or {{"topic": "...", "confidence": 0.3, "notes": "..."}},
        "new_mistake_pattern": null or "Description of mistake pattern"
    }},
    "next_action": "continue_teaching" or "assess_understanding" or "review_previous" or "module_complete",
    "interactive_element": null or {{
        "type": "quiz" or "diagram" or "video",
        "content": "..."
    }}
}}"""

        # Build messages
        messages_content = []

        # Add chat history context
        if chat_history:
            history_text = "\n".join([
                f"{'Student' if m['role'] == 'student' else 'Tutor'}: {m['content']}"
                for m in chat_history[-10:]  # Last 10 messages
            ])
            messages_content.append({
                "type": "text",
                "text": f"RECENT CONVERSATION:\n{history_text}\n\n"
            })

        # Add writing image if provided
        if writing_image:
            image_b64 = base64.standard_b64encode(writing_image).decode('utf-8')
            messages_content.append({
                "type": "text",
                "text": "STUDENT'S HANDWRITTEN WORK:"
            })
            messages_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64
                }
            })

        # Add current message
        messages_content.append({
            "type": "text",
            "text": f"STUDENT'S MESSAGE: {student_message}\n\nRespond with JSON:"
        })

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": messages_content}]
        )

        response_text = message.content[0].text

        # Parse JSON
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            result['raw_response'] = response_text
            return result

        return {
            'response': response_text,
            'response_type': 'teaching',
            'assessment': None,
            'profile_updates': None
        }

    except Exception as e:
        logger.error(f"Error in learning assessment: {e}")
        return {
            'error': str(e),
            'response': "I'm having trouble right now. Let's try again!"
        }


def generate_interactive_assessment(
    module: Dict,
    difficulty: str = "medium",
    question_type: str = "mixed"
) -> Dict[str, Any]:
    """
    Generate an interactive assessment for a module.

    Args:
        module: Module to assess
        difficulty: easy/medium/hard
        question_type: mcq/short_answer/problem/mixed

    Returns:
        Assessment questions and answers
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    try:
        system_prompt = f"""Generate an interactive assessment for this learning module.

MODULE: {module.get('title')}
OBJECTIVES: {', '.join(module.get('learning_objectives', []))}
DIFFICULTY: {difficulty}
QUESTION TYPE: {question_type}

Create 5 questions that test understanding of the learning objectives.

Respond with JSON:
{{
    "questions": [
        {{
            "id": 1,
            "type": "mcq",
            "question": "...",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "correct_answer": "B",
            "explanation": "Why B is correct...",
            "hints": ["Hint 1", "Hint 2"],
            "points": 10
        }},
        {{
            "id": 2,
            "type": "short_answer",
            "question": "...",
            "correct_answer": "...",
            "acceptable_answers": ["...", "..."],
            "explanation": "...",
            "points": 15
        }}
    ],
    "total_points": 50,
    "passing_score": 35,
    "time_limit_minutes": 15
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": "Generate the assessment now."}]
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())

        return {'error': 'Could not generate assessment'}

    except Exception as e:
        logger.error(f"Error generating assessment: {e}")
        return {'error': str(e)}


def analyze_writing_submission(
    image_data: bytes,
    module: Dict,
    expected_content: str = None
) -> Dict[str, Any]:
    """
    Analyze student's handwritten work (equations, diagrams, workings).

    Args:
        image_data: Image bytes of handwritten work
        module: Current module context
        expected_content: What the student was asked to show

    Returns:
        Analysis of the work
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    try:
        image_b64 = base64.standard_b64encode(image_data).decode('utf-8')

        system_prompt = f"""Analyze this student's handwritten work for the module: {module.get('title')}

{'Expected content: ' + expected_content if expected_content else ''}

Evaluate:
1. Mathematical/logical correctness
2. Clarity of presentation
3. Method and approach used
4. Any errors or misconceptions

Respond with JSON:
{{
    "transcription": "Text version of what's written",
    "analysis": "Detailed analysis of the work",
    "is_correct": true/false/partial,
    "errors": ["List of specific errors if any"],
    "suggestions": ["How to improve"],
    "mastery_indication": 0-100
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64
                        }
                    },
                    {
                        "type": "text",
                        "text": "Analyze this handwritten work and respond with JSON:"
                    }
                ]
            }]
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())

        return {'analysis': response_text}

    except Exception as e:
        logger.error(f"Error analyzing writing: {e}")
        return {'error': str(e)}
```

---

## Flask Routes (Add to app.py)

### Teacher Routes

```python
# ============================================================================
# MY MODULES - TEACHER ROUTES
# ============================================================================

from utils.module_ai import (
    generate_modules_from_syllabus,
    generate_interactive_assessment
)
import uuid

def generate_module_id():
    return f"MOD-{uuid.uuid4().hex[:8].upper()}"

def generate_resource_id():
    return f"RES-{uuid.uuid4().hex[:8].upper()}"

def generate_session_id():
    return f"SES-{uuid.uuid4().hex[:8].upper()}"


@app.route('/teacher/modules')
@teacher_required
def teacher_modules():
    """List all module trees created by this teacher"""
    # Get root modules (parent_id is None)
    root_modules = list(Module.find({
        'teacher_id': session['teacher_id'],
        'parent_id': None
    }).sort('created_at', -1))

    # Get statistics for each root module
    for module in root_modules:
        # Count total modules in tree
        module['total_modules'] = Module.count({
            'teacher_id': session['teacher_id'],
            '$or': [
                {'module_id': module['module_id']},
                {'parent_id': {'$regex': f"^{module['module_id']}"}}
            ]
        })

        # Get class mastery average (if assigned to classes)
        # ... aggregation logic

    return render_template('teacher_modules.html',
                         modules=root_modules,
                         teacher=Teacher.find_one({'teacher_id': session['teacher_id']}))


@app.route('/teacher/modules/create', methods=['GET', 'POST'])
@teacher_required
def create_module():
    """Create new module tree from syllabus upload"""
    if request.method == 'POST':
        try:
            subject = request.form.get('subject')
            year_level = request.form.get('year_level')
            file = request.files.get('syllabus_file')

            if not file or not subject:
                return jsonify({'error': 'Missing required fields'}), 400

            # Read file
            file_content = file.read()
            file_type = 'pdf' if file.filename.lower().endswith('.pdf') else 'docx'

            # Generate modules using AI
            result = generate_modules_from_syllabus(
                file_content=file_content,
                file_type=file_type,
                subject=subject,
                year_level=year_level,
                teacher_id=session['teacher_id']
            )

            if 'error' in result:
                return jsonify({'error': result['error']}), 500

            # Save module tree to database
            root_module_id = save_module_tree(
                result['root'],
                session['teacher_id'],
                subject,
                year_level
            )

            return jsonify({
                'success': True,
                'module_id': root_module_id,
                'total_modules': result.get('total_modules', 0)
            })

        except Exception as e:
            logger.error(f"Error creating module: {e}")
            return jsonify({'error': str(e)}), 500

    # GET - show upload form
    teacher = Teacher.find_one({'teacher_id': session['teacher_id']})
    return render_template('teacher_create_module.html', teacher=teacher)


def save_module_tree(node: dict, teacher_id: str, subject: str, year_level: str,
                     parent_id: str = None, depth: int = 0) -> str:
    """Recursively save module tree to database"""
    module_id = generate_module_id()

    children = node.pop('children', [])
    is_leaf = len(children) == 0

    # Calculate 3D position
    position = calculate_module_position(depth, len(children), parent_id)

    module_doc = {
        'module_id': module_id,
        'teacher_id': teacher_id,
        'subject': subject,
        'year_level': year_level,
        'title': node.get('title', 'Untitled'),
        'description': node.get('description', ''),
        'parent_id': parent_id,
        'children_ids': [],
        'depth': depth,
        'is_leaf': is_leaf,
        'position': position,
        'color': node.get('color', '#667eea'),
        'icon': node.get('icon', 'bi-book'),
        'learning_objectives': node.get('learning_objectives', []),
        'estimated_hours': node.get('estimated_hours', 0),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
        'status': 'draft'
    }

    Module.insert_one(module_doc)

    # Save children recursively
    children_ids = []
    for i, child in enumerate(children):
        child_id = save_module_tree(
            child, teacher_id, subject, year_level,
            parent_id=module_id, depth=depth + 1
        )
        children_ids.append(child_id)

    # Update parent with children IDs
    if children_ids:
        Module.update_one(
            {'module_id': module_id},
            {'$set': {'children_ids': children_ids}}
        )

    return module_id


def calculate_module_position(depth: int, sibling_count: int, parent_id: str) -> dict:
    """Calculate 3D position for module visualization"""
    import math

    if depth == 0:
        # Root at center
        return {'x': 0, 'y': 0, 'z': 0, 'angle': 0, 'distance': 0}

    # Get parent position
    parent = Module.find_one({'module_id': parent_id}) if parent_id else None
    parent_pos = parent.get('position', {'x': 0, 'y': 0, 'z': 0}) if parent else {'x': 0, 'y': 0, 'z': 0}

    # Calculate radial position
    base_distance = 100 * depth  # Distance increases with depth
    angle_offset = 2 * math.pi / max(sibling_count, 1)

    return {
        'x': parent_pos['x'],
        'y': depth * 30,  # Slight vertical offset per level
        'z': parent_pos['z'],
        'angle': 0,  # Will be updated when siblings are positioned
        'distance': base_distance
    }


@app.route('/teacher/modules/<module_id>')
@teacher_required
def view_module(module_id):
    """View and edit module tree in 3D space"""
    root_module = Module.find_one({
        'module_id': module_id,
        'teacher_id': session['teacher_id']
    })

    if not root_module:
        return redirect(url_for('teacher_modules'))

    # Get full module tree
    all_modules = list(Module.find({
        'teacher_id': session['teacher_id'],
        '$or': [
            {'module_id': module_id},
            {'parent_id': module_id}
        ]
    }))

    # Build tree structure for Three.js
    def build_tree(m):
        m['children'] = [
            build_tree(Module.find_one({'module_id': cid}))
            for cid in m.get('children_ids', [])
            if Module.find_one({'module_id': cid})
        ]
        return m

    module_tree = build_tree(root_module.copy())

    return render_template('teacher_module_view.html',
                         module=root_module,
                         module_tree=module_tree,
                         modules_json=json.dumps(module_tree, default=str))


@app.route('/teacher/modules/<module_id>/node/<node_id>/resources', methods=['GET', 'POST'])
@teacher_required
def manage_module_resources(module_id, node_id):
    """Add/edit resources for a leaf module"""
    module = Module.find_one({
        'module_id': node_id,
        'teacher_id': session['teacher_id']
    })

    if not module:
        return jsonify({'error': 'Module not found'}), 404

    if request.method == 'POST':
        try:
            resource_type = request.form.get('type')
            title = request.form.get('title')

            resource_doc = {
                'resource_id': generate_resource_id(),
                'module_id': node_id,
                'teacher_id': session['teacher_id'],
                'type': resource_type,
                'title': title,
                'description': request.form.get('description', ''),
                'order': ModuleResource.count({'module_id': node_id}) + 1,
                'created_at': datetime.utcnow()
            }

            if resource_type == 'youtube':
                resource_doc['url'] = request.form.get('url')
                # Extract duration if possible
            elif resource_type == 'pdf':
                file = request.files.get('file')
                if file:
                    resource_doc['content'] = base64.b64encode(file.read()).decode('utf-8')
            elif resource_type == 'link':
                resource_doc['url'] = request.form.get('url')

            ModuleResource.insert_one(resource_doc)

            return jsonify({'success': True, 'resource_id': resource_doc['resource_id']})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # GET - return resources
    resources = list(ModuleResource.find({'module_id': node_id}).sort('order', 1))
    return jsonify({'resources': resources})


@app.route('/teacher/modules/<module_id>/mastery')
@teacher_required
def module_class_mastery(module_id):
    """View class mastery overview for a module tree"""
    root_module = Module.find_one({
        'module_id': module_id,
        'teacher_id': session['teacher_id']
    })

    if not root_module:
        return redirect(url_for('teacher_modules'))

    # Get all students with mastery data for this module tree
    # Aggregate mastery data by student
    pipeline = [
        {
            '$match': {
                'module_id': {'$regex': f"^{module_id}"}  # All modules in tree
            }
        },
        {
            '$group': {
                '_id': '$student_id',
                'avg_mastery': {'$avg': '$mastery_score'},
                'modules_started': {'$sum': 1},
                'total_time': {'$sum': '$time_spent_minutes'}
            }
        }
    ]

    student_mastery = list(StudentModuleMastery.aggregate(pipeline))

    # Enrich with student details
    for sm in student_mastery:
        student = Student.find_one({'student_id': sm['_id']})
        if student:
            sm['name'] = student.get('name', 'Unknown')
            sm['class'] = student.get('class', '')

    return render_template('teacher_module_mastery.html',
                         module=root_module,
                         student_mastery=student_mastery)
```

### Student Routes

```python
# ============================================================================
# MY MODULES - STUDENT ROUTES
# ============================================================================

from utils.module_ai import (
    assess_student_understanding,
    analyze_writing_submission,
    generate_interactive_assessment
)

@app.route('/modules')
@login_required
def student_modules():
    """Student's module space - shows all available module trees"""
    student = Student.find_one({'student_id': session['student_id']})

    # Get teacher IDs for this student
    teacher_ids = get_student_teacher_ids(session['student_id'])

    # Get published root modules from student's teachers
    root_modules = list(Module.find({
        'teacher_id': {'$in': teacher_ids},
        'parent_id': None,
        'status': 'published'
    }))

    # Add mastery data for each module
    for module in root_modules:
        mastery = calculate_tree_mastery(module['module_id'], session['student_id'])
        module['student_mastery'] = mastery

    return render_template('student_modules.html',
                         student=student,
                         modules=root_modules)


@app.route('/modules/<module_id>')
@login_required
def student_module_view(module_id):
    """3D module visualization for student"""
    root_module = Module.find_one({
        'module_id': module_id,
        'status': 'published'
    })

    if not root_module:
        return redirect(url_for('student_modules'))

    # Build full tree with mastery data
    def build_tree_with_mastery(m):
        # Get student's mastery for this module
        mastery = StudentModuleMastery.find_one({
            'student_id': session['student_id'],
            'module_id': m['module_id']
        })
        m['mastery_score'] = mastery.get('mastery_score', 0) if mastery else 0
        m['status'] = mastery.get('status', 'not_started') if mastery else 'not_started'

        # Recursively build children
        m['children'] = []
        for cid in m.get('children_ids', []):
            child = Module.find_one({'module_id': cid})
            if child:
                m['children'].append(build_tree_with_mastery(child))

        return m

    module_tree = build_tree_with_mastery(root_module.copy())

    return render_template('student_module_view.html',
                         module=root_module,
                         module_tree=module_tree,
                         modules_json=json.dumps(module_tree, default=str))


@app.route('/modules/<module_id>/learn/<node_id>')
@login_required
def learning_page(module_id, node_id):
    """Main learning page for a specific module"""
    module = Module.find_one({'module_id': node_id})
    root_module = Module.find_one({'module_id': module_id})

    if not module or not module.get('is_leaf'):
        return redirect(url_for('student_module_view', module_id=module_id))

    # Get or create learning session
    existing_session = LearningSession.find_one({
        'student_id': session['student_id'],
        'module_id': node_id,
        'ended_at': None  # Active session
    })

    if not existing_session:
        session_doc = {
            'session_id': generate_session_id(),
            'student_id': session['student_id'],
            'module_id': node_id,
            'started_at': datetime.utcnow(),
            'ended_at': None,
            'chat_history': [],
            'assessments': [],
            'writing_submissions': [],
            'resources_viewed': []
        }
        LearningSession.insert_one(session_doc)
        existing_session = session_doc

    # Get resources for this module
    resources = list(ModuleResource.find({'module_id': node_id}).sort('order', 1))

    # Get student's mastery
    mastery = StudentModuleMastery.find_one({
        'student_id': session['student_id'],
        'module_id': node_id
    })

    # Get student's learning profile for this subject
    profile = StudentLearningProfile.find_one({
        'student_id': session['student_id'],
        'subject': root_module.get('subject')
    })

    # Get overall subject mastery
    overall_mastery = calculate_tree_mastery(module_id, session['student_id'])

    return render_template('learning_page.html',
                         module=module,
                         root_module=root_module,
                         session_data=existing_session,
                         resources=resources,
                         mastery=mastery,
                         profile=profile,
                         overall_mastery=overall_mastery)


@app.route('/api/learning/chat', methods=['POST'])
@login_required
def learning_chat():
    """Handle chat messages in learning session"""
    try:
        data = request.get_json()
        module_id = data.get('module_id')
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        writing_image = data.get('writing_image')  # Base64 image

        if not message and not writing_image:
            return jsonify({'error': 'No message or image provided'}), 400

        module = Module.find_one({'module_id': module_id})
        if not module:
            return jsonify({'error': 'Module not found'}), 404

        root_module = Module.find_one({'module_id': module.get('parent_id') or module_id})

        # Get session and chat history
        learning_session = LearningSession.find_one({'session_id': session_id})
        chat_history = learning_session.get('chat_history', []) if learning_session else []

        # Get student profile
        profile = StudentLearningProfile.find_one({
            'student_id': session['student_id'],
            'subject': root_module.get('subject')
        })

        # Process writing image if provided
        writing_bytes = None
        if writing_image:
            # Remove data URL prefix if present
            if ',' in writing_image:
                writing_image = writing_image.split(',')[1]
            writing_bytes = base64.b64decode(writing_image)

        # Get AI response
        result = assess_student_understanding(
            student_message=message,
            module=module,
            chat_history=chat_history,
            student_profile=profile,
            writing_image=writing_bytes
        )

        if 'error' in result and 'response' not in result:
            return jsonify({'error': result['error']}), 500

        # Update chat history
        new_messages = [
            {'role': 'student', 'content': message, 'timestamp': datetime.utcnow().isoformat()}
        ]
        if writing_bytes:
            new_messages[0]['has_image'] = True

        new_messages.append({
            'role': 'assistant',
            'content': result.get('response', ''),
            'timestamp': datetime.utcnow().isoformat()
        })

        # Update session
        LearningSession.update_one(
            {'session_id': session_id},
            {
                '$push': {'chat_history': {'$each': new_messages}},
                '$set': {'last_activity': datetime.utcnow()}
            }
        )

        # Update mastery based on assessment
        if result.get('assessment'):
            mastery_change = result['assessment'].get('mastery_change', 0)
            if mastery_change != 0:
                update_student_mastery(
                    session['student_id'],
                    module_id,
                    mastery_change
                )

        # Update student profile if needed
        if result.get('profile_updates'):
            update_student_profile(
                session['student_id'],
                root_module.get('subject'),
                result['profile_updates']
            )

        return jsonify({
            'response': result.get('response', ''),
            'response_type': result.get('response_type', 'teaching'),
            'assessment': result.get('assessment'),
            'interactive': result.get('interactive_element'),
            'mastery_updated': result.get('assessment', {}).get('mastery_change', 0) != 0
        })

    except Exception as e:
        logger.error(f"Error in learning chat: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/learning/submit_writing', methods=['POST'])
@login_required
def submit_writing():
    """Submit handwritten work for analysis"""
    try:
        data = request.get_json()
        module_id = data.get('module_id')
        session_id = data.get('session_id')
        image_data = data.get('image')  # Base64 canvas data
        expected_content = data.get('expected_content', '')

        if not image_data:
            return jsonify({'error': 'No image provided'}), 400

        module = Module.find_one({'module_id': module_id})
        if not module:
            return jsonify({'error': 'Module not found'}), 404

        # Decode image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)

        # Analyze with AI
        result = analyze_writing_submission(
            image_data=image_bytes,
            module=module,
            expected_content=expected_content
        )

        # Save to session
        LearningSession.update_one(
            {'session_id': session_id},
            {
                '$push': {
                    'writing_submissions': {
                        'image_data': image_data[:100] + '...',  # Truncate for storage
                        'ai_analysis': result,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                }
            }
        )

        # Update mastery based on analysis
        if result.get('mastery_indication'):
            mastery_change = (result['mastery_indication'] - 50) / 10  # Convert to -5 to +5
            update_student_mastery(session['student_id'], module_id, mastery_change)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error analyzing writing: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/learning/resource_viewed', methods=['POST'])
@login_required
def mark_resource_viewed():
    """Mark a resource as viewed and update progress"""
    try:
        data = request.get_json()
        resource_id = data.get('resource_id')
        session_id = data.get('session_id')

        # Add to viewed resources
        LearningSession.update_one(
            {'session_id': session_id},
            {'$addToSet': {'resources_viewed': resource_id}}
        )

        # Small mastery boost for viewing resources
        resource = ModuleResource.find_one({'resource_id': resource_id})
        if resource:
            update_student_mastery(
                session['student_id'],
                resource['module_id'],
                2  # Small boost
            )

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def update_student_mastery(student_id: str, module_id: str, change: float):
    """Update student's mastery score and propagate to parents"""
    # Update this module
    current = StudentModuleMastery.find_one({
        'student_id': student_id,
        'module_id': module_id
    })

    current_score = current.get('mastery_score', 0) if current else 0
    new_score = max(0, min(100, current_score + change))

    # Determine status
    if new_score >= 100:
        status = 'mastered'
    elif new_score > 0:
        status = 'in_progress'
    else:
        status = 'not_started'

    StudentModuleMastery.update_one(
        {'student_id': student_id, 'module_id': module_id},
        {
            '$set': {
                'mastery_score': new_score,
                'status': status,
                'updated_at': datetime.utcnow()
            },
            '$inc': {'time_spent_minutes': 1}
        },
        upsert=True
    )

    # Propagate to parent modules
    module = Module.find_one({'module_id': module_id})
    if module and module.get('parent_id'):
        propagate_mastery_to_parent(student_id, module['parent_id'])


def propagate_mastery_to_parent(student_id: str, parent_module_id: str):
    """
    Recalculate parent module mastery based on all children.
    Uses MINIMUM THRESHOLD: Parent reaches 100% only when ALL children are at 100%
    """
    parent = Module.find_one({'module_id': parent_module_id})
    if not parent:
        return

    children_ids = parent.get('children_ids', [])
    if not children_ids:
        return

    # Get mastery for all children
    children_mastery = []
    for child_id in children_ids:
        child_mastery = StudentModuleMastery.find_one({
            'student_id': student_id,
            'module_id': child_id
        })
        children_mastery.append(child_mastery.get('mastery_score', 0) if child_mastery else 0)

    # MINIMUM THRESHOLD: Parent score is the minimum of all children
    # This ensures ALL children must be 100% for parent to be 100%
    parent_score = min(children_mastery) if children_mastery else 0

    # Determine status
    if parent_score >= 100:
        status = 'mastered'
    elif parent_score > 0 or any(m > 0 for m in children_mastery):
        status = 'in_progress'
    else:
        status = 'not_started'

    StudentModuleMastery.update_one(
        {'student_id': student_id, 'module_id': parent_module_id},
        {
            '$set': {
                'mastery_score': parent_score,
                'status': status,
                'updated_at': datetime.utcnow()
            }
        },
        upsert=True
    )

    # Continue propagation up the tree
    if parent.get('parent_id'):
        propagate_mastery_to_parent(student_id, parent['parent_id'])


def calculate_tree_mastery(root_module_id: str, student_id: str) -> float:
    """Calculate overall mastery for a module tree"""
    mastery = StudentModuleMastery.find_one({
        'student_id': student_id,
        'module_id': root_module_id
    })
    return mastery.get('mastery_score', 0) if mastery else 0


def update_student_profile(student_id: str, subject: str, updates: dict):
    """Update student's learning profile with new insights"""
    profile = StudentLearningProfile.find_one({
        'student_id': student_id,
        'subject': subject
    })

    update_ops = {'$set': {'last_updated': datetime.utcnow()}}

    if updates.get('new_strength'):
        if profile:
            update_ops['$push'] = {'strengths': updates['new_strength']}
        else:
            update_ops['$set']['strengths'] = [updates['new_strength']]

    if updates.get('new_weakness'):
        if profile:
            update_ops.setdefault('$push', {})['weaknesses'] = updates['new_weakness']
        else:
            update_ops['$set']['weaknesses'] = [updates['new_weakness']]

    if updates.get('new_mistake_pattern'):
        if profile:
            update_ops.setdefault('$push', {})['common_mistakes'] = {
                'pattern': updates['new_mistake_pattern'],
                'frequency': 1
            }
        else:
            update_ops['$set']['common_mistakes'] = [{
                'pattern': updates['new_mistake_pattern'],
                'frequency': 1
            }]

    StudentLearningProfile.update_one(
        {'student_id': student_id, 'subject': subject},
        update_ops,
        upsert=True
    )
```

---

## HTML Templates

### 1. templates/teacher_modules.html
```html
{% extends "base.html" %}

{% block title %}My Modules - Teacher Portal{% endblock %}

{% block navbar %}
<!-- Same as teacher_dashboard.html navbar with "Modules" link added -->
{% endblock %}

{% block content %}
<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1><i class="bi bi-diagram-3 me-2"></i>My Modules</h1>
            <p class="text-muted">Create and manage learning module trees</p>
        </div>
        <a href="{{ url_for('create_module') }}" class="btn btn-primary">
            <i class="bi bi-plus-circle me-1"></i>Create New Module
        </a>
    </div>

    {% if modules %}
    <div class="row g-4">
        {% for module in modules %}
        <div class="col-md-6 col-lg-4">
            <div class="card h-100 module-card">
                <div class="card-body">
                    <div class="d-flex align-items-start mb-3">
                        <div class="module-icon me-3" style="background: {{ module.color }}20; color: {{ module.color }};">
                            <i class="bi bi-diagram-3"></i>
                        </div>
                        <div class="flex-grow-1">
                            <h5 class="card-title mb-1">{{ module.title }}</h5>
                            <p class="text-muted small mb-0">{{ module.subject }} • {{ module.year_level }}</p>
                        </div>
                    </div>

                    <div class="module-stats d-flex gap-3 mb-3">
                        <div class="stat">
                            <i class="bi bi-boxes text-primary"></i>
                            <span>{{ module.total_modules }} modules</span>
                        </div>
                        <div class="stat">
                            <i class="bi bi-clock text-info"></i>
                            <span>{{ module.estimated_hours }}h</span>
                        </div>
                    </div>

                    <div class="d-flex gap-2">
                        <a href="{{ url_for('view_module', module_id=module.module_id) }}" class="btn btn-outline-primary btn-sm flex-grow-1">
                            <i class="bi bi-eye me-1"></i>View & Edit
                        </a>
                        <a href="{{ url_for('module_class_mastery', module_id=module.module_id) }}" class="btn btn-outline-success btn-sm">
                            <i class="bi bi-graph-up"></i>
                        </a>
                    </div>
                </div>
                <div class="card-footer bg-transparent">
                    <small class="text-muted">
                        {% if module.status == 'published' %}
                        <span class="badge bg-success">Published</span>
                        {% else %}
                        <span class="badge bg-warning">Draft</span>
                        {% endif %}
                        • Created {{ module.created_at.strftime('%d %b %Y') }}
                    </small>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="empty-state text-center py-5">
        <i class="bi bi-diagram-3 display-1 text-muted"></i>
        <h4 class="mt-3">No Modules Yet</h4>
        <p class="text-muted">Upload a syllabus to automatically generate your module tree</p>
        <a href="{{ url_for('create_module') }}" class="btn btn-primary">
            <i class="bi bi-plus-circle me-1"></i>Create Your First Module
        </a>
    </div>
    {% endif %}
</div>

<style>
.module-card {
    transition: transform 0.2s, box-shadow 0.2s;
}
.module-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
}
.module-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
}
.module-stats .stat {
    font-size: 0.875rem;
    color: var(--text-secondary);
}
.module-stats .stat i {
    margin-right: 0.25rem;
}
</style>
{% endblock %}
```

### 2. templates/learning_page.html
This is the main student learning interface. See LEARNING_PAGE_TEMPLATE.html in the next section.

---

## Three.js 3D Visualization

Create `static/js/module-3d.js`:

```javascript
/**
 * 3D Module Visualization using Three.js
 * Renders hierarchical module structure in 3D space
 */

import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.157.0/build/three.module.js';
import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.157.0/examples/jsm/controls/OrbitControls.js';

class ModuleVisualization {
    constructor(containerId, moduleTree, options = {}) {
        this.container = document.getElementById(containerId);
        this.moduleTree = moduleTree;
        this.options = {
            isTeacher: options.isTeacher || false,
            onModuleClick: options.onModuleClick || (() => {}),
            ...options
        };

        this.modules = new Map(); // module_id -> mesh
        this.connections = [];

        this.init();
        this.createModules(this.moduleTree);
        this.animate();
    }

    init() {
        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xf8fafc);

        // Camera
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 2000);
        this.camera.position.set(0, 200, 400);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // Controls
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.maxDistance = 800;
        this.controls.minDistance = 100;

        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(100, 200, 100);
        this.scene.add(directionalLight);

        // Raycaster for click detection
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // Event listeners
        this.container.addEventListener('click', this.onClick.bind(this));
        window.addEventListener('resize', this.onResize.bind(this));
    }

    createModules(node, parentPosition = null, depth = 0, siblingIndex = 0, siblingCount = 1) {
        // Calculate position
        const position = this.calculatePosition(depth, siblingIndex, siblingCount, parentPosition);

        // Create module sphere
        const radius = Math.max(20 - depth * 3, 8);
        const geometry = new THREE.SphereGeometry(radius, 32, 32);

        // Color based on mastery
        const masteryScore = node.mastery_score || 0;
        const color = this.getMasteryColor(masteryScore, node.color);

        const material = new THREE.MeshPhongMaterial({
            color: color,
            shininess: 50,
            transparent: true,
            opacity: masteryScore > 0 ? 1 : 0.7
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.copy(position);
        mesh.userData = {
            moduleId: node.module_id,
            title: node.title,
            isLeaf: node.is_leaf,
            masteryScore: masteryScore,
            depth: depth
        };

        this.scene.add(mesh);
        this.modules.set(node.module_id, mesh);

        // Create label
        this.createLabel(node.title, position, depth);

        // Create connection to parent
        if (parentPosition) {
            this.createConnection(parentPosition, position, masteryScore);
        }

        // Create children
        const children = node.children || [];
        children.forEach((child, index) => {
            this.createModules(child, position, depth + 1, index, children.length);
        });
    }

    calculatePosition(depth, siblingIndex, siblingCount, parentPosition) {
        if (depth === 0) {
            return new THREE.Vector3(0, 0, 0);
        }

        const baseDistance = 80 + depth * 30;
        const angle = (siblingIndex / siblingCount) * Math.PI * 2 + Math.PI / 4;
        const yOffset = depth * 20;

        const x = (parentPosition?.x || 0) + Math.cos(angle) * baseDistance;
        const z = (parentPosition?.z || 0) + Math.sin(angle) * baseDistance;
        const y = yOffset;

        return new THREE.Vector3(x, y, z);
    }

    getMasteryColor(mastery, baseColor) {
        // Convert hex to RGB
        const base = new THREE.Color(baseColor || '#667eea');

        if (mastery >= 100) {
            return new THREE.Color('#10b981'); // Green for mastered
        } else if (mastery > 0) {
            // Blend base color with progress
            const progress = new THREE.Color('#fbbf24'); // Yellow for in-progress
            return base.lerp(progress, mastery / 200);
        }
        return base;
    }

    createLabel(text, position, depth) {
        // Create canvas texture for label
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;

        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.font = 'bold 20px Arial';
        ctx.fillStyle = '#1e293b';
        ctx.textAlign = 'center';
        ctx.fillText(text.substring(0, 20), 128, 40);

        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);

        sprite.position.copy(position);
        sprite.position.y += 30 - depth * 3;
        sprite.scale.set(60, 15, 1);

        this.scene.add(sprite);
    }

    createConnection(start, end, mastery) {
        const points = [start, end];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);

        const color = mastery >= 100 ? 0x10b981 : 0x94a3b8;
        const material = new THREE.LineBasicMaterial({
            color: color,
            opacity: 0.5,
            transparent: true
        });

        const line = new THREE.Line(geometry, material);
        this.scene.add(line);
        this.connections.push(line);
    }

    onClick(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);

        const meshes = Array.from(this.modules.values());
        const intersects = this.raycaster.intersectObjects(meshes);

        if (intersects.length > 0) {
            const clicked = intersects[0].object;
            this.options.onModuleClick(clicked.userData);
        }
    }

    onResize() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));
        this.controls.update();

        // Gentle rotation animation
        this.modules.forEach((mesh) => {
            mesh.rotation.y += 0.002;
        });

        this.renderer.render(this.scene, this.camera);
    }

    highlightModule(moduleId) {
        const mesh = this.modules.get(moduleId);
        if (mesh) {
            // Pulse animation
            mesh.scale.set(1.2, 1.2, 1.2);
            setTimeout(() => mesh.scale.set(1, 1, 1), 300);
        }
    }

    updateMastery(moduleId, newScore) {
        const mesh = this.modules.get(moduleId);
        if (mesh) {
            const color = this.getMasteryColor(newScore, mesh.userData.baseColor);
            mesh.material.color = color;
            mesh.userData.masteryScore = newScore;
        }
    }
}

// Export for use
window.ModuleVisualization = ModuleVisualization;
```

---

## Static Files for Learning Page

### static/js/drawing-canvas.js

```javascript
/**
 * Drawing Canvas for Student Writing/Equations
 * Touch-optimized for iPad with pressure sensitivity
 */

class DrawingCanvas {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');

        this.options = {
            lineColor: options.lineColor || '#1e293b',
            lineWidth: options.lineWidth || 3,
            onSubmit: options.onSubmit || (() => {}),
            ...options
        };

        this.isDrawing = false;
        this.lastPoint = null;

        this.init();
    }

    init() {
        // Set canvas size
        this.resize();
        window.addEventListener('resize', () => this.resize());

        // Setup drawing context
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        this.ctx.strokeStyle = this.options.lineColor;
        this.ctx.lineWidth = this.options.lineWidth;

        // White background
        this.clear();

        // Event listeners for mouse
        this.canvas.addEventListener('mousedown', this.startDrawing.bind(this));
        this.canvas.addEventListener('mousemove', this.draw.bind(this));
        this.canvas.addEventListener('mouseup', this.stopDrawing.bind(this));
        this.canvas.addEventListener('mouseout', this.stopDrawing.bind(this));

        // Event listeners for touch (iPad)
        this.canvas.addEventListener('touchstart', this.handleTouchStart.bind(this));
        this.canvas.addEventListener('touchmove', this.handleTouchMove.bind(this));
        this.canvas.addEventListener('touchend', this.stopDrawing.bind(this));

        // Prevent scrolling while drawing
        this.canvas.addEventListener('touchmove', (e) => e.preventDefault(), { passive: false });
    }

    resize() {
        const container = this.canvas.parentElement;
        const rect = container.getBoundingClientRect();

        // Save current drawing
        const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);

        // Resize canvas
        this.canvas.width = rect.width;
        this.canvas.height = Math.max(300, rect.height);

        // Restore context settings
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        this.ctx.strokeStyle = this.options.lineColor;
        this.ctx.lineWidth = this.options.lineWidth;

        // Restore drawing
        this.ctx.putImageData(imageData, 0, 0);
    }

    getCanvasCoordinates(event) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;

        return {
            x: (event.clientX - rect.left) * scaleX,
            y: (event.clientY - rect.top) * scaleY
        };
    }

    getTouchCoordinates(touch) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;

        return {
            x: (touch.clientX - rect.left) * scaleX,
            y: (touch.clientY - rect.top) * scaleY
        };
    }

    startDrawing(event) {
        this.isDrawing = true;
        this.lastPoint = this.getCanvasCoordinates(event);
    }

    handleTouchStart(event) {
        event.preventDefault();
        if (event.touches.length === 1) {
            this.isDrawing = true;
            this.lastPoint = this.getTouchCoordinates(event.touches[0]);

            // Handle Apple Pencil pressure
            if (event.touches[0].force) {
                this.ctx.lineWidth = this.options.lineWidth * event.touches[0].force * 2;
            }
        }
    }

    draw(event) {
        if (!this.isDrawing) return;

        const currentPoint = this.getCanvasCoordinates(event);
        this.drawLine(this.lastPoint, currentPoint);
        this.lastPoint = currentPoint;
    }

    handleTouchMove(event) {
        event.preventDefault();
        if (!this.isDrawing || event.touches.length !== 1) return;

        const currentPoint = this.getTouchCoordinates(event.touches[0]);

        // Adjust line width based on pressure (Apple Pencil)
        if (event.touches[0].force) {
            this.ctx.lineWidth = this.options.lineWidth * event.touches[0].force * 2;
        }

        this.drawLine(this.lastPoint, currentPoint);
        this.lastPoint = currentPoint;
    }

    drawLine(from, to) {
        this.ctx.beginPath();
        this.ctx.moveTo(from.x, from.y);
        this.ctx.lineTo(to.x, to.y);
        this.ctx.stroke();
    }

    stopDrawing() {
        this.isDrawing = false;
        this.lastPoint = null;
    }

    clear() {
        this.ctx.fillStyle = '#ffffff';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    getImageData() {
        return this.canvas.toDataURL('image/png');
    }

    submit() {
        const imageData = this.getImageData();
        this.options.onSubmit(imageData);
    }

    setLineColor(color) {
        this.options.lineColor = color;
        this.ctx.strokeStyle = color;
    }

    setLineWidth(width) {
        this.options.lineWidth = width;
        this.ctx.lineWidth = width;
    }
}

window.DrawingCanvas = DrawingCanvas;
```

---

## CSS Additions (add to static/css/style.css)

```css
/* ============================================
   MY MODULES - Additional Styles
   ============================================ */

/* 3D Module Visualization */
.module-3d-container {
    width: 100%;
    height: 500px;
    border-radius: var(--border-radius);
    overflow: hidden;
    background: var(--bg-light);
}

@media (min-width: 992px) {
    .module-3d-container {
        height: 600px;
    }
}

/* Learning Page Layout */
.learning-page {
    display: grid;
    grid-template-columns: 1fr 350px;
    gap: 1.5rem;
    height: calc(100vh - 80px);
}

@media (max-width: 1200px) {
    .learning-page {
        grid-template-columns: 1fr;
        height: auto;
    }
}

.learning-main {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
}

.learning-sidebar {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
}

/* Chat Interface */
.learning-chat {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: white;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow);
    min-height: 400px;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    background: #f8fafc;
}

.chat-message {
    max-width: 80%;
    margin-bottom: 1rem;
    animation: messageIn 0.2s ease-out;
}

.chat-message.student {
    margin-left: auto;
}

.chat-message.assistant {
    margin-right: auto;
}

.chat-message .bubble {
    padding: 0.75rem 1rem;
    border-radius: 16px;
}

.chat-message.student .bubble {
    background: var(--gradient-primary);
    color: white;
    border-bottom-right-radius: 4px;
}

.chat-message.assistant .bubble {
    background: white;
    box-shadow: var(--shadow-sm);
    border-bottom-left-radius: 4px;
}

/* Writing Canvas */
.writing-panel {
    background: white;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow);
    padding: 1rem;
}

.writing-canvas-container {
    border: 2px solid var(--border-color);
    border-radius: 8px;
    background: white;
}

.writing-canvas {
    width: 100%;
    touch-action: none;
    cursor: crosshair;
}

.writing-tools {
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 0.5rem;
}

.writing-tools .btn {
    padding: 0.25rem 0.5rem;
}

/* Resources Panel */
.resources-panel {
    background: white;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow);
}

.resource-item {
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    transition: background 0.2s;
}

.resource-item:hover {
    background: var(--bg-light);
}

.resource-item:last-child {
    border-bottom: none;
}

.resource-icon {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 0.75rem;
}

.resource-icon.youtube {
    background: rgba(255, 0, 0, 0.1);
    color: #ff0000;
}

.resource-icon.pdf {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
}

.resource-icon.interactive {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
}

/* Progress Panel */
.progress-panel {
    background: white;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow);
    padding: 1rem;
}

.mastery-circle {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: conic-gradient(
        var(--primary) var(--mastery-percent),
        var(--border-color) var(--mastery-percent)
    );
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 1rem;
}

.mastery-circle-inner {
    width: 100px;
    height: 100px;
    border-radius: 50%;
    background: white;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
}

.mastery-score {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--primary);
}

.topic-progress {
    margin-top: 1rem;
}

.topic-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
}

.topic-item:last-child {
    border-bottom: none;
}

/* Interactive Quiz Modal */
.quiz-modal .question-card {
    background: var(--bg-light);
    border-radius: var(--border-radius);
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.quiz-modal .option {
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
}

.quiz-modal .option:hover {
    border-color: var(--primary);
    background: rgba(102, 126, 234, 0.05);
}

.quiz-modal .option.selected {
    border-color: var(--primary);
    background: rgba(102, 126, 234, 0.1);
}

.quiz-modal .option.correct {
    border-color: var(--success);
    background: rgba(16, 185, 129, 0.1);
}

.quiz-modal .option.incorrect {
    border-color: var(--danger);
    background: rgba(239, 68, 68, 0.1);
}

/* Module Node Tooltip */
.module-tooltip {
    position: absolute;
    background: white;
    padding: 1rem;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow-lg);
    z-index: 1000;
    max-width: 300px;
    pointer-events: none;
}

.module-tooltip h5 {
    margin: 0 0 0.5rem;
}

.module-tooltip .mastery-bar {
    height: 8px;
    background: var(--border-color);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 0.5rem;
}

.module-tooltip .mastery-fill {
    height: 100%;
    background: var(--gradient-primary);
    transition: width 0.3s;
}
```

---

## Navigation Updates

Add to both teacher and student navbars:

```html
<!-- Teacher Navbar - add after Submissions -->
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('teacher_modules') }}">
        <i class="bi bi-diagram-3 me-1"></i>Modules
    </a>
</li>

<!-- Student Navbar - add after Assignments -->
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('student_modules') }}">
        <i class="bi bi-diagram-3 me-1"></i>My Learning
    </a>
</li>
```

---

## Testing Checklist

### Teacher Flow
- [ ] Upload syllabus PDF → AI generates module tree
- [ ] View 3D module visualization
- [ ] Click nodes to add/edit resources
- [ ] Publish module for students
- [ ] View class mastery dashboard

### Student Flow
- [ ] View available module trees
- [ ] Navigate 3D visualization
- [ ] Click leaf module → enters learning page
- [ ] Chat with AI tutor
- [ ] Submit handwritten work
- [ ] View resources (YouTube, PDF)
- [ ] Complete assessments
- [ ] See mastery update and propagate

### Mastery Logic
- [ ] Child module mastery increases → parent recalculates
- [ ] All children at 100% → parent becomes 100%
- [ ] One child drops below 100% → parent updates accordingly

---

## Environment Variables to Add

```
# Already have ANTHROPIC_API_KEY from existing setup
# No new env vars needed for basic functionality

# Optional: For YouTube API (get video metadata)
YOUTUBE_API_KEY=your_key_here
```

---

## Implementation Order

1. **Database Setup**
   - Add new collections to models.py
   - Add indexes

2. **Backend Routes**
   - Teacher module creation/management
   - Student module viewing/learning
   - API endpoints for chat and writing

3. **AI Integration**
   - Module generation from syllabus
   - Learning assessment chat
   - Writing analysis

4. **Frontend**
   - 3D visualization (Three.js)
   - Learning page layout
   - Drawing canvas
   - Chat interface

5. **Testing**
   - Unit tests for mastery propagation
   - Integration tests for AI calls
   - UI testing on iPad

---

**CURSOR AI: Generate all files following this specification. Start with models.py updates, then utils/module_ai.py, then app.py routes, then HTML templates, then JavaScript files. Ensure all components integrate with the existing authentication and database systems.**
