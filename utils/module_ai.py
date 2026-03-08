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
import re
import json
import io
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2."""
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error("Error extracting text from PDF: %s", e)
        return ""


def _extract_and_repair_json(text: str) -> str:
    """Extract JSON from LLM response and apply common repairs. Returns empty string if none found."""
    if not text or not text.strip():
        return ""
    # Strip markdown code blocks
    stripped = text.strip()
    for marker in ("```json", "```"):
        if stripped.startswith(marker):
            stripped = stripped[len(marker):].lstrip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
    # Find first { and extract matching brace
    start = stripped.find("{")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(stripped)):
        c = stripped[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                json_str = stripped[start : i + 1]
                # Remove trailing commas before } or ]
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                # Remove control characters except newline/tab
                json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
                return json_str
    return ""

# Message shown when no API key is configured (teacher or env)
AI_UNAVAILABLE_MSG = (
    "AI service not available. Add your Anthropic API key in Teacher Settings "
    "(Profile → Settings), or set ANTHROPIC_API_KEY in the server environment."
)


def get_claude_client(api_key: Optional[str] = None):
    """Get Anthropic client. Uses api_key if provided, else ANTHROPIC_API_KEY env."""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed; run: pip install anthropic")
        return None
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key or not key.strip():
        return None
    return Anthropic(api_key=key.strip())


def generate_modules_from_syllabus(
    file_content: bytes,
    file_type: str,
    subject: str,
    year_level: str,
    teacher_id: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate hierarchical module structure from uploaded syllabus/scheme of work.

    Args:
        file_content: PDF or Word document bytes
        file_type: 'pdf' or 'docx'
        subject: Subject name
        year_level: e.g., "Secondary 3"
        teacher_id: Owner teacher ID
        api_key: Optional Anthropic API key (e.g. from teacher settings); else uses ANTHROPIC_API_KEY env.

    Returns:
        Dictionary with module tree structure
    """
    client = get_claude_client(api_key=api_key)
    if not client:
        return {"error": AI_UNAVAILABLE_MSG}

    try:
        content = []

        if file_type == 'pdf':
            # Extract text from PDF (Claude API doesn't accept PDF as image)
            pdf_text = _extract_text_from_pdf(file_content)
            if not pdf_text.strip():
                return {"error": "Could not extract text from PDF. The PDF may contain only images or be corrupted."}
            content.append({
                "type": "text",
                "text": f"SYLLABUS/SCHEME OF WORK DOCUMENT:\n\n{pdf_text}",
            })
        else:
            content.append({
                "type": "text",
                "text": f"[Document content for {subject} - upload PDF for full analysis]",
            })

        system_prompt = f"""You are an expert curriculum designer. Analyze this syllabus/scheme of work and create a Learning Objective (LO) based module structure for {subject} ({year_level}).

STRUCTURE (3 levels only — Subject → Topic → Learning Objective):
1. ROOT: The entire subject/course (depth 0)
2. TOPICS: Major topics or units from the syllabus (depth 1). Use the exact topic headings from the document.
3. LEARNING OBJECTIVES (leaves): Individual, assessable learning outcomes (depth 2). Each LO is ONE specific thing a student should be able to do.

CRITICAL RULES:
- Leaf nodes MUST be individual learning objectives, NOT sub-topics or categories
- Each leaf has an "lo_code" field — a hierarchical code like "1.1.1", "1.2.3", "2.1.1" etc.
  - First number = topic number, second = section within topic, third = LO within section
  - If the syllabus already uses numbering (e.g. "1.1.1", "1.2.4") or lettering (e.g. "a", "b", "c"), preserve those codes exactly
- Each leaf "title" should be the LO statement (e.g. "Perform calculations using bits, bytes, kilobytes...")
- Keep the title concise but complete — it IS the learning objective
- Do NOT create a 4th level — if the syllabus has sub-items under an LO (e.g. "i. primary cell culture, ii. cell lines"), include them in the LO's description, not as children
- Maximum depth: 3 levels (root + topics + LOs)
- Include estimated hours for each node

VISUALIZATION:
- Assign colors that group related topics (hex codes like #667eea)
- Use "icon" field with Bootstrap icon names like "bi-calculator", "bi-book"

Respond ONLY with valid JSON in this exact format (no markdown code fence):
{{
    "root": {{
        "title": "{subject} ({year_level})",
        "description": "Complete curriculum for {subject}",
        "estimated_hours": 150,
        "color": "#667eea",
        "icon": "bi-diagram-3",
        "children": [
            {{
                "title": "1. Computer Architecture",
                "description": "...",
                "estimated_hours": 10,
                "color": "#764ba2",
                "icon": "bi-cpu",
                "lo_code": "1",
                "children": [
                    {{
                        "title": "Perform calculations using bits, bytes, kilobytes, megabytes...",
                        "description": "Including kibibytes, mebibytes, gibibytes, tebibytes, pebibytes",
                        "estimated_hours": 2,
                        "color": "#8b5cf6",
                        "icon": "bi-calculator",
                        "lo_code": "1.1.1",
                        "is_leaf": true
                    }},
                    {{
                        "title": "Describe the function of key components of a computer system",
                        "description": "Processor, main memory and secondary storage",
                        "estimated_hours": 2,
                        "color": "#8b5cf6",
                        "icon": "bi-book",
                        "lo_code": "1.1.2",
                        "is_leaf": true
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
Respond with valid JSON only (no markdown, no text outside the JSON). Escape any double quotes inside string values with backslash.""",
        })

        # JSON schema for structured output (guarantees valid JSON from Claude)
        module_schema = {
            "type": "object",
            "properties": {
                "root": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "estimated_hours": {"type": "number"},
                        "color": {"type": "string"},
                        "icon": {"type": "string"},
                        "lo_code": {"type": "string"},
                        "learning_objectives": {"type": "array", "items": {"type": "string"}},
                        "children": {"type": "array", "items": {"$ref": "#/$defs/module"}},
                        "is_leaf": {"type": "boolean"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
                "total_modules": {"type": "integer"},
                "total_hours": {"type": "number"},
            },
            "required": ["root"],
            "additionalProperties": False,
            "$defs": {
                "module": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "estimated_hours": {"type": "number"},
                        "color": {"type": "string"},
                        "icon": {"type": "string"},
                        "lo_code": {"type": "string"},
                        "learning_objectives": {"type": "array", "items": {"type": "string"}},
                        "children": {"type": "array", "items": {"$ref": "#/$defs/module"}},
                        "is_leaf": {"type": "boolean"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
            },
        }

        create_kwargs = {
            "model": "claude-opus-4-6",
            "max_tokens": 20000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        create_kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": module_schema},
        }

        used_structured = False
        try:
            message = client.messages.create(**create_kwargs)
            used_structured = True
        except Exception as api_err:
            # If structured output is rejected (e.g. schema too complex), retry without it
            logger.warning("Structured output failed, retrying without: %s", api_err)
            create_kwargs.pop("output_config", None)
            message = client.messages.create(**create_kwargs)

        response_text = message.content[0].text
        json_str = response_text.strip() if used_structured else _extract_and_repair_json(response_text)

        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as je:
                logger.error("JSON parse error: %s\nRaw (first 2000 chars): %s", je, json_str[:2000])
                return {'error': f'AI returned invalid JSON. Please try again. (Parse error: {je.msg} at position {je.pos})'}
        return {'error': 'Could not parse module structure from AI response'}

    except Exception as e:
        logger.error("Error generating modules: %s", e)
        return {'error': str(e)}


def assess_student_understanding(
    student_message: str,
    module: Dict,
    chat_history: List[Dict],
    student_profile: Optional[Dict] = None,
    writing_image: Optional[bytes] = None,
    textbook_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    AI learning agent that assesses student understanding and provides teaching.

    Args:
        student_message: Student's chat message or question
        module: Current module being studied
        chat_history: Previous messages in this session
        student_profile: Student's learning profile (strengths/weaknesses)
        writing_image: Optional image of student's handwritten work
        textbook_context: Optional RAG passages from the course textbook to ground answers

    Returns:
        Dictionary with response, assessment, and profile updates
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    try:
        profile_context = ""
        if student_profile:
            strengths = ", ".join([s.get('topic', '') for s in student_profile.get('strengths', [])])
            weaknesses = ", ".join([w.get('topic', '') for w in student_profile.get('weaknesses', [])])
            profile_context = f"""
STUDENT PROFILE:
- Strengths: {strengths or 'Not yet identified'}
- Areas needing work: {weaknesses or 'Not yet identified'}
- Learning style: {student_profile.get('learning_style', 'Unknown')}
- Common mistakes: {', '.join([m.get('pattern', '') for m in student_profile.get('common_mistakes', [])])}
"""

        custom_prompt = (module.get('custom_prompt') or '').strip()
        custom_block = ""
        if custom_prompt:
            custom_block = f"""
TEACHER'S CUSTOM PROMPT FOR THIS MODULE (follow these instructions):
{custom_prompt}

"""
        book_block = ""
        if textbook_context and textbook_context.strip():
            book_block = f"""
RELEVANT TEXTBOOK PASSAGES (use these to ground your answer when appropriate):
{textbook_context}

"""
        system_prompt = f"""You are an expert, patient tutor helping a student learn.

CURRENT MODULE: {module.get('title', 'Unknown')}
LEARNING OBJECTIVES: {', '.join(module.get('learning_objectives', []))}
{custom_block}{book_block}{profile_context}

YOUR ROLE:
1. TEACH: Explain concepts clearly, use examples, adapt to student's level
2. ASSESS: Ask questions to check understanding, identify misconceptions
3. ENCOURAGE: Be supportive, celebrate progress, build confidence
4. ADAPT: Use the student's learning profile to personalize teaching

ASSESSMENT GUIDELINES:
- After teaching a concept, ask a question to assess understanding
- If student answers correctly: Award mastery points (mastery_change 1-10), move to next concept
- If student struggles: Provide hints, break down the problem, try different explanations
- Note any patterns in mistakes for profile updates

RESPONSE FORMAT - Respond with valid JSON only (no markdown):
{{
    "response": "Your teaching response to the student (use markdown for formatting, include examples)",
    "response_type": "teaching",
    "assessment": {{
        "question_asked": "The assessment question if any",
        "student_answer_correct": true,
        "mastery_change": 5,
        "concept_assessed": "Specific concept tested"
    }},
    "profile_updates": {{
        "new_strength": null,
        "new_weakness": null,
        "new_mistake_pattern": null
    }},
    "next_action": "continue_teaching",
    "interactive_element": null
}}

Use "response_type" one of: teaching, assessment, feedback, encouragement.
Use "mastery_change" between -10 and 10. Use "next_action" one of: continue_teaching, assess_understanding, review_previous, module_complete."""

        messages_content = []

        if chat_history:
            history_text = "\n".join([
                f"{'Student' if m.get('role') == 'student' else 'Tutor'}: {m.get('content', '')}"
                for m in chat_history[-10:]
            ])
            messages_content.append({
                "type": "text",
                "text": f"RECENT CONVERSATION:\n{history_text}\n\n",
            })

        if writing_image:
            image_b64 = base64.standard_b64encode(writing_image).decode('utf-8')
            messages_content.append({"type": "text", "text": "STUDENT'S HANDWRITTEN WORK:"})
            messages_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            })

        messages_content.append({
            "type": "text",
            "text": f"STUDENT'S MESSAGE: {student_message}\n\nRespond with JSON only:",
        })

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": messages_content}],
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            result['raw_response'] = response_text
            return result

        return {
            'response': response_text,
            'response_type': 'teaching',
            'assessment': None,
            'profile_updates': None,
        }

    except Exception as e:
        logger.error("Error in learning assessment: %s", e)
        return {
            'error': str(e),
            'response': "I'm having trouble right now. Let's try again!",
        }


def generate_interactive_assessment(
    module: Dict,
    difficulty: str = "medium",
    question_type: str = "mixed",
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

Respond with valid JSON only:
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
        }}
    ],
    "total_points": 50,
    "passing_score": 35,
    "time_limit_minutes": 15
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": "Generate the assessment now."}],
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())
        return {'error': 'Could not generate assessment'}

    except Exception as e:
        logger.error("Error generating assessment: %s", e)
        return {'error': str(e)}


