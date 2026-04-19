"""
LexAnnotate — Legal Document Annotation Pipeline
Two-pass Claude API workflow:
  Pass 1: Annotate document text against concept definitions (NER-style)
  Pass 2: Auto-generate information-extraction prompts from annotations
"""

import os
import json
import anthropic
import gradio as gr

# ---------------------------------------------------------------------------
# Default concept definitions
# ---------------------------------------------------------------------------
DEFAULT_CONCEPTS = """\
INDEMNITY: A clause where one party agrees to compensate the other for specific losses or damages.
GOVERNING_LAW: The jurisdiction whose laws govern the interpretation of the contract.
LIMITATION_OF_LIABILITY: A clause that caps the maximum liability of a party.
TERMINATION: Conditions under which the contract can be ended by either party.
CONFIDENTIALITY: Obligations to keep certain information private.
PAYMENT_TERMS: Terms specifying amounts, schedules, or conditions of payment.
INTELLECTUAL_PROPERTY: Ownership, licensing, or transfer of IP rights.
FORCE_MAJEURE: Events beyond a party's control that excuse non-performance.\
"""

DEFAULT_DOCUMENT = """\
This Agreement is governed by the laws of the State of Delaware.

Either party may terminate this Agreement upon 30 days written notice. Immediate termination
is permitted in the event of a material breach that remains uncured for 15 days after notice.

Each party agrees to indemnify and hold harmless the other party from any claims, damages,
or liabilities arising from its own negligence or wilful misconduct.

In no event shall either party's liability exceed the total fees paid in the twelve months
preceding the claim. Neither party shall be liable for indirect, incidental, or consequential damages.

All proprietary information disclosed under this agreement shall be kept confidential
and not disclosed to third parties without prior written consent.

Payment is due within 30 days of invoice date. Late payments will accrue interest at 1.5% per month.\
"""

# ---------------------------------------------------------------------------
# Claude client (reads ANTHROPIC_API_KEY from environment)
# ---------------------------------------------------------------------------
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


# ---------------------------------------------------------------------------
# Pass 1 — Annotation
# ---------------------------------------------------------------------------
def run_pass1_annotation(document_text: str, concepts_text: str) -> tuple[str, list[dict]]:
    """Annotate the document against concept definitions. Returns (formatted_str, raw_list)."""

    system_prompt = """You are a legal document annotation engine.
You will be given:
1. A set of legal concept definitions (name: description)
2. A legal document excerpt

Your task is to identify spans in the document that match any of the concepts.
Respond ONLY with a JSON array. Each element must have:
  - "concept": the concept name (uppercase, from the definitions)
  - "span": the exact text span from the document
  - "start_char": approximate character offset (integer)
  - "rationale": one sentence explaining the match

Return [] if nothing matches. No markdown, no explanation — just the JSON array."""

    user_prompt = f"""## Concept Definitions
{concepts_text}

## Document
{document_text}

Annotate the document. Return JSON array only."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    annotations = json.loads(raw)

    # Build human-readable display
    lines = [f"Found **{len(annotations)}** annotation(s)\n"]
    for i, ann in enumerate(annotations, 1):
        lines.append(
            f"### {i}. `{ann['concept']}`\n"
            f"**Span:** _{ann['span']}_\n\n"
            f"**Rationale:** {ann['rationale']}\n"
        )

    return "\n".join(lines), annotations


# ---------------------------------------------------------------------------
# Pass 2 — Prompt Generation
# ---------------------------------------------------------------------------
def run_pass2_prompts(annotations: list[dict], document_text: str) -> str:
    """Generate tailored IE prompts from annotations. Returns formatted markdown."""

    if not annotations:
        return "_No annotations found — run Pass 1 first._"

    system_prompt = """You are an expert prompt engineer specialising in legal information extraction.
Given a list of annotations (concept + span + rationale) from a legal document,
generate a precise information-extraction prompt for EACH unique concept found.

Each prompt should:
- Be self-contained (include the concept definition)
- Ask Claude to extract the relevant information from a document
- Request structured JSON output
- Handle cases where the concept is absent

Respond ONLY with a JSON object where keys are concept names and values are the prompt strings.
No markdown fences, no preamble — just the JSON object."""

    user_prompt = f"""## Annotations
{json.dumps(annotations, indent=2)}

## Original Document (for context)
{document_text}

