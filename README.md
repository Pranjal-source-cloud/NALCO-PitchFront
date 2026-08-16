# NALCO Anode Baking Furnace — Pitch Front Digital Tracking System

A production-quality Streamlit application for recording, tracking, and
visualizing Pitch Front observations on NALCO's two circular Anode Baking
Furnaces (ABF-II and ABF-III).

---

## 1. Project structure

```
NALCO_PitchFront_Streamlit_Final/
│
├── app.py            # Streamlit UI — all 4 pages, form logic, DB wiring
├── config.py          # Furnace/fire/FW constants, DB settings
├── database.py        # SQLAlchemy engine/session (cloud Postgres or local SQLite)
├── models.py           # ORM schema: Observation, PitchFrontEntry, ProcessReading
├── pitchfront.py       # Circular section math + form validation (no Streamlit code)
├── graph.py             # Plotly profile-sheet chart builder
├── utils.py              # Widget-key helper, CSV/Excel export, DataFrame flattening
├── requirements.txt
├── .env.example
└── README.md
```

Each module is independently testable — `pitchfront.py` and `graph.py`
contain no Streamlit code, so the circular-section math and the chart
construction can be unit-tested directly (see §7).

---

## 2. Running locally

```bash
cd NALCO_PitchFront_Streamlit_Final
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Using `python -m streamlit run app.py` (rather than a bare `streamlit`
command) avoids "command not found" issues on Windows when the Scripts
folder isn't on PATH.

With no `DATABASE_URL` set, the app automatically uses a local SQLite file
(`nalco_pitchfront.db`, created next to `app.py`) — this is for local
development only, see §4.

---

## 3. Application pages

| Page | Purpose |
|---|---|
| **Current Profile** | Select a Fire, view the latest **locked** observation as the profile chart. |
| **New Observation** | Fire → auto Furnace → Shift Incharge → Exhaust Ramp Section → FW1-FW9 pitch-front entry → Remarks → FW Temperature/Draft → live preview → Lock. |
| **History** | Filter locked observations by Fire / Furnace / Shift Incharge / date range; export CSV/Excel; view any past record's profile. |
| **Database Summary** | Counts by Fire/Furnace, latest observation, active DB backend. |

---

## 4. Database — local vs. production

The app is **not** designed around "everyone on the same Wi-Fi." It's built
so multiple Shift Incharges on different mobile networks all read and write
the same central database over HTTPS.

- **Production (recommended):** set `DATABASE_URL` to a Postgres/Supabase
  connection string. The app detects this automatically and uses it for
  every read/write. This is required for real multi-user, multi-network use.
- **Local development fallback:** if `DATABASE_URL` is unset, the app uses a
  local SQLite file (`LOCAL_SQLITE_PATH`, default `nalco_pitchfront.db`).
  This is single-machine only and must never be treated as the production
  system.

Copy `.env.example` to `.env` (or set the variables in your deployment
platform's secrets) and fill in your real connection string:

```
DATABASE_URL=postgresql://username:password@host:5432/database_name
```

`postgres://` URLs (as Supabase/Heroku sometimes hand out) are automatically
normalized to `postgresql://` for SQLAlchemy.