def generate_guided_interactive(
    module: Dict,
    concept: str,
    interactive_type: str = "guided_steps",
) -> Dict[str, Any]:
    """
    Generate an on-the-fly interactive to help when the student is unable to understand.
    Types: guided_steps (step-by-step walkthrough), practice_one (one question with feedback),
    order_steps (put steps in correct order).

    Args:
        module: Current module context
        concept: What the student is struggling with (e.g. "solving 2x + 3 = 7")
        interactive_type: "guided_steps" | "practice_one" | "order_steps"

    Returns:
        Structured payload for the frontend to render
    """
    client = get_claude_client()
    if not client:
        return {'error': 'AI service not available'}

    type_instructions = {
        "guided_steps": """Create a "do it together" walkthrough: 3-5 short steps. Each step has "instruction" (what the student should do or think) and optional "hint". Student will click "Next" after each step. Include "title" and "message_after" (encouragement when they finish).""",
        "practice_one": """Create ONE practice item: "question", optional "options" (array of choices for MCQ), "correct_answer" (letter like "B" or the exact short answer), "hint", and "explanation" (shown after they check). Use "title". If no options, student types short answer.""",
        "order_steps": """Create 3-5 steps that must be in a specific order (e.g. steps to solve an equation). Return "steps" as array of strings in RANDOM order, and "correct_order" as array of 0-based indices (e.g. [2,0,1]). Include "title" and "message_after".""",
    }
    instruction = type_instructions.get(
        interactive_type,
        type_instructions["guided_steps"],
    )

    try:
        system_prompt = f"""You are creating a small interactive to help a student who is struggling.

MODULE: {module.get('title')}
LEARNING OBJECTIVES: {', '.join(module.get('learning_objectives', []))}
WHAT THE STUDENT IS STRUGGLING WITH: {concept}
INTERACTIVE TYPE: {interactive_type}

{instruction}

Respond with valid JSON only. No markdown, no text outside the JSON."""

        schema = {
            "guided_steps": {
                "title": "string",
                "steps": [{"instruction": "string", "hint": "string or null"}],
                "message_after": "string",
            },
            "practice_one": {
                "title": "string",
                "question": "string",
                "options": "array of strings or null for short answer",
                "correct_answer": "string (letter like B or exact answer)",
                "hint": "string",
                "explanation": "string",
            },
            "order_steps": {
                "title": "string",
                "steps": ["string", "..."],
                "correct_order": [0, 1, 2],
                "message_after": "string",
            },
        }
        user_content = f"Generate a {interactive_type} interactive. Schema: {schema.get(interactive_type, schema['guided_steps'])}"

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            out = json.loads(json_match.group())
            out["interactive_type"] = interactive_type
            return out
        return {'error': 'Could not generate interactive', 'interactive_type': interactive_type}

    except Exception as e:
        logger.error("Error generating guided interactive: %s", e)
        return {'error': str(e), 'interactive_type': interactive_type}


