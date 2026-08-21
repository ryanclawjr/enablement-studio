# Enablement Studio product contract

Audience: humans and agents working this repo.

This file is the definition of good. Enablement Studio v0 already has typed outputs and an offline engine. Tablework is the product name; the repo and package stay enablement-studio. Later LLM prompts and evals must satisfy this contract. They are not written here.

Passing the Harborline Account Executive demo is the happy path only. It does not certify Role on other jobs.

## Why this file exists

The offline Role path looks right on `fixtures/example_account_executive_job.txt` and used to fail on a real enablement job posting: it pasted the new title onto a sales-discovery / "before presenting price" template. The skill graph, practice, and quiz stayed a seller module. That miss is the title-swap test.

This file names what good means so the next sitting can change prompts and tests against it.

## Spine

Keep these. Do not grow them in this sitting.

- Three products only: Role → Enablement, Call → Coach, Lesson critic.
- One entry point: `generate(product, text)` in `src/enablement_studio/engine.py`. Optional `force_offline=True` skips the LLM hook. Do not add a second generate path.
- One SQLite store per surface. Local Air is the file `data/enablement.db`. Public is a per-visitor ephemeral sqlite (temp file on the in-memory FS), keyed by a session cookie — not a shared guestbook of pasted JDs. Each save is a versioned run. `list`, `show`, and `compare` read that store.
- The dataclasses and JSON shapes in `src/enablement_studio/models.py` are the API. CLI, UI, offline engine, and LLM all emit the same objects: `RoleEnablement`, `CallCoaching`, `LessonCritique`.
- The offline path never dies. Demos, CI, and interviews run with no API key. If an LLM call fails or the JSON does not match the schema, fall back to offline.
- No LAPC, WarU, Autonoma, IDN, SIGNIT, or subscriber/PII content in fixtures or docs. Demo data stays labeled EXAMPLE DATA.
- Local-first on the Air. Public host is Cloudflare (Python Worker), specified below. No custom domain. No login.

## Role → Enablement

Input is a job posting or a messy SOP.

Output already exists on `RoleEnablement`: a skill graph, measurable objectives, a 30-minute outline, a practice activity, and a quiz.

The module trains the person who will do **this** job. It does not decorate a generic seller module with a new title.

### Rules