Tables are created automatically on first run (`init_db()` — safe to call
every startup; it only creates what's missing).

---

## 5. Deployment (Streamlit Community Cloud or similar)

1. Push this project to a GitHub repository.
2. On Streamlit Community Cloud, create a new app pointing at `app.py`.
3. In the app's **Secrets**, add:
   ```
   DATABASE_URL = "postgresql://username:password@host:5432/database_name"
   ```
4. Deploy. The app is served over HTTPS at a public URL — Shift Incharges
   open that URL from any Android phone, iPhone, tablet, or desktop, on any
   network. No LAN/localhost dependency exists anywhere in the code.

---

## 6. Key domain rules implemented

- **Terminology:** "Shift Incharge" is used everywhere in the UI (form,
  history, summary, export, hover text). "Operator" never appears.
- **"Behind" is never shown.** Every section is labeled by its actual number
  (e.g. `S17`, `S16`, `S15`); "behind_section_*" is only ever an internal
  Python variable name, never rendered.
- **Circular section math** (`pitchfront.circular_previous_section`):
  section 1's predecessor wraps to the furnace's last section
  (58 for ABF-II, 40 for ABF-III). Verified against every acceptance test
  in the original spec (§7 below).
- **No pitch-front input for the exhaust ramp section.** Only the two
  preceding sections (`section_2`, `section_3`) get a P1–P4 / "No Pitch
  Front" selector, for every FW.
- **Furnace is derived, never typed:** Fire-1/2/3 → ABF-II, Fire-4/5 → ABF-III.
- **Exhaust Ramp Section is always drawn at the TOP** of the profile chart,
  regardless of its numeric value, with the two preceding sections below it
  in physical (not numerical) order.
- **Locking is append-only.** Locking never overwrites a prior record — it
  inserts a brand-new `Observation` row. The *Current Profile* page always
  selects the most recently **locked** row per Fire (`ORDER BY locked_at
  DESC`); *History* shows all of them, forever.
- **No duplicate Streamlit widget keys.** Every widget key is built from
  `utils.make_widget_key(...)`, which folds in the field's role, FW number,
  section role, current Fire, and a form "nonce" that increments after every
  lock/reset — so keys stay unique and stable across reruns and across
  different Fire selections, avoiding `StreamlitDuplicateElementKey`.

---

## 7. Chart design notes

The chart in `graph.py` deliberately does **not** use a plain numeric
Y-axis of section numbers (that was the source of the original
unreadable graph). Instead:

- The Y-axis is divided into three **bands** — top (Exhaust Ramp Section,
  label only), middle (1st preceding section), bottom (2nd preceding
  section) — each internally showing **P4 (top) → P1 (bottom)**, exactly
  as on the paper profile sheet, with dashed grid lines and a solid
  separator between bands.
- The X-axis is always **FW1 → FW9**, in that fixed order — never sorted by
  section or value.
- There are **two line traces** (1st preceding section, 2nd preceding
  section), because every FW carries *two* independent pitch-front
  readings (one per preceding section), not one. Each trace connects its
  own FW1→FW9 sequence independently, strictly in FW order — a trace never
  "jumps" based on matching section/hole values between non-adjacent FWs.
  "No Pitch Front" (or an unentered value in the live preview) leaves a
  genuine gap in that trace rather than fabricating or interpolating a
  point.
- Hover text on every point shows Fire, FW, Section, Pitch Front position,
  Shift Incharge, FW Temperature, Draft, and observation time.
- FW Temperature and Draft are **never** plotted on the profile chart's
  axes — they're shown in a separate table (Current Profile page) and in
  hover text only, per the spec.

### Acceptance tests (verified during development)

All of the following were run against `pitchfront.py`, `graph.py`, and the
database layer directly (not just eyeballed):

- Fire-1 / ABF-II / Exhaust Ramp 17 → `S17, S16, S15` ✅
- Fire-1 / ABF-II / Exhaust Ramp 1 → `S1, S58, S57` ✅
- Fire-4 / ABF-III / Exhaust Ramp 1 → `S1, S40, S39` ✅
- ABF-II Exhaust Ramp 58 → `S58, S57, S56` ✅
- Fire-1 → Fire-4 changes Furnace ABF-II → ABF-III and section range 1–58 → 1–40 automatically ✅
- Locking two observations for the same Fire at different times: *Current
  Profile* uses the later one; *History* retains both ✅
- A third lock for the same Fire does not error or overwrite earlier
  records ✅
- Every graph trace preserves each FW's X-position even when that FW has no
  value for a given section, so a trace never silently connects two
  non-adjacent FWs across a gap (`connectgaps=False`) ✅

---

## 8. Security notes

- No credentials are hard-coded anywhere in the source. `DATABASE_URL` is
  read only from the environment (`.env` locally, platform secrets in
  production).
- The current version does not include a login screen. Structuring it this
  way was intentional: `database.py`/`app.py` are self-contained enough
  that an authentication layer (e.g. `streamlit-authenticator`, or a
  reverse-proxy SSO) can be dropped in front of `main()` without touching
  the data model.

---

## 9. Known extension points

- Additional process readings can be added by extending `ProcessReading`
  in `models.py` and the corresponding form fields in `app.py` — the schema
  was normalized specifically so this doesn't require touching
  `PitchFrontEntry` or `Observation`.
- Authentication/roles (§50 of the original spec) can be added as a
  thin wrapper around `main()` in `app.py`.
