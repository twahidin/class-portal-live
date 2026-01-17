import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

logger = logging.getLogger(__name__)

# Colors
PRIMARY_COLOR = HexColor('#667eea')
SECONDARY_COLOR = HexColor('#764ba2')
TEXT_COLOR = HexColor('#333333')
LIGHT_GRAY = HexColor('#f5f5f5')
BORDER_COLOR = HexColor('#e0e0e0')

def get_styles():
    """Get custom paragraph styles"""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='Title_Custom',
        parent=styles['Title'],
        fontSize=24,
        textColor=PRIMARY_COLOR,
        spaceAfter=30,
        alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name='Heading_Custom',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=PRIMARY_COLOR,
        spaceBefore=20,
        spaceAfter=10
    ))
    
    styles.add(ParagraphStyle(
        name='SubHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=SECONDARY_COLOR,
        spaceBefore=15,
        spaceAfter=8
    ))
    
    styles.add(ParagraphStyle(
        name='Body_Custom',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXT_COLOR,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        leading=14
    ))
    
    styles.add(ParagraphStyle(
        name='Question',
        parent=styles['Normal'],
        fontSize=11,
        textColor=TEXT_COLOR,
        spaceBefore=15,
        spaceAfter=5,
        leftIndent=0,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='Answer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXT_COLOR,
        spaceBefore=5,
        spaceAfter=5,
        leftIndent=20,
        borderColor=BORDER_COLOR,
        borderWidth=1,
        borderPadding=8
    ))
    
    styles.add(ParagraphStyle(
        name='Feedback',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor('#1a5f2a'),
        spaceBefore=5,
        spaceAfter=10,
        leftIndent=20,
        backColor=HexColor('#e8f5e9'),
        borderPadding=8
    ))
    
    styles.add(ParagraphStyle(
        name='Score',
        parent=styles['Normal'],
        fontSize=11,
        textColor=PRIMARY_COLOR,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER
    ))
    
    return styles

def generate_feedback_pdf(submission: dict, assignment: dict, student: dict) -> bytes:
    """
    Generate a PDF feedback report for a submission
    
    Args:
        submission: The submission document with answers and feedback
        assignment: The assignment document with questions
        student: The student document
    
    Returns:
        PDF content as bytes
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    story = []
    
    # Title
    story.append(Paragraph("Assignment Feedback Report", styles['Title_Custom']))
    story.append(Spacer(1, 10))
    
    # Student and assignment info
    info_data = [
        ['Student:', student.get('name', 'Unknown')],
        ['Student ID:', student.get('student_id', 'N/A')],
        ['Class:', student.get('class', 'N/A')],
        ['Assignment:', assignment.get('title', 'Untitled')],
        ['Subject:', assignment.get('subject', 'N/A')],
        ['Submitted:', submission.get('submitted_at', datetime.utcnow()).strftime('%d %B %Y, %H:%M') if isinstance(submission.get('submitted_at'), datetime) else str(submission.get('submitted_at', 'N/A'))],
    ]
    
    info_table = Table(info_data, colWidths=[2.5*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXT_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Divider
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR))
    story.append(Spacer(1, 20))
    
    # Questions and Answers
    story.append(Paragraph("Questions & Responses", styles['Heading_Custom']))
    
    questions = assignment.get('questions', [])
    answers = submission.get('answers', {})
    ai_feedback = submission.get('ai_feedback', {})
    teacher_review = submission.get('teacher_review', {})
    
    for i, q in enumerate(questions, 1):
        # Question
        question_text = q.get('question', q.get('text', f'Question {i}'))
        marks = q.get('marks', 0)
        story.append(Paragraph(f"Q{i}. {question_text} [{marks} marks]", styles['Question']))
        
        # Student Answer
        answer = answers.get(str(i), answers.get(f'q{i}', 'No answer provided'))
        story.append(Paragraph(f"<b>Your Answer:</b> {answer}", styles['Answer']))
        
        # Score if available
        q_feedback = teacher_review.get('questions', {}).get(str(i), {})
        if q_feedback.get('score') is not None:
            story.append(Paragraph(f"Score: {q_feedback['score']}/{marks}", styles['Score']))
        
        story.append(Spacer(1, 10))
    
    # Overall Feedback
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER_COLOR))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Feedback & Assessment", styles['Heading_Custom']))
    
    # AI Feedback
    if ai_feedback.get('overall'):
        story.append(Paragraph("AI-Generated Feedback:", styles['SubHeading']))
        # Clean up the feedback text for PDF
        feedback_text = ai_feedback['overall'].replace('\n', '<br/>')
        story.append(Paragraph(feedback_text, styles['Body_Custom']))
    
    # Teacher Review
    if teacher_review.get('comments'):
        story.append(Spacer(1, 15))
        story.append(Paragraph("Teacher's Comments:", styles['SubHeading']))
        story.append(Paragraph(teacher_review['comments'], styles['Feedback']))
    
    # Final Score
    if teacher_review.get('final_score') is not None:
        story.append(Spacer(1, 20))
        total_marks = assignment.get('total_marks', 100)
        score = teacher_review['final_score']
        percentage = (score / total_marks * 100) if total_marks > 0 else 0
        
        score_data = [
            ['Final Score', f"{score} / {total_marks}", f"{percentage:.1f}%"]
        ]
        score_table = Table(score_data, colWidths=[4*cm, 4*cm, 4*cm])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PRIMARY_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, -1), HexColor('#ffffff')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 15),
            ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ]))
        story.append(score_table)
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER_COLOR))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated on {datetime.utcnow().strftime('%d %B %Y at %H:%M UTC')}",
        ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=HexColor('#888888'),
            alignment=TA_CENTER
        )
    ))
    
    # Build PDF
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        return None

def generate_assignment_pdf(assignment: dict, teacher: dict = None) -> bytes:
    """
    Generate a PDF version of an assignment (for printing/distribution)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = get_styles()
    story = []
    
    # Title
    story.append(Paragraph(assignment.get('title', 'Assignment'), styles['Title_Custom']))
    
    # Info
    story.append(Paragraph(f"Subject: {assignment.get('subject', 'N/A')}", styles['Body_Custom']))
    story.append(Paragraph(f"Total Marks: {assignment.get('total_marks', 0)}", styles['Body_Custom']))
    
    if assignment.get('due_date'):
        due_date = assignment['due_date']
        if isinstance(due_date, datetime):
            due_date = due_date.strftime('%d %B %Y')
        story.append(Paragraph(f"Due Date: {due_date}", styles['Body_Custom']))
    
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR))
    story.append(Spacer(1, 20))
    
    # Instructions
    if assignment.get('instructions'):
        story.append(Paragraph("Instructions:", styles['SubHeading']))
        story.append(Paragraph(assignment['instructions'], styles['Body_Custom']))
        story.append(Spacer(1, 15))
    
    # Questions
    story.append(Paragraph("Questions", styles['Heading_Custom']))
    
    for i, q in enumerate(assignment.get('questions', []), 1):
        question_text = q.get('question', q.get('text', ''))
        marks = q.get('marks', 0)
        story.append(Paragraph(f"Q{i}. {question_text} [{marks} marks]", styles['Question']))
        story.append(Spacer(1, 30))  # Space for answer
    
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error generating assignment PDF: {e}")
        return None
