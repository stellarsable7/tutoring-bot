# Telegram Additional Mathematics Practice Bot

## Summary

Build a Telegram bot that assigns daily Singapore-Cambridge GCE O-Level Additional Mathematics questions to a tutor's students, accepts handwritten solutions, and returns provisional exam-style marks with line-by-line feedback. The first release supports one tutor and multiple invited students targeting the 2026 Additional Mathematics syllabus 4049.

The bot uses questions from public paper repositories such as Holy Grail by linking students to the original source, paper, and question number. It does not reproduce the paper. A question is eligible only when the same source set contains a published worked solution or mark scheme. The system never invents an answer key, worked solution, or mark scheme.

## Goals

- Map all assignments to the official 2026 syllabus 4049.
- Let the tutor control the curriculum sequence while adapting difficulty and revision to each student.
- Send one question by default, with a tutor-configurable daily question count.
- Accept multiple photos or a PDF containing handwritten working.
- Allocate answer, method, and accuracy marks using a published worked solution or mark scheme.
- Return provisional line-by-line feedback without revealing answers, corrected working, or model solutions.
- Route ambiguous marking decisions to the tutor inside Telegram.
- Retain useful progress data while deleting submission images after processing.
- Validate both marking accuracy and student completion during the pilot.

## Non-goals for the first release

- Multiple independent tutor accounts or tenant isolation
- Billing or subscriptions
- A tutor web dashboard
- Support for the 2027 SEC G3 K341 syllabus
- Reproduction or hidden redistribution of third-party papers
- AI-generated answer keys, worked solutions, or mark schemes
- Bot-delivered corrections, answers, or model solutions
- Fully autonomous, definitive marking without tutor oversight

## Users and roles

### Tutor

One allowlisted Telegram account administers students, schedules, topics, assignments, and marking reviews. The tutor can approve or override every provisional result.

### Student

A student joins with a tutor-issued, single-use invite code. The student receives scheduled assignments, submits handwritten work, and sees provisional marks and diagnostic feedback.

## System architecture

The system is divided into independently testable services with explicit interfaces.

### Syllabus service

Stores a versioned, structured representation of the official 2026 Additional Mathematics syllabus 4049. It exposes topic and learning-objective identifiers used by the catalogue, assignment engine, and mastery model. The broad domains are algebra, geometry and trigonometry, and calculus.

### Source catalogue

Indexes eligible source questions without republishing their papers. Each record contains:

- Source URL, provider, school, year, paper, and question number
- Primary and supporting syllabus objectives
- Estimated difficulty, expected time, and total marks
- Prerequisites and calculator or diagram requirements
- Published solution or mark-scheme URL and provenance
- Structured mark allocations parsed from the published solution
- Availability and validation status

An item is assignable only when its question source and published worked solution or mark scheme are reachable and its content is within syllabus 4049. A final-answer-only key is insufficient. The system does not fill gaps by deriving an answer or scheme.

### Assignment engine

The tutor selects the current topic sequence and may pin, exclude, pause, or directly assign items. Within that scope, the engine ranks questions using topic mastery, recent errors, completion history, overdue revision, difficulty, and prior exposure.

The engine prevents accidental repetition of the exact same source item. It deliberately uses near-transfer questions with similar concepts and methods when remediating a weak point, then broadens the framing as mastery improves. It schedules spaced review after success. The tutor may explicitly reassign an exact question.

### Telegram bot

The bot is the only user interface in the first release. It manages onboarding, consent, assignment delivery, submission grouping, progress messages, tutor controls, and marking review.

### Submission processor

Accepts multiple images or one PDF, preserves page order, checks image quality and completeness, and creates a short-lived encrypted processing bundle. It rejects or requests replacement media when the working cannot be read reliably.

### Hybrid marking pipeline

The pipeline uses three distinct forms of evidence:

1. A vision model transcribes the student's working line by line and records recognition confidence.
2. A symbolic mathematics engine checks calculations, equivalence, and valid transformations where supported.
3. A reasoning model maps the transcribed work to the published solution and its mark allocations, recording marking confidence and evidence for every awarded or withheld mark.

Recognition confidence and mathematical-marking confidence remain separate. The reasoning model may recognise a valid alternative method, but it cannot change the authoritative answer or fabricate missing criteria. A valid-looking method not clearly covered by the published scheme is routed to the tutor.

### Student record

Stores assignments, structured transcriptions, marks, confidence values, feedback, tutor overrides, completion events, and topic mastery. Original submission images and PDFs are deleted when marking is finalized. Tutor corrections are retained as calibration examples but never silently modify the source scheme.

### Scheduler and job queue

Schedules assignments in Asia/Singapore time, defaults to one question per assignment, and supports tutor-configurable weekdays, time, and question count. Durable jobs handle assignment delivery, submission processing, marking, media deletion, and retryable notifications.

## Student flow

1. The student runs `/start`, supplies a single-use invite code, reviews the privacy notice, and records consent.
2. At the scheduled time, the bot sends the original source link, paper identity, exact question number, marks, and expected time.
3. The student opens the linked paper, completes the question on paper, then uploads one or more photos or a PDF.
4. The bot groups uploads until the student taps **Submit attempt**.
5. The submission processor checks clarity, page order, and apparent completeness. It requests replacement media when necessary.
6. The marking pipeline produces a provisional score and feedback or queues the submission for tutor review.
7. The student receives the provisional total and line-by-line comments describing what earned or lost marks. Feedback does not contain answers, corrected steps, or model working.
8. Corrections and solutions are discussed with the tutor outside the bot.

