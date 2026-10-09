# SixAudio UI and Backend Technology Recommendation

Status: Recommendation for review; no dependencies or architecture have been changed.

Related product brief: [SYSTEM_REDESIGN_PROPOSAL.md](SYSTEM_REDESIGN_PROPOSAL.md)

## Recommendation in one sentence

Build the local web UI with **React + TypeScript + Vite**, keep **Python + FastAPI** for the application/API and existing media engines, and use **SQLite + SQLAlchemy + Alembic** for durable stories, chapter catalogs, and pipeline jobs. Run one database-backed worker sequentially at first.

This keeps the proven Python scraping/TTS/caption code while replacing the fragile, growing vanilla-JavaScript UI and scrape-only persistence with a typed interface and a versioned data model.

## Proposed stack

| Area | Recommendation | Why it fits SixAudio |
| --- | --- | --- |
| Frontend language | TypeScript | Types catch mismatched story, chapter, and pipeline states as the UI grows. React documents first-class TypeScript usage. |
| UI framework | React | The library/player and dashboard share reusable cards, progress, player controls, dialogs, and queue components. |
| Frontend build | Vite | Fast local development and a static production build that FastAPI can serve. No server-side rendering is needed for a personal local app. |
| Routes | React Router | Two clear top-level routes: Library/Player and Dashboard; story details can be nested under the library route. |
| Server data/cache | TanStack Query | Handles API loading, caching, refresh, mutation state, and reconnect/refetch behavior for persisted server state. |
| Styling and components | CSS variables/design tokens plus Tailwind CSS; use accessible headless primitives for dialogs, menus, and other complex controls | Tokens keep the visual system consistent, utility styling speeds iteration, and accessible primitives reduce custom keyboard/focus bugs. Keep components visually owned by SixAudio rather than adopting a rigid full dashboard theme. |
| Backend/API | Python 3.12+ and FastAPI | Preserves the current backend and Python libraries, with request validation and generated OpenAPI documentation. |
| API schemas | Pydantic v2 | Validates API inputs/outputs and keeps transport models explicit. Generate TypeScript API types from FastAPI's OpenAPI schema to avoid hand-maintained duplicates. |
| Database | SQLite | Appropriate for one local user, one machine, durable restart recovery, and simple backup. Keep large media files on disk, not in database rows. |
| Database access | SQLAlchemy 2.x | Gives explicit models, relationships, and a path to PostgreSQL later without binding application logic to raw SQLite statements. |
| Schema changes | Alembic | Versioned migrations make upgrades repeatable and let existing installations move forward without discarding the library. |
| Job execution | A small application-owned, SQLite-backed sequential worker | It matches the single-user workload and shared Chromium profile. Avoid adding Redis/Celery/RQ until measured workload requires them. |
| Live progress | Server-Sent Events (SSE) for one-way progress; REST for pause/resume/retry/reorder commands | Progress flows server → browser, while user actions flow browser → API. This is simpler than a bidirectional socket for pipeline status. Retain WebSockets only where true two-way messaging is useful. |
| Scraping | Keep DrissionPage during the first redesign milestone; evaluate Playwright separately with real site fixtures | Replacing scraper and UI/database simultaneously would increase migration risk. Pick a browser engine from measured reliability on the supported sites, not general popularity alone. |
| TTS and captions | Keep the current Kokoro/Edge TTS and faster-whisper implementations behind stage interfaces | These are working, compute-heavy subsystems. The redesign needs to orchestrate them reliably before it needs to replace them. |
| Packaging/launch | One Python entry point starts FastAPI, serves the built UI, and opens the local browser | Meets the `python app.py` workflow while keeping browser and Python process lifecycle in one place. A packaged installer can be considered later. |

## Frontend details

### React, TypeScript, and Vite

Use a small single-page app. Vite compiles the frontend into static assets; FastAPI serves those assets and its `/api` endpoints from the same local origin. In development, Vite can proxy `/api` to FastAPI. This avoids production CORS setup and makes the local launch model straightforward.

