# Public dashboard screenshots

These PNGs illustrate the actual Jobot dashboard for the root README. They were
captured on October 21, 2026 from the UI at `6030175`, using an isolated local
managed service and newly created synthetic records.

| File | View |
|---|---|
| `applications.png` | Applications pipeline and queue overview |
| `answer-inbox.png` | Needs your answer and the question editor |
| `learned-answers.png` | Reusable answers and their scope |
| `settings.png` | Model choices, concurrency and application deadline |

All employers, jobs, candidate facts, answers and recorded outcomes are fictional.
Example posting URLs use reserved `.test` domains. No employer was contacted, no
application was submitted, and no production database, profile, mailbox, resume
or authenticated browser session was used. The queue is intentionally paused and
no executor or worker is running. Counts are demonstration data, not benchmarks.

The captures use the repository's real HTML/CSS/JavaScript, API and service methods,
with an isolated headless Chromium profile at 1440 pixels wide (view heights of
1000–1540 pixels to include the relevant controls). They are browser
screenshots, not generated mockups. Model menus reflect fixture defaults, not a
guarantee that any particular provider/model is available in a new installation.

When refreshing these assets, use a fresh synthetic instance and isolated browser,
capture the current UI, and visually inspect each image before publishing. Keep
temporary databases, capture logs and browser profiles under ignored `artifacts/`.
