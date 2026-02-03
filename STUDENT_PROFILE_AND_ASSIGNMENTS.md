# Student Profile and Assignment–Module Linking

## How the student profile is built

The **student learning profile** (strengths, weaknesses, common mistakes, learning style) is maintained per **subject** and is built from two sources:

### 1. Learning chat (My Learning / modules)

- When a student uses the **AI tutor** on a module (learning page chat), the agent can:
  - **record_student_strength** – when the student shows clear mastery of a topic
  - **record_student_weakness** – when they need more work on a topic
  - **record_mistake_pattern** – when a recurring mistake is observed
- The tutor also receives the current profile so it can adapt teaching (e.g. focus on weaknesses, use strengths as anchors).
- Profile is keyed by `student_id` and `subject` (from the root module’s subject).

### 2. Assignments linked to a module

- When you **link an assignment to a module** (optional when creating/editing an assignment), the system uses that assignment to update both **module mastery** and **learning profile** when feedback is sent.
- **When feedback is sent** (teacher sends feedback to student, or AI feedback is sent immediately after submit):
  - **Module mastery**  
    The assignment’s linked module (root) has its **StudentModuleMastery** updated: the student’s mastery score for that module is set from the assignment score percentage (e.g. 75% on the assignment → 75% mastery for that module).
  - **Learning profile**  
    - If score **≥ 80%**: a **strength** is added for that subject (topic = assignment title).
  - If score **< 50%**: a **weakness** is added for that subject (topic = assignment title, notes include score).
- So **every linked assignment** contributes to the same profile and mastery picture used by the learning tutor.

## Linking an assignment to a module

- In **Create Assignment** or **Edit Assignment**, in Basic Information you’ll see **“Link to module (optional)”**.
- The dropdown lists **all your module trees** (root modules), including **draft (unpublished)** ones.
- You can link an assignment to a module even if that module is not yet published to students. When you later publish the module, students will see it; assignment results already recorded will have updated their mastery and profile for that module/subject.
- Choosing **“— No link —”** means the assignment does not update module mastery or profile; it only affects assignment/submission views.

## Summary

| Source              | Updates module mastery? | Updates learning profile? |
|---------------------|-------------------------|----------------------------|
| Learning chat       | Yes (via agent tools)   | Yes (strengths/weaknesses/mistakes) |
| Linked assignment   | Yes (when feedback sent)| Yes (strength if ≥80%, weakness if <50%) |

This gives you a single profile per student per subject, built from both **learning interactions** and **assignment results**, so the tutor and reports can use one consistent picture.