Use React components around product concepts, not around generic technical layers:

- `StoryCard`, `StoryGrid`, `StoryDetails`, and `AudioPlayer` for the library/listening experience.
- `AddStoryForm`, `DiscoveryPreview`, `PipelineStages`, `QueueList`, and `JobControls` for the dashboard.
- Shared `CoverImage`, `StatusBadge`, `ProgressBar`, `ConfirmDialog`, and empty/error/loading states.

Keep only UI-only state (open dialog, selected tab, player drawer visibility) in component state. Treat stories, queue order, progress, and chapter state as server data, refreshed through TanStack Query and live events.

### Visual system

Start with a small design system: color/type/spacing/radius tokens, a restrained set of reusable components, and responsive layouts. The existing cyberpunk/glass look can inform the visual identity, but contrast, text readability, focus visibility, and dense queue readability should take priority over decorative effects.

Use semantic HTML and accessible primitives for keyboard-operable dialogs, popovers, and menus. Build desktop first for the dashboard and ensure the library/player remains comfortable on a phone.

### API type safety

FastAPI already describes endpoints in OpenAPI. Generate frontend TypeScript types from that schema during development/CI. This keeps the backend's authoritative data shapes aligned with the UI without introducing a second manually edited API contract.

## Backend details

### FastAPI remains the application server

Keep FastAPI as both local API server and static frontend host. Organize backend code into clear areas:

- `api`: HTTP routes, SSE event route, and Pydantic request/response schemas.
- `domain`: story, chapter, pipeline, and state-transition rules.
- `services`: discovery, scraping, TTS, captioning, and library import orchestration.
- `repositories`: SQLAlchemy queries and transaction boundaries.
- `worker`: durable queue claiming, stage execution, checkpoints, and recovery.
- `storage`: configured library paths, cover downloads, and artifact verification.

Routes should orchestrate use cases rather than contain scraper selectors, SQL statements, or long-running media work.

### SQLite with SQLAlchemy and Alembic

Use SQLite as the first durable database because the intended deployment is local and single-user. Put the database under a configured application-data directory, separate from the source checkout and media library. Enable WAL mode and set transaction behavior deliberately. SQLite WAL supports concurrent readers alongside a writer, but it still permits only one writer at a time; serialize job-state writes and keep database transactions short. Do not copy only the `.db` file while the database is open in WAL mode; use SQLite's backup mechanism or stop the app cleanly.

Use SQLAlchemy models for `Story`, `Chapter`, `PipelineJob`, and (if useful after modeling) `StageRun`/`JobEvent`. Use Alembic from the first schema so future changes are migration files, not ad-hoc table edits. Add uniqueness constraints for normalized source URLs and chapter identity within a story to support idempotent update checks.

Move existing `.story_progress.json` data into the new schema through a dry-run-capable, repeatable importer. Keep chapter/audio files where they are initially; the migration should index and validate them, not relocate them.

### Durable worker, not a new distributed queue

Start with a single sequential worker owned by the application process or a closely coupled worker thread. It claims persisted jobs, advances one stage at a time, writes a checkpoint after each chapter, and observes pause/cancel requests between safe work units. Startup recovery inspects the last persisted stage/chapter and requeues resumable work.

Do not use FastAPI's in-memory `BackgroundTasks` as the durable job system: process memory is not a queue and cannot by itself recover interrupted work. The SQLite job table is authoritative. If the app later needs multiple workers, a remote host, or sustained parallel workloads, extract the worker and move to PostgreSQL plus a dedicated queue then.

### State and progress events

Persist meaningful transitions and counts; do not persist every rapid progress tick. Publish progress events over SSE for immediate display, and have clients refetch canonical job/story state after reconnect or missed events. REST endpoints perform state-changing actions and validate legal transitions. This makes a browser refresh safe and prevents WebSocket memory from becoming the only record of progress.

### Local launch and security boundary

