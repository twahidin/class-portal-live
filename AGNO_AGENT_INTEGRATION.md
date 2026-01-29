# Agno Agent Integration for Learning Module

This document provides the Agno agent implementation to replace the raw Claude API calls in the module AI system. Agno is faster and provides better agent orchestration.

## Installation

```bash
pip install agno anthropic
```

## New File: utils/agno_learning_agent.py

```python
"""
Agno-based Learning Agent for Student Mastery Assessment

Uses Agno framework for fast, reliable agent execution with:
- Student profile management (memory)
- Learning assessment with tools
- Writing/image analysis
- Interactive quiz generation
"""

import os
import json
import base64
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.tools import tool
from agno.memory import Memory
from agno.storage import MongoStorage

logger = logging.getLogger(__name__)

# ============================================================================
# AGNO TOOLS - Functions the agent can call
# ============================================================================

@tool
def update_student_mastery(student_id: str, module_id: str, mastery_change: float, concept: str) -> dict:
    """
    Update a student's mastery score for a specific module.

    Args:
        student_id: The student's ID
        module_id: The module being assessed
        mastery_change: Points to add/subtract (-10 to +10)
        concept: The specific concept being assessed

    Returns:
        Updated mastery information
    """
    from models import StudentModuleMastery, Module

    # Get current mastery
    current = StudentModuleMastery.find_one({
        'student_id': student_id,
        'module_id': module_id
    })

    current_score = current.get('mastery_score', 0) if current else 0
    new_score = max(0, min(100, current_score + mastery_change))

    # Determine status
    if new_score >= 100:
        status = 'mastered'
    elif new_score > 0:
        status = 'in_progress'
    else:
        status = 'not_started'

    # Update database
    StudentModuleMastery.update_one(
        {'student_id': student_id, 'module_id': module_id},
        {
            '$set': {
                'mastery_score': new_score,
                'status': status,
                'updated_at': datetime.utcnow()
            },
            '$inc': {'assessments_completed': 1 if mastery_change != 0 else 0}
        },
        upsert=True
    )

    return {
        'previous_score': current_score,
        'new_score': new_score,
        'change': mastery_change,
        'status': status,
        'concept_assessed': concept
    }


@tool
def record_student_strength(student_id: str, subject: str, topic: str, confidence: float) -> dict:
    """
    Record a new strength in the student's learning profile.

    Args:
        student_id: The student's ID
        subject: Subject area (e.g., "Mathematics")
        topic: Specific topic they're strong in
        confidence: Confidence level 0.0-1.0

    Returns:
        Confirmation of update
    """
    from models import StudentLearningProfile

    StudentLearningProfile.update_one(
        {'student_id': student_id, 'subject': subject},
        {
            '$push': {
                'strengths': {
                    'topic': topic,
                    'confidence': confidence,
                    'recorded_at': datetime.utcnow().isoformat()
                }
            },
            '$set': {'last_updated': datetime.utcnow()}
        },
        upsert=True
    )

    return {'recorded': True, 'topic': topic, 'confidence': confidence}


@tool
def record_student_weakness(student_id: str, subject: str, topic: str, notes: str) -> dict:
    """
    Record a weakness or area for improvement in the student's profile.

    Args:
        student_id: The student's ID
        subject: Subject area
        topic: Topic they struggle with
        notes: Specific notes about the weakness

    Returns:
        Confirmation of update
    """
    from models import StudentLearningProfile

    StudentLearningProfile.update_one(
        {'student_id': student_id, 'subject': subject},
        {
            '$push': {
                'weaknesses': {
                    'topic': topic,
                    'notes': notes,
                    'recorded_at': datetime.utcnow().isoformat()
                }
            },
            '$set': {'last_updated': datetime.utcnow()}
        },
        upsert=True
    )

    return {'recorded': True, 'topic': topic}


@tool
def record_mistake_pattern(student_id: str, subject: str, pattern: str) -> dict:
    """
    Record a common mistake pattern the student makes.

    Args:
        student_id: The student's ID
        subject: Subject area
        pattern: Description of the mistake pattern

    Returns:
        Confirmation of update
    """
    from models import StudentLearningProfile

    StudentLearningProfile.update_one(
        {'student_id': student_id, 'subject': subject},
        {
            '$push': {
                'common_mistakes': {
                    'pattern': pattern,
                    'frequency': 1,
                    'first_seen': datetime.utcnow().isoformat()
                }
            },
            '$set': {'last_updated': datetime.utcnow()}
        },
        upsert=True
    )

    return {'recorded': True, 'pattern': pattern}


@tool
def generate_practice_question(topic: str, difficulty: str, question_type: str) -> dict:
    """
    Generate a practice question for the student.

    Args:
        topic: The topic to generate a question for
        difficulty: "easy", "medium", or "hard"
        question_type: "mcq", "short_answer", or "problem"

    Returns:
        Generated question with answer
    """
    # This would typically call another AI or use a question bank
    # For now, return a placeholder structure
    return {
        'generated': True,
        'topic': topic,
        'difficulty': difficulty,
        'type': question_type,
        'question': f"[AI will generate a {difficulty} {question_type} question about {topic}]",
        'hints_available': True
    }


@tool
def get_module_resources(module_id: str) -> list:
    """
    Get all learning resources for a module.

    Args:
        module_id: The module ID

    Returns:
        List of resources (videos, slides, PDFs, interactives)
    """
    from models import ModuleResource

    resources = list(ModuleResource.find({'module_id': module_id}).sort('order', 1))
    return [
        {
            'resource_id': r.get('resource_id'),
            'type': r.get('type'),
            'title': r.get('title'),
            'description': r.get('description'),
            'duration_minutes': r.get('duration_minutes')
        }
        for r in resources
    ]


# ============================================================================
# AGNO LEARNING AGENT
# ============================================================================

class LearningAgent:
    """
    Agno-based learning agent that:
    1. Teaches concepts adaptively
    2. Assesses student understanding
    3. Maintains student profiles
    4. Generates practice questions
    """

    def __init__(self, mongodb_uri: str = None):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        # Initialize storage for agent memory
        self.storage = None
        if mongodb_uri:
            self.storage = MongoStorage(
                connection_string=mongodb_uri,
                database='school_portal',
                collection='agno_memory'
            )

        # Create the agent
        self.agent = Agent(
            model=Claude(
                id="claude-sonnet-4-5-20250929",
                api_key=self.api_key
            ),
            tools=[
                update_student_mastery,
                record_student_strength,
                record_student_weakness,
                record_mistake_pattern,
                generate_practice_question,
                get_module_resources
            ],
            memory=Memory(storage=self.storage) if self.storage else None,
            description="Expert tutor that teaches, assesses, and tracks student learning",
            instructions=[
                "You are a patient, encouraging tutor helping students learn.",
                "Adapt your teaching style to the student's level and learning profile.",
                "After explaining concepts, assess understanding with questions.",
                "Use the tools to track mastery and update student profiles.",
                "When a student answers correctly, use update_student_mastery with positive change.",
                "When a student makes mistakes, record the pattern and provide hints.",
                "Never give answers directly - guide students to discover them.",
                "Be encouraging and celebrate progress.",
            ],
            markdown=True
        )

    def create_session_context(
        self,
        student_id: str,
        module: Dict,
        student_profile: Optional[Dict] = None,
        chat_history: Optional[List[Dict]] = None
    ) -> str:
        """Build context string for the agent"""

        profile_text = ""
        if student_profile:
            strengths = ", ".join([s['topic'] for s in student_profile.get('strengths', [])])
            weaknesses = ", ".join([w['topic'] for w in student_profile.get('weaknesses', [])])
            mistakes = ", ".join([m['pattern'] for m in student_profile.get('common_mistakes', [])])
            profile_text = f"""
STUDENT PROFILE:
- Strengths: {strengths or 'Not yet identified'}
- Areas to improve: {weaknesses or 'Not yet identified'}
- Common mistake patterns: {mistakes or 'None recorded'}
- Learning style: {student_profile.get('learning_style', 'Unknown')}
"""

        history_text = ""
        if chat_history:
            recent = chat_history[-10:]  # Last 10 messages
            history_text = "\nRECENT CONVERSATION:\n"
            for msg in recent:
                role = "Student" if msg['role'] == 'student' else "Tutor"
                history_text += f"{role}: {msg['content']}\n"

        return f"""
CURRENT SESSION:
- Student ID: {student_id}
- Module: {module.get('title', 'Unknown')}
- Subject: {module.get('subject', 'General')}
- Learning Objectives: {', '.join(module.get('learning_objectives', []))}
{profile_text}
{history_text}
"""

    def chat(
        self,
        message: str,
        student_id: str,
        module: Dict,
        student_profile: Optional[Dict] = None,
        chat_history: Optional[List[Dict]] = None,
        image_data: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Process a student message and return the agent's response.

        Args:
            message: Student's message
            student_id: Student ID for tracking
            module: Current module data
            student_profile: Student's learning profile
            chat_history: Previous messages
            image_data: Optional image (handwritten work)

        Returns:
            Agent response with any tool calls made
        """
        try:
            # Build context
            context = self.create_session_context(
                student_id, module, student_profile, chat_history
            )

            # Build the full prompt
            full_message = f"{context}\n\nSTUDENT MESSAGE: {message}"

            # If there's an image, we need to handle it
            if image_data:
                full_message += "\n\n[Student has submitted handwritten work - analyze the image]"
                # Note: Agno handles images via the model's native capabilities
                # You may need to pass image_data to the model depending on Agno version

            # Run the agent
            response = self.agent.run(full_message)

            # Extract the response content
            return {
                'response': response.content,
                'tool_calls': [
                    {'name': tc.name, 'args': tc.arguments, 'result': tc.result}
                    for tc in response.tool_calls
                ] if hasattr(response, 'tool_calls') else [],
                'success': True
            }

        except Exception as e:
            logger.error(f"Error in learning agent chat: {e}")
            return {
                'response': "I'm having trouble right now. Let's try again!",
                'tool_calls': [],
                'success': False,
                'error': str(e)
            }

    def analyze_writing(
        self,
        image_data: bytes,
        module: Dict,
        expected_content: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze student's handwritten work.

        Args:
            image_data: Image bytes
            module: Current module
            expected_content: What student was asked to show

        Returns:
            Analysis of the work
        """
        try:
            prompt = f"""
Analyze this student's handwritten work for the module: {module.get('title')}
{f'Expected content: {expected_content}' if expected_content else ''}

Evaluate:
1. Mathematical/logical correctness
2. Clarity of presentation
3. Method and approach used
4. Any errors or misconceptions

Provide:
- Transcription of what's written
- Whether it's correct
- Specific errors if any
- Suggestions for improvement
- Mastery indication (0-100)
"""

            # Run with image
            response = self.agent.run(
                prompt,
                images=[image_data]  # Pass image to agent
            )

            return {
                'analysis': response.content,
                'success': True
            }

        except Exception as e:
            logger.error(f"Error analyzing writing: {e}")
            return {
                'analysis': "Unable to analyze the writing at this time.",
                'success': False,
                'error': str(e)
            }


# ============================================================================
# SYLLABUS PARSING AGENT
# ============================================================================

class SyllabusAgent:
    """
    Agno agent for parsing syllabus documents and generating module structures.
    """

    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.agent = Agent(
            model=Claude(
                id="claude-sonnet-4-5-20250929",
                api_key=self.api_key
            ),
            description="Curriculum designer that creates module structures from syllabi",
            instructions=[
                "Analyze syllabus documents and create hierarchical module structures.",
                "The root module represents the entire year/course.",
                "First level children are major topics/units.",
                "Second level are sub-topics.",
                "Third level (leaves) are specific learning objectives.",
                "Maximum depth: 4 levels.",
                "Each leaf module should be learnable in 1-2 hours.",
                "Include estimated hours for each module.",
                "Generate clear learning objectives.",
                "Assign colors that group related topics.",
                "Output valid JSON only."
            ],
            markdown=False
        )

    def parse_syllabus(
        self,
        file_content: bytes,
        file_type: str,
        subject: str,
        year_level: str
    ) -> Dict[str, Any]:
        """
        Parse a syllabus document and generate module structure.

        Args:
            file_content: PDF or Word document bytes
            file_type: 'pdf' or 'docx'
            subject: Subject name
            year_level: e.g., "Secondary 3"

        Returns:
            Module tree structure as JSON
        """
        try:
            prompt = f"""
Analyze this syllabus/scheme of work for {subject} ({year_level}).

Create a hierarchical module structure with:
- Root module (entire year/course)
- Level 1: Major topics/units
- Level 2: Sub-topics
- Level 3: Specific learning objectives (leaf nodes)

Output ONLY valid JSON in this format:
{{
    "root": {{
        "title": "{subject} {year_level}",
        "description": "...",
        "estimated_hours": 150,
        "color": "#667eea",
        "children": [
            {{
                "title": "Topic Name",
                "description": "...",
                "estimated_hours": 40,
                "color": "#764ba2",
                "learning_objectives": ["...", "..."],
                "children": [...]
            }}
        ]
    }},
    "total_modules": 25,
    "total_hours": 150
}}
"""

            # Run with document
            if file_type == 'pdf':
                response = self.agent.run(
                    prompt,
                    files=[{'content': file_content, 'type': 'application/pdf'}]
                )
            else:
                # For other file types, you may need to convert first
                response = self.agent.run(prompt)

            # Parse the JSON response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                return json.loads(json_match.group())

            return {'error': 'Could not parse module structure from response'}

        except Exception as e:
            logger.error(f"Error parsing syllabus: {e}")
            return {'error': str(e)}


# ============================================================================
# HELPER FUNCTIONS FOR FLASK ROUTES
# ============================================================================

# Singleton instances
_learning_agent = None
_syllabus_agent = None

def get_learning_agent(mongodb_uri: str = None) -> LearningAgent:
    """Get or create the learning agent singleton"""
    global _learning_agent
    if _learning_agent is None:
        _learning_agent = LearningAgent(mongodb_uri)
    return _learning_agent

def get_syllabus_agent() -> SyllabusAgent:
    """Get or create the syllabus agent singleton"""
    global _syllabus_agent
    if _syllabus_agent is None:
        _syllabus_agent = SyllabusAgent()
    return _syllabus_agent
```