def analyze_writing_submission(
    image_data: bytes,
    module: Dict,
    expected_content: Optional[str] = None,
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

{('Expected content: ' + expected_content) if expected_content else ''}

Evaluate:
1. Mathematical/logical correctness
2. Clarity of presentation
3. Method and approach used
4. Any errors or misconceptions

Respond with valid JSON only:
{{
    "transcription": "Text version of what's written",
    "analysis": "Detailed analysis of the work",
    "is_correct": true,
    "errors": [],
    "suggestions": [],
    "mastery_indication": 75
}}

Use is_correct: true, false, or "partial". mastery_indication is 0-100."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": "Analyze this handwritten work and respond with JSON only:"},
                    ],
                }
            ],
        )

        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            return json.loads(json_match.group())
        return {'analysis': response_text}

    except Exception as e:
        logger.error("Error analyzing writing: %s", e)
        return {'error': str(e)}


def generate_assignment_from_los(
    selected_los,
    subject,
    num_questions,
    total_marks,
    difficulty,
    question_types,
    additional_instructions,
    teacher,
):
    """Generate assignment questions + answer key from selected Learning Objectives.

    Args:
        selected_los: list of dicts [{title, lo_code, learning_objectives}]
        subject: subject name
        num_questions: number of questions to generate
        total_marks: total marks for the assignment
        difficulty: easy/medium/hard/mixed
        question_types: mcq/short_answer/structured/mixed
        additional_instructions: free-text teacher instructions
        teacher: teacher document (for AI provider resolution)

    Returns:
        dict with keys: questions (list), title_suggestion (str)
        Each question: {number, text, marks, answer, lo_code, type}
    """
    from utils.ai_marking import get_teacher_ai_service

    model_type = teacher.get('default_ai_model', 'anthropic') if teacher else 'anthropic'
    client, model_name, provider = get_teacher_ai_service(teacher, model_type)
    if not client:
        return {'error': AI_UNAVAILABLE_MSG}

    lo_descriptions = []
    for lo in selected_los:
        code = lo.get('lo_code', '')
        title = lo.get('title', '')
        objectives = lo.get('learning_objectives', [])
        obj_text = '; '.join(objectives) if objectives else ''
        lo_descriptions.append(f"- [{code}] {title}" + (f" (Objectives: {obj_text})" if obj_text else ''))

    lo_block = '\n'.join(lo_descriptions)

    system_prompt = f"""You are an expert teacher creating a {subject} assignment.

LEARNING OBJECTIVES TO ASSESS:
{lo_block}

CONSTRAINTS:
- Number of questions: {num_questions}
- Total marks: {total_marks} (distribute marks across questions proportionally)
- Difficulty: {difficulty}
- Question types: {question_types}
{('- Additional instructions: ' + additional_instructions) if additional_instructions else ''}

RULES:
- Each question must clearly test one or more of the listed learning objectives
- Include the lo_code for the primary LO each question targets
- For MCQ questions, provide 4 options labeled A-D
- For short_answer questions, provide the expected answer
- For structured questions, break into parts (a), (b), etc. and provide detailed answers
- Distribute marks to total exactly {total_marks}
- Vary question difficulty according to the "{difficulty}" setting
- Suggest a concise assignment title

Respond with valid JSON only:
{{
    "title_suggestion": "Chapter X: Topic Name",
    "questions": [
        {{
            "number": 1,
            "text": "Full question text here",
            "marks": 5,
            "answer": "Full model answer or correct option",
            "lo_code": "1.1.1",
            "type": "mcq|short_answer|structured",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."]
        }}
    ]
}}

The "options" field should only be present for MCQ questions. Omit it for other types."""

    try:
        if provider == 'anthropic':
            message = client.messages.create(
                model=model_name,
                max_tokens=8000,
                system=system_prompt,
                messages=[{"role": "user", "content": "Generate the assignment now. Respond with JSON only."}],
            )
            response_text = message.content[0].text
        elif provider in ('openai', 'deepseek'):
            response = client.chat.completions.create(
                model=model_name,
                max_tokens=8000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate the assignment now. Respond with JSON only."},
                ],
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content
        elif provider == 'google':
            model = client.GenerativeModel(model_name)
            response = model.generate_content(
                system_prompt + "\n\nGenerate the assignment now. Respond with JSON only.",
                generation_config={"response_mime_type": "application/json", "max_output_tokens": 8000},
            )
            response_text = response.text
        else:
            return {'error': f'Unsupported provider: {provider}'}

        json_str = _extract_and_repair_json(response_text) if response_text else ''
        if json_str:
            result = json.loads(json_str)
            if 'questions' not in result:
                return {'error': 'AI response missing questions field'}
            return result
        return {'error': 'Could not parse AI response'}

    except Exception as e:
        logger.error("Error generating assignment from LOs: %s", e)
        return {'error': str(e)}


