# SixAudio System Redesign Proposal

Status: Proposal for review — no implementation decisions are final.

## 1. Purpose

Redesign SixAudio as a dependable, personal web application for collecting web novels and turning them into playable, captioned audiobooks. The system should be pleasant to use every day, recover cleanly from interruptions, and remain understandable and maintainable as a long-term personal project.

The first release remains a single-user application on the user's own computer. The design should avoid blocking a future move to another machine, but does not assume a public multi-user service, cloud accounts, or multiple simultaneous workers.

## 2. Problems to solve

1. Starting `python app.py` should start the backend and open the web app. The normal workflow should not show or require the terminal UI.
2. A user can submit more story links while work is underway. Each accepted story is saved in a visible, ordered queue and processed one at a time.
3. Work can be paused or stopped from the web app and continued later, including after the app or computer restarts. Completed chapters and audio must be retained and skipped on resume.
4. A story can be checked for new chapters and scraped incrementally without duplicating existing chapters or audio.
5. Pasting a story URL starts a discovery step that collects the story title, cover image, summary/description, and chapter catalog before bulk chapter scraping begins.
6. The user can follow the full pipeline and its progress: story URL → discovery → chapter text → audio → captions.
7. The primary UI has two destinations: a story library/player screen and a dashboard.

## 3. Product experience

### Screen A: Story library and player

This is the listening-first home screen. It presents story cards with cover, title, author when available, summary, listening progress, and processing state. Selecting a card opens its story view/player with chapter navigation, playback controls, and synchronized captions when available.

Story actions should be available without exposing implementation details: play/continue, check for updates, continue scraping, generate missing audio/captions, and open story details. Missing cover images use a consistent local placeholder. Metadata should identify its source and allow editing when extraction is wrong.

### Screen B: Dashboard

This is the work and status screen. It contains:

- A prominent “Add story” URL field.
- A discovery preview showing the detected title, cover, summary, chapter count, and chapter list before the user starts the full scrape. The user can correct the title or cover and choose whether to continue.
- An ordered queue of submitted stories, including the active item, waiting items, paused items, and failures. Queue items can be reordered, removed when waiting, retried, or opened.
- A pipeline view for each story: Discovery → Chapters → Audio → Captions, with stage status, counts, current item, elapsed time where useful, and a concise error with a recovery action.
- Controls to pause after the current safe unit, resume, retry, and stop. “Stop” should preserve completed work and checkpoint the active stage; it should not mean deleting a story or its files.
- A way to run the same pipeline on an existing story, or to check for new chapters and queue only missing chapters.

Navigation between these two screens should be persistent and obvious. Settings can be a small panel or dialog rather than a third primary destination.

## 4. Proposed end-to-end flow

1. User pastes a supported story URL and submits it.
2. The backend validates the URL and creates a durable discovery job. The UI immediately shows its status.
3. Discovery extracts available story metadata and the chapter catalog. The system stores the catalog and metadata, downloads a cover when permitted, and presents a preview.
4. User confirms processing (or has enabled an explicit “automatically continue after discovery” preference).
5. The chapter stage downloads chapters sequentially, recording each chapter URL, title, stable chapter identity/order, and completion state. Existing complete chapters are skipped.
6. The audio stage converts chapters that do not have valid audio, then updates the story's playable state.
7. The caption stage generates timestamped captions for audio that does not already have valid captions.
8. On update check, discovery refreshes the catalog, identifies chapters absent from the local library, and offers or queues only those chapters through the same downstream stages.

The pipeline should be resumable at both the story and stage level. A failure in captions must not cause chapters or audio to be downloaded/generated again. A retry should restart from the failed or explicitly selected stage.

## 5. Backend design direction

### One application process and launcher

Keep one Python entry point. It should initialize configuration and storage, start FastAPI and its background worker, then open the local web address in the default browser. If the browser is already open or auto-open is disabled, print the local URL. Shutdown should request a safe checkpoint and close worker/browser resources. The terminal remains available for logs and diagnostics, not as the normal control surface.

