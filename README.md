# Enablement Studio

Tablework is the product name. The repo and package stay enablement-studio.

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

Same three products, same SQLite file, no API key. The product on the page is **Tablework**.

```bash
enablement serve
```

That binds **127.0.0.1:8765** (loopback only; pass `--host` / `--port` to change). `--host 0.0.0.0` prints a warning: stored job postings and transcripts would be on the LAN with no auth. Open http://127.0.0.1:8765.

`/` is Role Source: one job document on a full-bleed `#16161d` table, with the path as six objects on the grid (Source, Graph, Objectives, Outline, Practice, Quiz). Type is local Instrument Sans. Run hover is a yellow glow, not a lift. `/role` is the same studio. Paste a job or SOP, Run, or Run Harborline (EXAMPLE DATA). Chrome is dark Tablework with a yellow accent. The walk is those six objects, not a dump of all five Role artifacts and not a three-door landing. One `generate()` still returns the whole Role module; the UI reveals it one step at a time. After Run, you land on Graph and the sheet shows that step. Opening `/` with no run is Source. Harborline is a muted text action on the sheet. **Run is offline** and returns a board without waiting on a network, even if `ENABLEMENT_LLM_API_KEY` is set. LLM is optional polish on the same `generate()` hook and must not freeze other tabs. Versions are dots in the sheet footer. Job family and EnablementFrame (enablement family only) are labeled on Graph. Invalid Role runs stop the walk on Graph in plain English. An empty Run stays on Source with that English validation. History is this project and product; two Role runs can be compared. Call and Critic are a quiet next line (no walkthrough yet). POSTs from a foreign Origin or Referer are rejected; curl and same-origin form posts still work. Run writes to the same `data/enablement.db` the CLI uses. There is no login. The public host (below) is a separate per-visitor store, not this file.

## Public host

Same Role Source, same `generate(..., force_offline=True)` as `enablement serve`. The loopback server is unchanged. Cloudflare Python Workers cannot run `http.server` / `threading`; both hosts call the pure handler in `src/enablement_studio/handler.py`.

Preferred public URL (Pages project, same family as autonoma-intelligence): **https://enablement-studio.pages.dev**. No custom domain.

From a Cloudflare-authenticated Air (uv + Node):

```bash
uvx --from workers-py pywrangler deploy
```

After `pip install -e ".[cloudflare]"` (or `uv add --optional cloudflare`):

```bash
uv run pywrangler deploy
```

`wrangler pages deploy` is the Autonoma static path. This app is a Python Worker, so `pywrangler deploy` is the command that publishes `generate()` + the Role Source HTML. Create a Pages project named `enablement-studio` once in the dashboard and attach this Worker to get the `pages.dev` hostname. The Worker name is `enablement-studio`; the immediate Workers URL is `https://enablement-studio.<subdomain>.workers.dev`.

Public pastes are not a shared guestbook. Each visitor gets a session cookie. Their sqlite lives in a temp file for the request, then the bytes go to a Durable Object (KV-shaped key + TTL). Local Air still uses `data/enablement.db`.

Optional LLM on the Worker is the secret `ENABLEMENT_LLM_API_KEY`:

```bash
npx wrangler secret put ENABLEMENT_LLM_API_KEY
```

Do not set it for this cut. Do not put the key in `wrangler.toml`. Do not read `~/.enablement_llm.env`. Offline Run works with no secret.

## Sample data

The three demo fixtures are labeled **EXAMPLE DATA**. Harborline Payments, Maple Street Bakery, Alex Rivera, and Jordan Kim are invented. Rates, promos, and quotas in the samples are not real and are not from a live employer or customer.

`fixtures/eval_stripe_sa_enablement_job.txt` is a sanitized **PUBLIC POSTING** copy used to eval Role on an enablement job. It is not fictional sample copy.

## Optional LLM

The default engine is offline and deterministic. Studio **Run** always uses that path (`generate(..., force_offline=True)`). To try an LLM from the CLI, or from the studio **LLM** button, set `ENABLEMENT_LLM_API_KEY` (or `OPENAI_API_KEY`) and optionally `ENABLEMENT_LLM_BASE_URL` and `ENABLEMENT_LLM_MODEL`. The hook is OpenAI-shaped: `POST {base}/chat/completions` with `temperature` 0 and `response_format` `json_object`. No reasoning / `reasoning_effort` / thinking fields. Default model is `gpt-4.1-mini`. Default base is `https://api.openai.com/v1`. Timeout is 20 seconds and must actually bound the urllib call — Harborline Role JSON is about 6KB of structured output, and 8 seconds was tight. Each product has its own system prompt that names the existing JSON shape and the PRODUCT.md rules. If the call fails or the JSON does not match the schema, the engine falls back to offline. A key in the environment must not freeze `enablement serve`. Demos and CI leave these unset.

## Layout

```
src/enablement_studio/
  role/      # Role → Enablement
  call/      # Call → Coach
  critic/    # Lesson critic
  prompts.py # Per-product LLM system prompts
  handler.py # Pure HTTP handler (local + Worker)
  serve.py   # Local UI (stdlib ThreadingHTTPServer)
  store/     # SQLite projects, runs, artifacts
src/worker.py # Cloudflare Python Worker entry
wrangler.toml
fixtures/    # Fictional demo inputs
data/        # schema.sql; enablement.db created locally
```

## License

MIT. See [LICENSE](LICENSE).
