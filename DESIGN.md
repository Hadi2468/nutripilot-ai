# NutriPilot AI: Design

This document explains *why* the service is shaped the way it is: the output contract, the
checks, the repair loop, the safety rules, the deployment and the trade-offs.

---

## 1. Problem

Turn a short profile (calories, meals per day, goal, age, diet style, allergies, dislikes,
health conditions) into a usable seven-day meal plan, plus single meals, nutrient estimates,
healthier swaps and tips.

v1 sent one prompt per feature and returned the model's free text. Three failure modes
drove the redesign:

1. **Wrong numbers.** LLMs are poor at arithmetic over long outputs. A "2,000 kcal" plan
   often totals 1,600-2,400 kcal per day, and nothing noticed.
2. **Unsafe content.** "No peanuts" in a prompt is a request, not a guarantee. A single
   peanut sauce in 28 meals is a serious failure for someone with an allergy.
3. **Unusable shape.** Free text cannot be charted, revised reliably or tested. The only
   v1 check was whether the strings "Day 1" ... "Day 7" appeared.

The design rule, shared with BMIPilot AI: **numbers from code, words from the LLM,
guardrails from code.**

## 2. Output contract

Every feature has a Pydantic schema for what the model must return (`schemas.py`):

| Feature | LLM returns | Code adds |
|---|---|---|
| Plan / regenerate | `WeeklyPlan`: days → meals (name, dish, ingredients, kcal, protein, carbs, fat), notes | `totals` per day (computed field) |
| Meal | `Meal` | — |
| Analysis | `NutritionAnalysis`: items (food, quantity, kcal, macros) | `totals` (computed field) |
| Substitute | `Substitutions`: original, alternative, why | — |
| Tips | `Tips`: tip, why | — |

The schema is embedded in the system prompt and the request uses JSON mode
(`response_format={"type": "json_object"}`), which both Groq and OpenAI support. Strict
`json_schema` mode would be tighter but is not available for every model on every provider;
Pydantic validation plus repair covers the gap and keeps the provider switch a one-line setting.

Totals are `computed_field`s: if the model sends its own `totals`, they are ignored and
recomputed from the meals.

Every response is wrapped in an `Envelope`: `type`, `data`, `warnings`, `meta` (provider,
model, prompt version, latency, tokens, repairs) and the `disclaimer`.

## 3. Checks

`checks.py` holds pure functions; each returns a list of problems.

| Check | Rule |
|---|---|
| Plan structure | Exactly days 1-7, once each; every day has `meal_count` meals |
| Daily calories | Each day within `calorie_tolerance` (default ±10%) of the target; the prompt asks for ±5% so the model aims inside the gate |
| Excluded foods | No allergy or dislike in any dish name or ingredient. Matching is whole-word, case-insensitive and plural-aware: `eggs` catches "1 egg", `peanuts` catches "peanut butter", but `nut` does not match "peanut" or "nutmeg" |
| Meal | Excluded foods, calories within tolerance |
| Substitutions | No excluded food in any alternative |
| Analysis | No item with 0 kcal but non-zero macronutrients |
| Tips | Exactly five |

**Warnings (non-blocking).** A meal or food whose calories differ by more than 25% from
4·protein + 4·carbs + 9·fat is reported in `warnings`. It signals an arithmetic slip but is
not dangerous, and fibre, alcohol and rounding make the rule approximate, so it does not
trigger a repair.

**Known limit.** Text matching cannot know that "satay sauce" contains peanuts. The prompt
tells the model to avoid excluded foods *and* to list main ingredients; the check catches
what is written. A food-composition lookup is on the roadmap.

## 4. Repair loop

```text
messages = [system, user]
for attempt in 0..max_repairs:
    reply  = llm(messages)
    result = parse(reply)           # Pydantic; a parse error is a problem too
    problems = check(result)
    if no problems: return result, meta(repairs=attempt)
    messages += [assistant: reply, user: "Your previous answer failed these checks: ..."]
raise OutputValidationError(problems)   # → HTTP 502 with the problems
```