### Durable pipeline jobs

Replace the scrape-only queue conceptually with a durable job/pipeline model in SQLite. Keep SQLite for the personal single-machine deployment unless measured needs justify another database. Persist:

- Story records and their source URLs / site identifiers.
- Discovery metadata and a normalized chapter catalog.
- Pipeline jobs, queue order, current stage, state, attempts, timestamps, and last actionable error.
- Per-chapter stage state so completed work is idempotent and resume can continue precisely.

Use explicit states such as `queued`, `discovering`, `ready_for_confirmation`, `scraping`, `audio`, `captions`, `paused`, `completed`, `failed`, and `cancelled`. Keep cancellation distinct from pause and failure. Define transitions in one place and validate them.

### Worker and recovery

Start with one sequential worker to protect the shared browser profile and avoid overloading source sites or the local TTS/GPU. Worker stages should checkpoint between chapters and between major stages. On restart, recover interrupted jobs into a resumable state rather than blindly marking them complete or restarting the entire pipeline. Persist enough information that UI state is reconstructed from SQLite, not only from in-memory WebSocket events.

### Stage boundaries and adapters

Separate site-specific discovery/chapter extraction from orchestration, text cleaning, TTS, and captioning. Keep the existing scraper, TTS, and faster-whisper implementations as adapters during the first migration where practical. The pipeline coordinator should call stage interfaces and should not contain site selectors or synthesis details.

### Story files and metadata

Continue storing large chapter/audio files on disk. Treat the database as the authoritative index and the files as stage artifacts. Add safe, predictable per-story paths and a migration/import pass for existing `Library/` folders and `.story_progress.json` metadata. Never require users to discard an existing library to adopt the redesigned app.

For covers, cache downloaded image files locally and store their source URL, local relative path, and fetch status. Store summary/description text and metadata provenance. Handle unavailable or blocked images without blocking the rest of discovery.

### API and UI updates

Expose endpoints for story list/detail, add/discover, confirm/start, queue list/reorder, job pause/resume/cancel/retry, update checks, and stage actions. Use WebSockets or server-sent events for live updates, with ordinary API reads as the source of truth after reconnect. Keep all filesystem paths server-side and validate every requested story/job identifier.

## 6. Reliability and long-term quality

- Idempotency: rerunning a stage must not duplicate chapters, tracks, or captions.
- Checkpointing: save progress after each chapter and meaningful state transition.
- Recovery: app crash, computer restart, network loss, and a single bad chapter must leave useful completed work intact.
- Observability: provide readable logs, actionable errors, and a per-stage history without requiring the user to inspect JSON files.
- Configuration: keep library path, launch behavior, browser visibility, scrape pacing, TTS engine/voice, caption model, and audio preferences in one documented settings location.
- Data safety: do not delete user media when clearing queue items; distinguish removing a queue entry from deleting a library story.
- Source support: implement each site behind a discovery/chapter adapter and verify selectors against representative pages. Respect source access controls and site terms; browser automation cannot guarantee bypassing security checks.
- Portability: use paths relative to configured data locations, document backup/restore, and avoid machine-specific assumptions.
- Accessibility and usability: keyboard-friendly controls, readable status labels, clear empty/loading/error states, and responsive layout for desktop and phone.

## 7. Migration approach

This is a staged redesign, not a one-shot rewrite. Keep current data usable throughout.

### Phase 0 — agree on behavior and inventory

Confirm the open questions in Section 9. Inventory actual library formats, supported sites, launch expectations, and current web routes. Record a migration and backup plan.

### Phase 1 — web-first startup

Make `python app.py` start the local web application and open the browser. Retain the TUI only as an optional diagnostic/legacy entry point until web workflows cover the necessary operations.

### Phase 2 — discovery and story catalog

Add durable story/discovery records, metadata and cover handling, chapter catalog preview, and a migration path that imports existing library stories.

