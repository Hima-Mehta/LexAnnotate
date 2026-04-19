
# ⚖️ LexAnnotate

A two-pass legal document annotation pipeline powered by Claude, with a Gradio web UI.

---

## What it does

LexAnnotate takes a legal document and a set of concept definitions, then runs two sequential Claude API calls:

**Pass 1 — Annotate**
Identifies spans in the document that match your concept definitions (INDEMNITY, GOVERNING_LAW, TERMINATION, etc.). Returns each matched span with the concept name, exact text, character offset, and a one-sentence rationale.

**Pass 2 — Generate Extraction Prompts**
Takes the Pass 1 annotations and auto-generates a tailored, self-contained Claude information-extraction prompt for every unique concept found. Each generated prompt requests structured JSON output and handles cases where the concept is absent — ready to drop into your own pipelines.

---

## Concepts supported (defaults)

| Concept | Description |
|---|---|
| `INDEMNITY` | Compensation clause for losses or damages |
| `GOVERNING_LAW` | Jurisdiction governing contract interpretation |
| `LIMITATION_OF_LIABILITY` | Caps on maximum party liability |
| `TERMINATION` | Conditions for ending the contract |
| `CONFIDENTIALITY` | Obligations to keep information private |
| `PAYMENT_TERMS` | Amounts, schedules, or conditions of payment |
| `INTELLECTUAL_PROPERTY` | Ownership, licensing, or transfer of IP rights |
| `FORCE_MAJEURE` | Events excusing non-performance |

You can edit these freely in the UI — add your own, remove ones you don't need, or replace them entirely.

---

## Setup

### Prerequisites

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/)

### Install

```bash
git clone https://github.com/yourname/lexannotate.git
cd lexannotate
pip install -r requirements.txt
```

### Run

```bash
# Option A — set API key as environment variable (recommended)
export ANTHROPIC_API_KEY=sk-ant-...
python app.py

# Option B — paste API key in the UI accordion instead
python app.py
```

Then open **http://localhost:7860** in your browser.

---

## Usage

1. **Paste your document** in the left panel (or use the built-in example contract).
2. **Edit concept definitions** in the right panel — one per line, format: `NAME: description`.
3. Click **▶ Run Annotation** → Pass 1 runs; matched spans appear with rationale.
4. Click **▶ Generate Prompts** → Pass 2 generates a Claude IE prompt per concept.
5. Click **⬇ Export Annotations JSON** to download the raw Pass 1 output.

> **Note:** Pass 2 is only enabled after a successful Pass 1 run that returns at least one annotation.

---

## Output format

### Pass 1 — Annotations JSON

```json
[
  {
    "concept": "GOVERNING_LAW",
    "span": "governed by the laws of the State of Delaware",
    "start_char": 24,
    "rationale": "Specifies Delaware law as the governing jurisdiction for the agreement."
  },
  {
    "concept": "TERMINATION",
    "span": "Either party may terminate this Agreement upon 30 days written notice",
    "start_char": 73,
    "rationale": "Sets out the conditions and notice period for terminating the contract."
  }
]
```

### Pass 2 — Generated Prompts

One extraction prompt per concept, structured to request JSON output from Claude. Example:

```
You are a legal document analysis assistant. Extract any GOVERNING_LAW clause from
the document below. GOVERNING_LAW refers to the jurisdiction whose laws govern the
interpretation of the contract.

Return a JSON object: {"governing_law": "<jurisdiction or null>", "verbatim_clause": "<exact text or null>"}

Document:
{document}
```

---

## Project structure

```
lexannotate/
├── app.py            # Entire application — Gradio UI + Claude pipeline
├── requirements.txt  # gradio, anthropic
├── .gitignore
└── README.md
```

---

## Model

Uses `claude-sonnet-4-20250514` for both passes. Both prompts instruct Claude to return pure JSON (no markdown fences), with fallback stripping if fences appear anyway.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `AuthenticationError` | Check your API key — must start with `sk-ant-` |
| `JSONDecodeError` on Pass 1 | The document may be too short or ambiguous; try adding more text |
| Export button does nothing | Run Pass 1 first — the export is empty until annotations exist |
| Gradio `InvalidPathError` | Ensure you're on the latest commit; `allowed_paths` is set in `launch()` |

---

## License

MIT