Bind to loopback by default for a personal local app. Make LAN access an explicit setting with authentication and clear network exposure behavior. `python app.py` should start the server, wait until it is accepting requests, and then open the local dashboard. Provide a `--no-browser` or configuration option for headless/server use, and handle an occupied port by selecting/reporting a usable port rather than failing silently.

Keep tokens/secrets out of the frontend bundle. Validate all story/job identifiers and resolve media paths within the configured library root. Keep cloud deployment as a separate deployment profile; local paths, browser scraping, and GPU TTS should not be implicitly enabled in a cloud server.

## Suggested repository shape

```text
frontend/
  src/
    app/             # routes, application shell
    components/      # shared UI components
    features/
      library/       # story cards, story details, player
      dashboard/     # discovery, queue, pipeline controls
    api/             # generated API types and typed client
    styles/          # design tokens and global styles
  package.json
  vite.config.ts

modules/
  api/
  domain/
  repositories/
  services/
  worker/
  storage/
  templates/         # built frontend output only, if kept under Python package

alembic/
  versions/
```

The exact location for built assets should be chosen during implementation; do not keep two independently edited copies of frontend files. The current duplicated static asset trees should be replaced by one frontend source and one generated build output.

## Alternatives considered

### Keep vanilla JavaScript

Lowest initial migration cost, but the two screens, player state, discovery preview, durable queue controls, and live progress will create more hand-built state management and repeated UI. Suitable only if the redesign stays very small.

### Next.js or another server-rendered framework

Strong options for public websites and server-rendered content. SixAudio is a local application with an existing Python backend and no SEO requirement, so a React SPA built by Vite has fewer runtime pieces and avoids splitting server responsibilities across Node and Python.

### PostgreSQL immediately

Excellent when multiple users/processes or concurrent writers are a real requirement. For the current local single-user scope, it adds a separate service to install, run, secure, and back up. Keep SQLAlchemy and clean repository boundaries so moving later remains possible.

### Celery, Redis, or a general workflow platform

These become useful for distributed workers, broad parallelism, and operationally complex retries. A single sequential local worker can meet the current needs with a persisted SQLite state machine and fewer moving parts.

### Replace DrissionPage with Playwright now

Playwright has a broad browser automation ecosystem and automatic waiting behavior, but migration can change profile/session and anti-bot behavior on existing sources. First isolate the scraper behind an interface; then compare both against the same supported-site acceptance cases before selecting a replacement.

## Adoption sequence

1. Confirm local-only vs LAN use, the existing-library migration rules, and the initial site list.
2. Add the frontend build and serve it from FastAPI. Keep the existing API available while migrating screens.
3. Define story, chapter, and job states; add SQLAlchemy models and the initial Alembic migration.
4. Import existing stories and progress non-destructively; verify counts and paths before enabling writes to the new model.
5. Implement discovery and catalog preview, then the durable sequential worker and its pause/resume/recovery behavior.
6. Connect scraping, existing TTS, and captions as independently retryable stages.
7. Finish the two screens, one-command browser launch, backup/restore guidance, and a controlled migration from legacy routes/data.

The current code should not be discarded in one pass. Keep the existing scraper/TTS/caption modules running behind the new orchestration layer until the new end-to-end path has been exercised against a copy of the real library.

## Official references

- [React: Using TypeScript](https://react.dev/learn/typescript)
- [Vite: Getting Started](https://vite.dev/guide/) and [Why Vite](https://vite.dev/guide/why)
- [FastAPI: Features and OpenAPI](https://fastapi.tiangolo.com/features/)
- [SQLAlchemy: ORM](https://docs.sqlalchemy.org/en/20/orm/) and [SQLite dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [Alembic: Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [SQLite: Write-Ahead Logging](https://www.sqlite.org/wal.html)
- [TanStack Query: React documentation](https://tanstack.com/query/latest/docs/framework/react/overview)

Documentation reviewed on 2026-10-09. Check supported version compatibility at implementation time and pin versions in the project lock/config files.