### Phase 3 — durable pipeline queue

Unify scrape, audio, and caption work under a single persisted pipeline with queue controls, pause/resume, restart recovery, stage retries, and incremental update checks.

### Phase 4 — two-screen experience

Polish the story library/player and dashboard around real persisted state. Add accessibility, mobile layout, and useful empty/error states.

### Phase 5 — hardening and retirement

Verify migration on a copy of the real library, confirm crash/restart behavior and stage idempotency, document backup/restore, then decide whether to remove old TUI-only paths.

Each phase should have acceptance criteria and be reviewed before the next broad change. Keep a tested backup before any schema or on-disk migration.

## 8. Initial acceptance criteria

- Running `python app.py` starts the local server and opens the dashboard without requiring a TUI menu.
- A user can submit multiple story URLs while one story is processing; they remain visible and are handled sequentially in saved order.
- A submitted story survives app restart and appears with accurate status and progress.
- Pause/stop preserves completed chapter, audio, and caption artifacts; resuming skips valid completed work.
- Discovery displays extracted story metadata and chapter links before bulk scraping, with a way to handle partial metadata extraction.
- Update check finds newly listed chapters and does not duplicate already stored chapters.
- Audio and caption failures can be retried independently without repeating successful earlier stages.
- Existing library folders can be imported without moving or deleting their media.
- The story screen supports browsing and listening; the dashboard supports adding, monitoring, and managing work.
- The UI remains understandable after reconnecting, refreshing, or restarting because persisted API state is authoritative.

## 9. Questions to settle before implementation

These are the decisions that materially shape the first build. Recommended defaults are included so they are easy to confirm or change.

1. After discovery, should the system automatically scrape the full story, or wait for you to review the cover/summary/chapter list and press “Start”? Recommended: show the preview and require one confirmation initially; add an auto-continue setting later.
2. When you say “stop,” should the current chapter finish and then pause, or should the browser stop immediately? Recommended: finish the current chapter, checkpoint, then pause; also offer a separate immediate cancel for a genuinely stuck job.
3. Should the pipeline automatically run audio and captions as soon as scraping finishes? Recommended: yes, with per-stage settings and the option to disable captions or defer expensive work.
4. Which sources are essential for version one? The current code has adapters/selectors for ScribbleHub, NovelBin, Webnovel, FreeWebNovel, and LightNovel.to, but their reliability may differ.
5. Is this strictly a local app on one computer, or do you need to control it from another device on your home network? Recommended: local-only by default; keep mobile access as an explicit secured setting.
6. For the library screen, should playback position be tracked per story/chapter so “Continue listening” is a core feature? Recommended: yes.
7. Do you want existing story folders and generated files to stay in their current `Library/` layout? Recommended: preserve them and build a non-destructive importer before changing storage layout.

## 10. Current project observations

This proposal is grounded in the current repository, where:

- `app.py` is a Rich terminal menu and already has a mobile-server workflow.
- FastAPI and a browser-based player/dashboard already exist in `modules/server.py` and `modules/templates/`.
- `modules/scrape_queue.py` persists scrape URLs in SQLite and processes them sequentially through `modules/scrape_worker.py`.
- Scrape progress and catalog data partly live in per-story `.story_progress.json` files; TTS and captions are separate operations.
- The scraper already detects the five listed novel sites and contains some catalog and resume behavior.
- The current data model does not yet represent a single durable discovery → scrape → audio → caption pipeline, and the queue UI/state is not the unified control plane described above.

These are observations of the current implementation, not commitments to preserve every module or API unchanged.

## 11. Proposed decision

If approved, use this document as the product and architecture brief for a phased redesign. Before implementation, resolve the questions above, inspect the current routes and library metadata in more detail, and write a migration plan with explicit backup and compatibility criteria. The first implementation milestone should be web-first startup plus an accurate inventory/migration strategy, followed by durable discovery—not a wholesale replacement of scraping, TTS, and playback all at once.