- The repair prompt lists **concrete, checkable** problems ("Day 3 totals 1,640 kcal but
  the target is 2,000 kcal"), which models fix far more reliably than "try again".
- The budget is **bounded** (`max_repairs`, default 1). Unbounded loops cost money and,
  behind API Gateway's 30 s limit, would time out anyway.
- After the budget, the service **fails** rather than returning a plan that breaks a rule.
  For allergens this is the only acceptable choice; for calories it is a deliberate
  consistency choice, and the tolerance is configurable.
- Tokens are summed across attempts and `repairs` is reported, so the cost of quality is visible.

## 5. Safety policy

| Rule | Where |
|---|---|
| No weight-loss plans under 18 (422, suggest "healthy eating") | `PlanRequest` validator |
| No adult plans below 1,200 kcal/day (422) | `PlanRequest` validator |
| Input bounds: age 2-120, 1,000-5,000 kcal, 1-6 meals; text length limits | Pydantic fields |
| Children: write for the caregiver, no restriction; teens: no dieting, positive food relationship; 65+: protein, hydration, no aggressive deficits | `policy.audience_guidance` in the prompt |
| Health conditions: use accepted dietary guidance, never suggest changing medication or claim to treat; add a clinician warning to the response | `policy.conditions_guidance` + `CONDITIONS_WARNING` |
| User text is data: analysis and swap prompts say to treat it only as a list of foods | `prompts.py` |
| Disclaimer on every response, in the CLI and in the dashboard | `policy.DISCLAIMER` |

Prompts tell the model the rules; code makes sure the rules that can be checked actually hold.

## 6. LLM adapter

Groq and OpenAI both implement the OpenAI Chat Completions API, so `llm.py` uses the
`openai` SDK with a provider-specific `base_url`. This keeps the Lambda package small
(no LangChain), and switching providers is `NUTRIPILOT_PROVIDER=openai`.

The service depends on a two-method `ChatModel` protocol, not on the SDK. Tests inject a
scripted `FakeLLM`; nothing in the suite needs a key or the network.

Provider errors are translated: rate limits → 429, anything else → 503. Missing keys are
detected when the service is first used, not at import, so the app (and its health check)
starts without secrets.

## 7. Interfaces

One `NutriPilotService` backs the REST API, the CLI and, through the API, the dashboard.

- **API** (`api.py`): sync handlers (FastAPI runs them in a threadpool, so a slow LLM call
  does not block the event loop); constant-time bearer-token comparison; `/health` is open
  for load balancers and container health checks.
- **CLI** (`cli.py`): the same features with Rich tables, or `--json`.
- **Dashboard** (`dashboard/app.py`): a thin API client. A plan is kept in session state, so
  "revise" sends the structured plan and the original profile back to `/plan/regenerate`.

## 8. Deployment

```text
Client ──HTTPS──▶ API Gateway (HTTP API, throttled) ──▶ Lambda (arm64, Python 3.13)
                                                        FastAPI + Mangum
                                                        │  cold start: Secrets Manager → env
                                                        ▼
                                                   Groq / OpenAI
```

- **HTTP API** instead of a REST API: cheaper and simpler for a proxy integration. Its
  integration timeout is 30 s, so the Lambda timeout is 30 s, each LLM call is capped at
  12 s with no SDK retries, and the plan plus one repair has to fit inside that.
- A named stage prefixes every path (`/prod/health`); `NUTRIPILOT_BASE_PATH` tells Mangum
  to strip it. (Without it every route returns 404, which is covered by a test.)
- **Secrets Manager** instead of plain environment variables: keys are not visible in the
  Lambda console or the template. The secret is a JSON object of env-var names, loaded once
  per cold start without overriding variables that are already set.
- **Fail-closed auth**: the template sets `NUTRIPILOT_AUTH_REQUIRED=true`, so a missing token
  in the secret returns 503 instead of opening the API.
- The same image runs the API and the dashboard locally with Docker Compose.

## 9. Trade-offs and future work

- **Calorie targets come from the user.** Computing them (Mifflin-St Jeor with activity
  level) would add another deterministic layer and stop unrealistic targets earlier.
- **Nutrient values are model estimates.** Grounding them in USDA FoodData Central through a
  tool call would make analysis numbers verifiable rather than plausible.
- **Allergen matching is lexical.** It catches what is written, not hidden ingredients
  (sauces, pastes). A curated allergen-to-ingredient map would close part of that gap.
- **No offline eval set yet.** Measuring allergen recall, calorie accuracy and repair rate
  per model would turn these guarantees into numbers and guide the provider and model choice.
- **Single-shot plan generation.** Seven days in one call is the slowest request. Generating
  days in parallel and checking each one would cut latency at the cost of variety across the week.
