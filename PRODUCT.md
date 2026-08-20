# Enablement Studio product contract

Audience: humans and agents working this repo.

This file is the definition of good. Enablement Studio v0 already has typed outputs and an offline engine. Later LLM prompts and evals must satisfy this contract. They are not written here.

Passing the Harborline Account Executive demo is the happy path only. It does not certify Role on other jobs.

## Why this file exists

The offline Role path looks right on `fixtures/example_account_executive_job.txt` and fails on a real enablement job posting. It pastes the new title onto a sales-discovery / "before presenting price" template. The skill graph, practice, and quiz remain a seller module.

This file names what good means so the next sitting can change prompts and tests against it.

## Spine

Keep these. Do not grow them in this sitting.

- Three products only: Role → Enablement, Call → Coach, Lesson critic.
- One entry point: `generate(product, text)` in `src/enablement_studio/engine.py`.
- One local SQLite store. Each save is a versioned run. `list`, `show`, and `compare` read that store.
- The dataclasses and JSON shapes in `src/enablement_studio/models.py` are the API. CLI, later UI, offline engine, and LLM all emit the same objects: `RoleEnablement`, `CallCoaching`, `LessonCritique`.
- The offline path never dies. Demos, CI, and interviews run with no API key. If an LLM call fails or the JSON does not match the schema, fall back to offline.
- No LAPC, WarU, Autonoma, IDN, SIGNIT, or subscriber/PII content in fixtures or docs. Demo data stays labeled EXAMPLE DATA.
- Local-first. Domain and hosting are later work. This file does not specify them.

## Role → Enablement

Input is a job posting or a messy SOP.

Output already exists on `RoleEnablement`: a skill graph, measurable objectives, a 30-minute outline, a practice activity, and a quiz.

The module trains the person who will do **this** job. It does not decorate a generic seller module with a new title.

### Rules

1. The skill graph is for this job. Extract skills from the source text. Do not stamp a generic account-executive / discovery / price template onto every title.
2. If the job is an enablement, L&D, or coaching role, the learner is a person doing that job. In-scope work includes gap analysis, onboarding design, technical packaging, launch readiness, and impact metrics. Do not treat every JD as "train this person to sell."
3. If the job is a seller, SE, or SA in the field, seller skills are in-bounds: discovery, demo, objection handling, and the like.
4. Every objective verb must appear in the graph. Practice and quiz must measure those same verbs.
5. Fail the run, or mark it invalid, if the module could be reused on a random AE job by swapping the title. That check is the title-swap test.
6. Known failure (public posting, not an application): Stripe Solution Architect Enablement Business Partner, Greenhouse 8115022, listed at [stripe.com/careers](https://stripe.com/careers/listing/solution-architect-enablement-business-partner/8115022). Offline v0 kept AE discovery, price, and CRM next-step quiz items after swapping in the title. A passing Role run on that JD talks about SA onboarding, technical packaging for a sales audience, launch readiness, and enablement impact metrics.

Rule 2 applies to an enablement partner who supports solution architects. That person is not a field SA. Rule 3 does not win because the title contains "Solution Architect."

### Title-swap test

Take a finished Role module. Replace only the role title with "Account Executive" or another unrelated seller title. If the skill graph, practice, and quiz still read as a coherent module for that seller, the run fails.

The Harborline AE fixture may look like an AE module. The source is an AE posting. The Stripe enablement JD is the counterexample. A passing module does not ask what to do before presenting price, and does not treat CRM next-step logging as the proof of skill.

v0 has no invalid flag on `RoleEnablement`. When this contract is implemented, a title-swap failure must not be stored as a successful Role run. Either refuse to save or persist a run marked invalid so `list`, `show`, and eval can see the miss. Do not silently emit the AE template.

## Call → Coach

Input is a sales or training transcript.

Output already exists on `CallCoaching`.

- Notes for learner, customer, and coach. No other audiences.
- Exactly one enablement fix, tied to a signal that appears in the transcript.
- Do not invent speakers or facts that are not in the source.
- The fix is a drill or artifact a manager can run, plus a measure.

Speakers come from the transcript. A call that never mentions price does not get a discovery-before-rate drill unless a listed signal justifies it. A note that invents a buyer problem the transcript never stated is a miss.

## Lesson critic

Input is a lesson outline or storyboard.

Output already exists on `LessonCritique`.

- Scores from 1 to 5 for objective clarity, activity alignment, and assessment alignment. `AlignmentScores.overall` is the rounded mean of those three, as the type already stores.
- Findings explain the scores.
- Rewrite the weakest part so the activity or assessment practices the same verb as the objective.

A scavenger-hunt activity against "explain interchange" fails alignment. The rewrite must make the learner practice that verb, not a different one, and not a logistics check.

## Eval

Specify only. Do not add cases in this sitting.

- Keep the three fictional fixtures for the happy-path demos: `example_account_executive_job.txt`, `example_sales_call.txt`, `example_new_hire_lesson.md`. They stay labeled EXAMPLE DATA.
- Add a later eval case: the Stripe SA Enablement JD, or a sanitized copy labeled as a public posting. Role must fail the title-swap test on that case today and pass after this contract is implemented.
- `pytest` stays green with no API keys. LLM work is a later sitting.

Do not check the Stripe JD into this sitting. When it is added, label it as a public posting, not as fictional EXAMPLE DATA, and do not include application materials or subscriber/PII.

## Out of scope this sitting

- No LLM prompt rewrite.
- No local web UI.
- No domain, hosting, or Autonoma merge.
- No new products.

This sitting is the contract only.
