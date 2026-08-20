# Enablement Studio

Local-first instructional design tools. One Python CLI, one SQLite file, three products.

I automated the work I used to do by hand as an ISD: turn a messy job or SOP into a skill graph and a 30-minute module, turn a transcript into coaching notes, and score whether a lesson's activity and quiz actually measure the objective. Each product is a specialist with a deterministic offline path. Versions land in a local database so you can list, show, and compare runs.

No login. No cloud database. Demos run without an API key.

## The three products

1. **Role → Enablement** — Paste a job posting or SOP. Get a skill graph, measurable objectives, a 30-minute outline, a practice activity, and a short quiz.
2. **Call → Coach** — Paste a sales or training transcript. Get three short notes (learner, customer, coach) and one concrete enablement fix.
3. **Lesson critic** — Paste a lesson outline or storyboard. Get alignment scores (objective → activity → assessment) and a rewrite of the weakest part.

## Install

Python 3.11+ on a MacBook Air is enough.

```bash
git clone https://github.com/ryanclawjr/enablement-studio.git
cd enablement-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The SQLite file is created at `data/enablement.db` on first run. That file is gitignored. The schema is checked in as `data/schema.sql`.

## Run one demo of each

These commands use fictional sample files under `fixtures/`. They do not call a network API.

```bash
enablement demo role
enablement demo call
enablement demo critic
```

Equivalent file form:

```bash
enablement role --file fixtures/example_account_executive_job.txt --project example
enablement call --file fixtures/example_sales_call.txt --project example
enablement critic --file fixtures/example_new_hire_lesson.md --project example
```

Then inspect versions:

```bash
enablement list
enablement show 1
enablement compare 1 2
```

`pytest` exercises the same offline path. No keys required.

## Local UI

Same three products, same SQLite file, no API key.

```bash
enablement serve
```

That binds **127.0.0.1:8765** (loopback only; pass `--host` / `--port` to change). Open http://127.0.0.1:8765, pick Role / Call / Critic, paste a job, SOP, transcript, or outline, or load a packaged demo fixture. Run writes to the same `data/enablement.db` the CLI uses. There is no login and no cloud database.

## Sample data

The three demo fixtures are labeled **EXAMPLE DATA**. Harborline Payments, Maple Street Bakery, Alex Rivera, and Jordan Kim are invented. Rates, promos, and quotas in the samples are not real and are not from a live employer or customer.

`fixtures/eval_stripe_sa_enablement_job.txt` is a sanitized **PUBLIC POSTING** copy used to eval Role on an enablement job. It is not fictional sample copy.

## Optional LLM

The default engine is offline and deterministic. To try an LLM, set `ENABLEMENT_LLM_API_KEY` (or `OPENAI_API_KEY`) and optionally `ENABLEMENT_LLM_BASE_URL` and `ENABLEMENT_LLM_MODEL`. The hook is OpenAI-shaped: `POST {base}/chat/completions` with `temperature` 0 and `response_format` `json_object`. No reasoning / `reasoning_effort` / thinking fields. Default model is `gpt-4.1-mini`. Default base is `https://api.openai.com/v1`. Timeout is 20 seconds — Harborline Role JSON is about 6KB of structured output, and 8 seconds was tight. Each product has its own system prompt that names the existing JSON shape and the PRODUCT.md rules. If the call fails or the JSON does not match the schema, the CLI falls back to the offline engine. Demos and CI leave these unset.

## Layout

```
src/enablement_studio/
  role/      # Role → Enablement
  call/      # Call → Coach
  critic/    # Lesson critic
  prompts.py # Per-product LLM system prompts
  serve.py   # Local UI (stdlib http.server)
  store/     # SQLite projects, runs, artifacts
fixtures/    # Fictional demo inputs
data/        # schema.sql; enablement.db created locally
```

## License

MIT. See [LICENSE](LICENSE).