## Tutor flow and commands

- `/students`: show completion, current topic, recent marks, and flags.
- `/schedule`: configure delivery time, weekdays, default question count, and topic sequence.
- `/assign`: send or schedule a specific eligible question.
- `/review`: inspect flagged attempts with media while it is still available, transcription, published scheme reference, proposed marks, evidence, and confidence.
- Review buttons: approve, edit marks, replace feedback, or request another upload.
- `/progress`: show mastery, completion rate, common errors, and pending reviews.
- `/pause`: pause one student or all assignments.

Sensitive tutor actions require confirmation. Tutor-only commands are restricted to the allowlisted Telegram account.

## Marking and feedback rules

- Every result is provisional when first produced.
- Marks must cite the relevant published marking step internally.
- The bot provides per-line diagnostic comments but never an answer, correction, model solution, or newly derived scheme.
- Follow-through marks may be awarded when supported by the published scheme and verified work.
- Recognition ambiguity is never treated as a mathematical error without review.
- A review flag is mandatory when:
  - handwriting or notation is ambiguous;
  - the symbolic checker and reasoning model disagree;
  - the student uses a plausible valid method absent from the published scheme;
  - page completeness is uncertain;
  - confidence falls below the configured threshold.
- A provisional label remains until the tutor approves the result or the configured review window expires. Expiry does not convert a low-confidence result into a high-confidence one.

## Privacy and data handling

- Collect only the Telegram identifier, display name, syllabus assignment, schedule, consent record, and learning history necessary for the service.
- Define responsibility for obtaining any required parent or guardian consent because students may be minors.
- Download media into short-lived encrypted storage.
- Use an AI provider configuration that does not use submission media for model training and supports appropriate retention controls.
- Delete local submission media immediately when marking is finalized. A clear, high-confidence attempt is finalized after automated marking; a flagged attempt is finalized after tutor review. Flagged media has an absolute 24-hour retention limit, after which it is deleted and the unresolved attempt is closed without a definitive mark.
- Ask Telegram to delete bot-accessible media messages where supported, while clearly stating that the product cannot guarantee removal from Telegram's own infrastructure.
- Exclude images and full transcriptions from application logs.
- Encrypt retained data in transit and at rest and restrict production access.

## Failure handling

- **Unreadable media:** request a clearer upload before marking.
- **Missing or unordered pages:** ask the student to confirm and reorder the submission.
- **Unavailable question or solution source:** make the item unassignable and select another item.
- **Model disagreement or ambiguity:** preserve the provisional result and queue tutor review.
- **Flag not reviewed within 24 hours:** delete the media, keep the attempt unresolved, and ask the student for a new submission if the tutor still needs to mark it.
- **AI provider outage:** retain the encrypted submission in the durable queue, notify the student of a delay, and retry with limits.
- **Delivery failure:** retry transient errors and alert the tutor after repeated failure.
- **Media deletion failure:** retry as a high-priority privacy job and alert the operator.
- **Student inactivity:** send a limited number of reminders, then surface the missed assignment to the tutor.

## Testing strategy

Create a tutor-labelled evaluation set covering clear and messy handwriting, multiple valid methods, crossed-out work, missing steps, weak images, multi-page submissions, and commonly confused notation. Use student work only with appropriate consent.

Automated and integration tests cover:

- Syllabus tagging and out-of-syllabus rejection
- Source and published-solution validation
- Accidental exact-duplicate prevention and intentional remediation selection
- Multi-image and PDF grouping
- Mathematical transcription and confidence tracking
- Symbolic equivalence and follow-through marking
- Scheme-to-evidence traceability
- Review thresholds and tutor overrides
- Telegram permissions, commands, scheduling, and retries
- Media lifecycle, deletion, and privacy-safe logging
- Prevention of answers or corrected working in student feedback

## Pilot launch gates

- Every assigned question has a reachable original source and published worked solution or mark scheme.
- At least 95% of total scores are within one mark of the tutor's score on the evaluation set.
- At least 90% of total scores exactly match the tutor's score.
- All materially ambiguous submissions in the evaluation set are flagged rather than confidently auto-marked.
- Student feedback contains no answer, corrected working, or model solution.
- Media deletion and access-control tests pass end to end.

## Pilot metrics

Run the pilot for four weeks and evaluate both marking reliability and student participation:

- Exact agreement and within-one-mark agreement with tutor marking
- Tutor override and review rates
- Average tutor review time per submission
- Assignment completion and on-time submission rates
- Topic-level performance and recovery after remediation
- Student drop-off and reminder effectiveness
- Processing failures and media-deletion failures

The pilot succeeds when it reduces tutor marking time, meets the marking launch gates, and sustains useful student completion without weakening tutor trust.

## Authoritative references

- [SEAB: 2026 school-candidate O-Level syllabuses](https://www.seab.gov.sg/gce-o-level/o-level-syllabuses-examined-for-school-candidates-2026/)
- [SEAB: 2026 Additional Mathematics syllabus 4049](https://www.seab.gov.sg/files/O%20Lvl%20Syllabus%20Sch%20Cddts/2026/4049_y26_sy.pdf)
- [Holy Grail library](https://grail.moe/library)