1. The skill graph is for this job. Extract skills from the source text. Do not stamp a generic account-executive / discovery / price template onto every title.
2. If the job is an enablement, L&D, or coaching role, the learner is a person doing that job. That family includes instructional design, customer education, nurse / clinical / patient educator, nursing-education leadership, and director of education. In-scope work includes gap analysis, onboarding design, technical packaging, launch readiness, and impact metrics. Do not treat every JD as "train this person to sell."
3. If the job is a seller, SE, or SA in the field, seller skills are in-bounds: discovery, demo, objection handling, and the like. Practice and objective nouns come from the source (operators, integration, architecture). Buyer / cautious-buyer lines only if the source has those nouns.
4. Every objective verb must appear in the graph. Practice and quiz must measure those same verbs.
5. Fail the run, or mark it invalid, if the module could be reused on a random AE job by swapping the title. That check is the title-swap test.
6. Known failure (public posting, not an application): Stripe Solution Architect Enablement Business Partner, Greenhouse 8115022, listed at [stripe.com/careers](https://stripe.com/careers/listing/solution-architect-enablement-business-partner/8115022). Offline v0 kept AE discovery, price, and CRM next-step quiz items after swapping in the title. A passing Role run on that JD talks about SA onboarding, technical packaging for a sales audience, launch readiness, and enablement impact metrics.

Rule 2 applies to an enablement partner who supports solution architects. That person is not a field SA. Rule 3 does not win because the title contains "Solution Architect."

### Title-swap test

Take a finished Role module. Replace only the role title with "Account Executive" or another unrelated seller title. If the skill graph, practice, and quiz still read as a coherent module for that seller, the run fails.

The Harborline AE fixture may look like an AE module. The source is an AE posting. The Stripe enablement JD is the counterexample. A passing module does not ask what to do before presenting price, and does not treat CRM next-step logging as the proof of skill.

A title-swap failure must not be stored as a successful Role run. `RoleEnablement.invalid` and `runs.invalid` mark the miss so `list`, `show`, and eval can see it. Do not silently emit the AE template. Harborline AE remains a valid successful run.

### Work-derived skills, application quiz, and EnablementFrame

These three rules sit on top of the Role rules above. They do not replace title-swap, invalid, or the Stripe known-failure. `classify_job_family` stays `enablement | seller | unknown`. Do not invent a fourth product. Do not explode JobFamily into more enums.

7. **Work-derived skill graph.** Extract work units from the source first: a bullet, a numbered SOP step, or a "you will" / responsibility line that actually appears in the input. If extract is empty, the graph is empty and the run is invalid (already the contract). Every skill node must be grounded in one of those source spans. A node name, or a clear span of it, must appear in the source. Catalogs may attach level, detail, or relation to a node whose name is grounded. They must not invent a node the source does not support, and they are not a fallback graph when extract is thin. Edges follow document order, plus explicit after/before language when it is present. Do not add catalog edges that connect invented nodes. Disclaimer and example-data sentences are not skill nodes. Known nit: Harborline "No live customer book is required" is not a node. Harborline AE stays valid because that fixture has discovery, price, and CRM work in the source — those nodes are grounded, not stamped. Stripe SA Enablement nodes (gap analysis, SA onboarding, technical packaging, launch, impact) still come from that public-posting source, not from a leftover AE catalog. A Product Manager JD with no extractable enablement or seller work stays unknown and invalid.

8. **Quiz is application, not recognition.** Practice is the real assessment. Each quiz item is a short scenario that uses nouns from the source, then asks for the next move or which success criterion was met. At least one quiz item maps to a `practice.success_criteria` line (same verb or same criterion). Fail the check if the dominant quiz pattern is title-recognition: "Which move best lets a {title} {verb} {stump}?" Choices are plausible moves in that scenario, not job-title trivia. Same verbs as the graph (rule 4). Stock AE lines only if those nouns are in the source.

9. **EnablementFrame** (enablement family only). ID, customer education, clinical educator, and enablement partner share "design for someone else's performance" as a classifier, not as one practice theory. When family is enablement, pick one frame and let practice, audience, and module voice follow it:
   - `designer` — instructional design, LXD, curriculum, storyboard, needs analysis. The learner designs instruction.
   - `educator` — nurse / clinical / patient educator, facilitator, train-the-trainer, customer-education delivery. The learner teaches or coaches practitioners.
   - `partner` — enablement partner, gap analysis, packaging, launch readiness, impact metrics for a field team. The learner enables people who sell or implement.
   Do not put "SA teams they support" on a designer or educator source. Do not put a storyboard studio on a Stripe SA enablement partner unless the source is about storyboards. Seller family is unchanged (field SA / AE). Director of Nursing Education and Patient Educator land `educator`, not `partner`. Instructional Designer / LXD land `designer`. Stripe SA Enablement and Customer Education Lead: pick from the source (customer-ed delivery vs program design). If both appear, prefer the verbs in the bullets.

## Call → Coach

Input is a sales or training transcript.

Output already exists on `CallCoaching`.

- Notes for learner, customer, and coach. No other audiences.
- Exactly one enablement fix, tied to a signal that appears in the transcript.
- Do not invent speakers or facts that are not in the source.
- The fix is a drill or artifact a manager can run, plus a measure.

Speakers come from the transcript. A call that never mentions price does not get a discovery-before-rate drill unless a listed signal justifies it. Payments voice (how money moves, rate card) only if the source is payments. A note that invents a buyer problem the transcript never stated is a miss.

## Lesson critic

Input is a lesson outline or storyboard.

Output already exists on `LessonCritique`.

- Scores from 1 to 5 for objective clarity, activity alignment, and assessment alignment. `AlignmentScores.overall` is the rounded mean of those three, as the type already stores.
- Findings explain the scores.
- Rewrite the weakest part so the activity or assessment practices the same verb as the objective.

A scavenger-hunt activity against "explain interchange" fails alignment. Same verb on a different object also fails (pallet-jack vs a buyer discovery call). The rewrite must make the learner practice that verb on that skill, in the objective's domain, as a readable sentence.

## Eval

- Keep the three fictional fixtures for the happy-path demos: `example_account_executive_job.txt`, `example_sales_call.txt`, `example_new_hire_lesson.md`. They stay labeled EXAMPLE DATA.
- Eval case: `fixtures/eval_stripe_sa_enablement_job.txt` is a sanitized public-posting copy of Stripe Solution Architect Enablement Business Partner (Greenhouse 8115022). It is labeled PUBLIC POSTING, not EXAMPLE DATA. No apply buttons, pay ranges, or application materials.
- A canned AE-template blob must fail the title-swap test. Role output on the Stripe eval fixture must pass it.
- `pytest` stays green with no API keys.

## Local UI

Tablework is the product name. The repo and package stay enablement-studio.

`enablement serve` is a loopback page over the same `generate()` entry and SQLite store. Default bind is 127.0.0.1:8765. No auth. No public site. Offline is the product.

GET `/` is Role Source. Home is one job document on a full-bleed dark table. Tokens come from the live microinteractions.co CSS: canvas `--black-brand` `#16161d`, cards `--black-2` `#1d1d25`, accent `--yellow-brand` `#ffe52f` on `#000`, ink `--white-brand` `#f6f6f6`, muted `--slate-grey` `#757575`, hairline `rgba(236,236,236,0.08)` or `rgba(109,112,130,0.21)`. Elevation is hairline only. The grid is CSS 1px lines, about 80px, stroke `#848484` at 0.25 opacity. No BGG.svg beam and no `<canvas>`. The sheet is centered, about 820px, radius 12–16px. Quiet SOURCE kicker, a 16px/24px textarea, yellow Run, ghost LLM, Harborline as muted text. Versions are small dots in the sheet footer. The Role path is six object cards on a 6-column grid with 16px gap: Source, Graph, Objectives, Outline, Practice, Quiz. Current step is one yellow marker (a dot), not a wash. Clicking a card uses the same `?run=` / `?step=` query as today's path. No second row of pills under the wordmark. No two-column studio and versions rail. Chrome stays tight: Tablework, one status pill (`this machine · 127.0.0.1 · offline`), and `Call Next · Critic Next`. Yellow is spent: Run and the current-object marker. Run hover is a yellow glow bloom (`0 20px 50px rgba(255,242,80,.34)` over 400ms), not translateY. Fonts are local Instrument Sans 400/500, stack `Instrument Sans, ui-sans-serif, sans-serif`. Not fonts.googleapis.com. Wordmark says Tablework, not Enablement Studio. Do not ship beige/stone/steel. Do not ship a hero, spotlight, pricing, or three equal-weight product cards.

GET `/role` is the same studio (same handler, or 302 to `/` with the same query). Old `/?product=role` stays on `/`. `/?product=call|critic` is a quiet next note under chrome; it must not replace the table with a splash. `/call` and `/critic` do the same.

One `generate()` still returns all five Role objects; the UI reveals them one step at a time: Source, Graph, Objectives, Outline, Practice, Quiz. Opening `/` with no run is Source. After a successful Run, redirect to Graph. Opening `/?run=N` or `/role?run=N` without a step is Graph. Step state is `?step=source|graph|objectives|outline|practice|quiz` plus `?run=` after generate. After Run, the sheet shows that step's object. Graph shows skill chips, labeled adjacency, and Family/Frame as quiet meta. Invalid Role stops the walk on Graph with "Invalid module" and reasons. Do not parade a successful Outline or Quiz. Do not dump all five objects on one page.

Studio Run is offline-first: it calls `generate(..., force_offline=True)` and must return a board without waiting on OpenAI. The optional LLM hook is the same one the CLI uses. It is a separate LLM action, never the thing that holds Run. A single-threaded `HTTPServer` that blocks GETs while urllib talks to a model is not acceptable; other tabs must stay readable while an LLM call is in flight. If `generate()` does call the LLM (CLI or LLM action), the urllib timeout must actually bound that call.

Empty Run stays on Source. Show the validation in English ("Source is empty. Paste a job or SOP, or Run Harborline."). Do not hang. Do not replace the studio with a raw 400 page. Do not render Role/Call/Critic radios in the form.

Call and Critic are a quiet next line. This sitting does not add `/call` or `/critic` walkthroughs.

History is this project and product. Two Role runs in the same project can be compared. There is no learner-facing onboarding buddy.

## Public host

Ryan authorized shipping Tablework as a premier public product. Anyone can paste a JD or messy SOP and walk Role Source → Quiz without cloning or `enablement serve`.

The public app is the same `generate()` and the same Role Source HTML as loopback. Request handling lives in `src/enablement_studio/handler.py`: `(method, path, query, body, headers) → (status, headers, body)`. Local `ThreadingHTTPServer` and the Cloudflare Worker `fetch()` both call it.

- Worker: `src/worker.py`, `from workers import WorkerEntrypoint, Response`. `wrangler.toml` name `enablement-studio`, `compatibility_flags = ["python_workers"]`. Pages `pages deploy` rejects `main`, `[assets]`, `[[migrations]]`, and Durable Object bindings without `script_name`; do not add those back. The static-assets binding must not be named `ASSETS`.
- Existing Pages project `enablement-studio`, production branch `main`. URL after first deploy: `https://enablement-studio.pages.dev`. Do not create a second project. No custom domain.
- Public store is not a global D1 table. Each visitor gets a random session cookie. Their runs live in an ephemeral sqlite file for the request, then the file bytes go to a Durable Object keyed by that cookie (KV-shaped: one key, short TTL). Isolate memory dies between requests; a shared guestbook would leak pastes.
- Local Air store stays file SQLite at `data/enablement.db`.
- Worker serves `/static/fonts/*` the same as loopback (package files, plus the STATIC binding).
- LLM key is the Worker secret `ENABLEMENT_LLM_API_KEY`. Do not put it in the repo, in chat, or in `wrangler.toml`. Do not read `~/.enablement_llm.env`. Studio Run is `force_offline=True` and works with no secret.
- GET `/` is Role Source (PR 14 composition). No lobby, no three-door, no marketing hero, no Get Lifetime Access, no Sign in, no Next.js, no React, no FastAPI, no SaaS LMS.

## Out of scope

- No Autonoma merge. No custom domain. No login.
- No new products.
