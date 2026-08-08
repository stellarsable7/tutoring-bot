# OpenRouter End-to-End Checklist

These checks prove that the real services work together. Run them before relying on automated
marking with students.

## 1. Ask the real AI to read and mark a sample

**What to do:** Run the opt-in OpenRouter E2E test with a test image and a published solution.

**What should happen:** OpenRouter reads the image, returns valid structured data, and proposes a
mark that does not exceed the question's maximum.

**Status:** Passed on 2026-08-08 using `google/gemma-4-26b-a4b-it:free`.

## 2. Check retries in real PostgreSQL

**What to do:** Run the opt-in PostgreSQL E2E test against a disposable database.

**What should happen:** A failed job waits 3 seconds, then 10 seconds, and remains safely stored in
the database. A later success clears the retry time and leaves the result ready for tutor review.

**Status:** Passed on 2026-08-08, including migration downgrade and upgrade.

## 3. Send a real Telegram submission

**What to do:** Start the bot, import the supplied catalogue, enrol a test student, assign a
question, upload readable working, and submit it.

**What should happen:** The submission moves from `queued` to `processing` to `flagged`. The tutor
receives a notification, and `/review` shows the proposed mark and evidence.

**Status:** Deferred. This still needs a tutor account and a separate test-student account.

## 4. Watch a temporary provider failure recover

**What to do:** In a test deployment, make the provider temporarily unavailable, submit test work,
then restore the provider.

**What should happen:** The work stays queued instead of disappearing. The retry count and next
retry time increase. After the provider returns, the same submission reaches tutor review.

**Status:** Automated retry behavior passed; the full Telegram version is deferred.

## Safety

- Use test accounts and test handwriting, not real student information.
- Never print or commit the OpenRouter key or Telegram token.
- Use a disposable database for migration and failure tests.
- Do not run `docker compose down -v` unless deleting the test database is intentional.