## Updated Flask Routes (app.py)

Replace the AI calls in your routes with Agno agent calls:

```python
from utils.agno_learning_agent import get_learning_agent, get_syllabus_agent

@app.route('/api/learning/chat', methods=['POST'])
@login_required
def learning_chat():
    """Handle chat messages in learning session using Agno agent"""
    try:
        data = request.get_json()
        module_id = data.get('module_id')
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        writing_image = data.get('writing_image')

        if not message and not writing_image:
            return jsonify({'error': 'No message or image provided'}), 400

        module = Module.find_one({'module_id': module_id})
        if not module:
            return jsonify({'error': 'Module not found'}), 404

        # Get learning session and profile
        learning_session = LearningSession.find_one({'session_id': session_id})
        chat_history = learning_session.get('chat_history', []) if learning_session else []

        root_module = Module.find_one({'module_id': module.get('parent_id') or module_id})
        profile = StudentLearningProfile.find_one({
            'student_id': session['student_id'],
            'subject': root_module.get('subject')
        })

        # Process image if provided
        image_bytes = None
        if writing_image:
            if ',' in writing_image:
                writing_image = writing_image.split(',')[1]
            image_bytes = base64.b64decode(writing_image)

        # Get Agno agent and run
        agent = get_learning_agent(app.config.get('MONGODB_URI'))
        result = agent.chat(
            message=message,
            student_id=session['student_id'],
            module=module,
            student_profile=profile,
            chat_history=chat_history,
            image_data=image_bytes
        )

        # Update chat history
        new_messages = [
            {'role': 'student', 'content': message, 'timestamp': datetime.utcnow().isoformat()}
        ]
        if image_bytes:
            new_messages[0]['has_image'] = True

        new_messages.append({
            'role': 'assistant',
            'content': result.get('response', ''),
            'timestamp': datetime.utcnow().isoformat()
        })

        LearningSession.update_one(
            {'session_id': session_id},
            {
                '$push': {'chat_history': {'$each': new_messages}},
                '$set': {'last_activity': datetime.utcnow()}
            }
        )

        return jsonify({
            'response': result.get('response', ''),
            'tool_calls': result.get('tool_calls', []),
            'success': result.get('success', False)
        })

    except Exception as e:
        logger.error(f"Error in learning chat: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/teacher/modules/create', methods=['POST'])
@teacher_required
def create_module():
    """Create new module tree from syllabus using Agno agent"""
    try:
        subject = request.form.get('subject')
        year_level = request.form.get('year_level')
        file = request.files.get('syllabus_file')

        if not file or not subject:
            return jsonify({'error': 'Missing required fields'}), 400

        file_content = file.read()
        file_type = 'pdf' if file.filename.lower().endswith('.pdf') else 'docx'

        # Use Agno syllabus agent
        agent = get_syllabus_agent()
        result = agent.parse_syllabus(
            file_content=file_content,
            file_type=file_type,
            subject=subject,
            year_level=year_level
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
```

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=your_anthropic_key

# Optional - for agent memory persistence
MONGODB_URI=mongodb://localhost:27017/school_portal
```

## Benefits of Agno over Raw API

1. **Speed**: Agno optimizes API calls and manages concurrency
2. **Tools**: Easy-to-define tool functions the agent can call
3. **Memory**: Built-in session memory with MongoDB storage
4. **Reliability**: Automatic retries and error handling
5. **Streaming**: Native support for streaming responses
6. **Type Safety**: Better type hints and validation

## Testing

```python
# Test the learning agent
from utils.agno_learning_agent import get_learning_agent

agent = get_learning_agent()
result = agent.chat(
    message="How do I solve x + 5 = 12?",
    student_id="S001",
    module={
        'title': 'Linear Equations',
        'subject': 'Mathematics',
        'learning_objectives': ['Solve one-variable equations']
    }
)
print(result['response'])
```