Generate one extraction prompt per unique concept. Return JSON object only."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    prompts: dict = json.loads(raw)

    lines = [f"Generated **{len(prompts)}** extraction prompt(s)\n"]
    for concept, prompt_text in prompts.items():
        lines.append(f"### `{concept}`\n```\n{prompt_text}\n```\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gradio pipeline wrappers
# ---------------------------------------------------------------------------
_annotation_cache: list[dict] = []  # module-level cache between passes


def gradio_pass1(document_text: str, concepts_text: str, api_key: str):
    global _annotation_cache
    _annotation_cache = []

    if not document_text.strip():
        return "⚠️ Please provide document text.", gr.update(interactive=False)
    if not concepts_text.strip():
        return "⚠️ Please provide concept definitions.", gr.update(interactive=False)

    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "⚠️ No API key provided.", gr.update(interactive=False)

    global client
    client = anthropic.Anthropic(api_key=key)

    try:
        result_md, annotations = run_pass1_annotation(document_text, concepts_text)
        _annotation_cache = annotations
        return result_md, gr.update(interactive=bool(annotations))
    except json.JSONDecodeError as e:
        return f"❌ Could not parse Claude's response as JSON.\n\n{e}", gr.update(interactive=False)
    except anthropic.AuthenticationError:
        return "❌ Invalid API key.", gr.update(interactive=False)
    except Exception as e:
        return f"❌ Error: {e}", gr.update(interactive=False)


def gradio_pass2(document_text: str, api_key: str):
    global _annotation_cache

    if not _annotation_cache:
        return "⚠️ Run Pass 1 (Annotate) first."

    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "⚠️ No API key provided."

    global client
    client = anthropic.Anthropic(api_key=key)

    try:
        return run_pass2_prompts(_annotation_cache, document_text)
    except Exception as e:
        return f"❌ Error: {e}"


def export_annotations():
    if not _annotation_cache:
        return gr.DownloadButton(value=None)
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "lexannotate_annotations.json")
    with open(path, "w") as f:
        json.dump(_annotation_cache, f, indent=2)
    return gr.DownloadButton(value=path)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
THEME = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
)

CSS = """
#title { text-align: center; margin-bottom: 8px; }
#subtitle { text-align: center; color: #6b7280; margin-bottom: 24px; }
.pass-header { font-weight: 600; font-size: 1rem; margin-bottom: 4px; }
"""

with gr.Blocks(theme=THEME, css=CSS, title="LexAnnotate") as demo:

    gr.Markdown("# ⚖️ LexAnnotate", elem_id="title")
    gr.Markdown(
        "Legal Document Annotation Pipeline — two-pass Claude workflow",
        elem_id="subtitle",
    )

    # ── API Key ──────────────────────────────────────────────────────────────
    with gr.Accordion("🔑 API Key", open=not bool(os.environ.get("ANTHROPIC_API_KEY"))):
        api_key_input = gr.Textbox(
            label="Anthropic API Key",
            placeholder="sk-ant-... (leave blank if set via ANTHROPIC_API_KEY env var)",
            type="password",
            show_label=True,
        )

    gr.Markdown("---")

    # ── Inputs ───────────────────────────────────────────────────────────────
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📄 Document")
            document_input = gr.Textbox(
                value=DEFAULT_DOCUMENT,
                label="Paste legal document text",
                lines=18,
                max_lines=40,
                placeholder="Paste contract text here…",
                show_label=False,
            )

        with gr.Column(scale=1):
            gr.Markdown("### 🏷️ Concept Definitions")
            concepts_input = gr.Textbox(
                value=DEFAULT_CONCEPTS,
                label="One concept per line: NAME: description",
                lines=18,
                max_lines=40,
                placeholder="INDEMNITY: A clause where one party agrees to compensate…",
                show_label=False,
            )

    gr.Markdown("---")

    # ── Pass 1 ───────────────────────────────────────────────────────────────
    gr.Markdown("## Pass 1 — Annotate")
    gr.Markdown(
        "Identifies spans in the document that match your concept definitions.",
        elem_classes="pass-header",
    )

    run_pass1_btn = gr.Button("▶ Run Annotation", variant="primary", size="lg")

    annotation_output = gr.Markdown(label="Annotation Results")

    with gr.Row():
        export_btn = gr.DownloadButton(
            label="⬇ Export Annotations JSON",
            size="sm",
            variant="secondary",
        )

    gr.Markdown("---")

    # ── Pass 2 ───────────────────────────────────────────────────────────────
    gr.Markdown("## Pass 2 — Generate Extraction Prompts")
    gr.Markdown(
        "Auto-generates a tailored IE prompt for each concept found in Pass 1.",
        elem_classes="pass-header",
    )

    run_pass2_btn = gr.Button(
        "▶ Generate Prompts", variant="secondary", size="lg", interactive=False
    )

    prompt_output = gr.Markdown(label="Generated Prompts")

    # ── Wiring ───────────────────────────────────────────────────────────────
    run_pass1_btn.click(
        fn=gradio_pass1,
        inputs=[document_input, concepts_input, api_key_input],
        outputs=[annotation_output, run_pass2_btn],
    )

    run_pass2_btn.click(
        fn=gradio_pass2,
        inputs=[document_input, api_key_input],
        outputs=[prompt_output],
    )

    export_btn.click(
        fn=export_annotations,
        inputs=[],
        outputs=[export_btn],
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile
    demo.launch(share=False, allowed_paths=[tempfile.gettempdir()])