def modify_assignment_content(
    original_text,
    original_assignment,
    modification_type,
    modification_level,
    custom_instructions,
    teacher,
):
    """Generate a modified version of an existing assignment.

    Args:
        original_text: extracted question paper text
        original_assignment: assignment metadata dict
        modification_type: difficulty/format/topic_focus/language_level
        modification_level: slight/moderate/significant
        custom_instructions: free-text teacher instructions
        teacher: teacher document (for AI provider resolution)

    Returns:
        dict with keys: questions (list), title_suggestion (str)
    """
    from utils.ai_marking import get_teacher_ai_service

    model_type = teacher.get('default_ai_model', 'anthropic') if teacher else 'anthropic'
    client, model_name, provider = get_teacher_ai_service(teacher, model_type)
    if not client:
        return {'error': AI_UNAVAILABLE_MSG}

    subject = original_assignment.get('subject', 'General')
    total_marks = original_assignment.get('total_marks', 100)
    title = original_assignment.get('title', 'Untitled')

    modification_descriptions = {
        'difficulty': {
            'slight': 'Make the questions slightly easier or harder (adjust complexity of 1-2 questions)',
            'moderate': 'Noticeably change the difficulty level across most questions',
            'significant': 'Substantially rework all questions to a different difficulty level',
        },
        'format': {
            'slight': 'Change the format of 1-2 questions (e.g., MCQ to short answer)',
            'moderate': 'Restructure most questions into different formats while keeping the same content',
            'significant': 'Completely reformat all questions into different types',
        },
        'topic_focus': {
            'slight': 'Shift emphasis slightly toward different aspects of the same topics',
            'moderate': 'Change context/scenarios while testing the same concepts',
            'significant': 'Create entirely new questions on the same topics with different angles',
        },
        'language_level': {
            'slight': 'Simplify or complexify the language slightly',
            'moderate': 'Rewrite questions with noticeably different vocabulary and sentence structure',
            'significant': 'Completely rewrite for a different language proficiency level',
        },
    }

    mod_desc = modification_descriptions.get(modification_type, {}).get(
        modification_level, 'Modify the assignment as specified'
    )

    system_prompt = f"""You are an expert teacher modifying an existing {subject} assignment.

ORIGINAL ASSIGNMENT: "{title}"
Total marks: {total_marks}

ORIGINAL QUESTION PAPER TEXT:
{original_text}

MODIFICATION REQUESTED:
Type: {modification_type}
Level: {modification_level}
Description: {mod_desc}
{('Custom instructions: ' + custom_instructions) if custom_instructions else ''}

RULES:
- Maintain the same total marks ({total_marks})
- Keep the same number of questions unless the modification requires changing it
- Ensure the modified version is a distinct paper (not just reworded identically)
- For MCQ questions, provide 4 options labeled A-D
- Suggest a title for the modified version
- Include complete model answers for each question

Respond with valid JSON only:
{{
    "title_suggestion": "Modified version title",
    "questions": [
        {{
            "number": 1,
            "text": "Full question text",
            "marks": 5,
            "answer": "Full model answer",
            "type": "mcq|short_answer|structured",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."]
        }}
    ]
}}

The "options" field should only be present for MCQ questions."""

    try:
        if provider == 'anthropic':
            message = client.messages.create(
                model=model_name,
                max_tokens=8000,
                system=system_prompt,
                messages=[{"role": "user", "content": "Generate the modified assignment now. Respond with JSON only."}],
            )
            response_text = message.content[0].text
        elif provider in ('openai', 'deepseek'):
            response = client.chat.completions.create(
                model=model_name,
                max_tokens=8000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate the modified assignment now. Respond with JSON only."},
                ],
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content
        elif provider == 'google':
            model = client.GenerativeModel(model_name)
            response = model.generate_content(
                system_prompt + "\n\nGenerate the modified assignment now. Respond with JSON only.",
                generation_config={"response_mime_type": "application/json", "max_output_tokens": 8000},
            )
            response_text = response.text
        else:
            return {'error': f'Unsupported provider: {provider}'}

        json_str = _extract_and_repair_json(response_text) if response_text else ''
        if json_str:
            result = json.loads(json_str)
            if 'questions' not in result:
                return {'error': 'AI response missing questions field'}
            return result
        return {'error': 'Could not parse AI response'}

    except Exception as e:
        logger.error("Error modifying assignment: %s", e)
        return {'error': str(e)}
