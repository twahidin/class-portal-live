import os
import logging
from anthropic import Anthropic
from utils.auth import decrypt_api_key

logger = logging.getLogger(__name__)

def get_teacher_ai_service(teacher):
    """Get AI service configured for a specific teacher"""
    api_key = None
    
    # Try teacher's personal API key first
    if teacher and teacher.get('anthropic_api_key'):
        api_key = decrypt_api_key(teacher['anthropic_api_key'])
    
    # Fall back to system API key
    if not api_key:
        api_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not api_key:
        logger.warning("No Anthropic API key available")
        return None
    
    try:
        return Anthropic(api_key=api_key)
    except Exception as e:
        logger.error(f"Error creating Anthropic client: {e}")
        return None

def mark_submission(submission: dict, assignment: dict, teacher: dict = None) -> dict:
    """
    Use AI to mark a student submission and provide feedback
    
    Args:
        submission: The student's submission with answers
        assignment: The assignment with questions and marking criteria
        teacher: Optional teacher document for API key
    
    Returns:
        Dictionary with feedback for each question and overall assessment
    """
    client = get_teacher_ai_service(teacher)
    if not client:
        return {
            'error': 'AI service not available',
            'questions': {},
            'overall': 'Unable to generate AI feedback - no API key configured'
        }
    
    try:
        # Build the prompt
        questions_text = ""
        for i, q in enumerate(assignment.get('questions', []), 1):
            answer = submission.get('answers', {}).get(str(i), submission.get('answers', {}).get(f'q{i}', 'No answer provided'))
            questions_text += f"""
Question {i}: {q.get('question', q.get('text', ''))}
Marks: {q.get('marks', 0)}
{"Model Answer: " + q.get('model_answer', '') if q.get('model_answer') else ""}
Student Answer: {answer}
---
"""
        
        prompt = f"""You are an experienced teacher marking a student assignment. 
Please evaluate the following submission and provide constructive feedback.

Assignment: {assignment.get('title', 'Untitled')}
Subject: {assignment.get('subject', 'General')}
Total Marks: {assignment.get('total_marks', 0)}

{questions_text}

For each question, provide:
1. A score out of the available marks
2. What the student did well
3. Areas for improvement
4. Specific suggestions for better answers

Then provide an overall summary with:
- Total score
- Strengths demonstrated
- Areas needing work
- Encouragement and next steps

Format your response as structured feedback that a student would find helpful and encouraging.
Be specific in your comments and reference the actual content of their answers."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        feedback_text = message.content[0].text
        
        # Parse the response into structured feedback
        result = {
            'raw_feedback': feedback_text,
            'questions': {},
            'overall': '',
            'generated_at': None
        }
        
        # Simple parsing - in production you'd want more sophisticated parsing
        from datetime import datetime
        result['generated_at'] = datetime.utcnow().isoformat()
        result['overall'] = feedback_text
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating AI feedback: {e}")
        return {
            'error': str(e),
            'questions': {},
            'overall': f'Error generating feedback: {str(e)}'
        }

def get_quick_feedback(answer: str, question: str, model_answer: str = None, teacher: dict = None) -> str:
    """
    Get quick feedback on a single answer (for draft saving)
    """
    client = get_teacher_ai_service(teacher)
    if not client:
        return "AI feedback not available"
    
    try:
        prompt = f"""Provide brief, constructive feedback (2-3 sentences) on this student answer.

Question: {question}
{"Model Answer: " + model_answer if model_answer else ""}
Student Answer: {answer}

Give specific, helpful feedback focusing on what's good and what could be improved."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
        
    except Exception as e:
        logger.error(f"Error getting quick feedback: {e}")
        return f"Unable to generate feedback: {str(e)}"
