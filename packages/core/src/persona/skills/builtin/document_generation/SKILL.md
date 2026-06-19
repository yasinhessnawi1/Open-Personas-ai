---
name: document_generation
description: Produce a downloadable document (docx, pdf, pptx, xlsx, md, txt) by writing code in the sandbox, routed by a format parameter.
when_to_use: >
  Use when the user wants a document FILE they can download — a Word doc, PDF,
  PowerPoint, Excel workbook, Markdown file, or plain-text file (not prose in
  the chat). Pass format=docx|pdf|pptx|xlsx|md|txt. For prose-then-format, draft
  the prose in your own context first, then activate this skill and embed the
  prose as a Python string. This skill also COVERS condensing/summarising source
  material into a brief — say so via content_spec. Skip for inline replies.
tools_required:
  - code_execution
metadata:
  parameters:
    type: object
    additionalProperties: false
    required: [format]
    properties:
      format:
        type: string
        enum: [docx, pdf, pptx, xlsx, md, txt]
        description: Output file format. Routes to the matching handler.
      template:
        type: string
        enum: [memo, report, business_letter, research_paper]
        description: Optional starting structure; its Markdown is staged for you to follow.
      domain:
        type: string
        description: Optional domain hint (e.g. legal, business, academic) for tone.
      content_spec:
        type: object
        description: Structured content to render (title, sections, summary, ...).
  not_for:
    - Inline chat replies or single-paragraph answers — just write the text.
    - Reading or parsing an existing document — that is document ingestion, not generation.
    - A format outside the registered six — add a handler module, do not improvise.
  composes_with:
    - web_research
    - code_review
  output_format: A file written to /workspace/out/<name>.<ext>, surfaced to the conversation as an artifact.
  token_budget: 2000
---

# Document Generation

One skill, six formats. You pick the format via the `format` parameter; the
runtime routes to the right handler and stages that format's supplements into
the sandbox. You author the document by writing Python that runs through the
`code_execution` tool — the file lands in the workspace and is surfaced to the
user. New formats are added by the platform (a handler module), never by you
improvising an unsupported one.

## Shared conventions (every format)

- **Install the library first.** The sandbox does NOT preinstall every format's
  library — `reportlab` (pdf) and `python-pptx` (pptx) are absent by default and
  importing them raises `ModuleNotFoundError`. Begin your generated code with an
  idempotent install of the exact pinned library for your `format` BEFORE any
  import, then import. `md`/`txt` need no library. The runtime grants a longer
  time budget to a turn that installs (it detects the `pip install` line), so
  this does not cost you the exec cap.

  ```python
  import importlib.util, subprocess, sys
  # pin per format: pdf→"reportlab==4.2.5", pptx→"python-pptx==1.0.2",
  # docx→"python-docx==1.1.2", xlsx→"openpyxl==3.1.5" (docx/xlsx are usually
  # preinstalled, but installing is a safe no-op when already present).
  for _pkg, _mod in [("reportlab==4.2.5", "reportlab")]:  # ← swap for your format
      if importlib.util.find_spec(_mod) is None:
          subprocess.run([sys.executable, "-m", "pip", "install", "-q", _pkg], check=True)
  ```
- **Output path.** Write to `/workspace/out/<descriptive-name><ext>` from
  inside the sandbox — lowercase, hyphenated filename. The runtime surfaces the
  produced file. Same-session persistence only; do not promise cross-session
  re-open.
- **Visual style.** If `persona.identity.visual_style` is set, prefer those
  aesthetic hints (palette, font, register) over generic defaults.
- **Compose, don't round-trip.** For prose-then-format, the bridge is your own
  context — embed drafted prose as a Python **string**. Do NOT write a `.md`
  file and read it back.
- **Summarise in place.** When the user wants a condensed brief, do the
  condensing as you build `content_spec` (lead with the finding, cut to the
  essentials) — there is no separate summarise skill; this is the folded
  capability (D-24-7).
- **Depth on demand.** The section below is the must-do path. Read a supplement
  **from inside your generated code** only when the task needs the depth:
  `Path("/workspace/in/.skills/document_generation/supplements/<format>-<topic>.md").read_text()`.
- **Templates.** If a `template` is given, its Markdown is staged at
  `/workspace/in/.skills/document_generation/templates/<template>.md` — read it
  and follow its structure, filling `{{placeholders}}` from `content_spec`.

## Formats

### `docx` — Word (`python-docx==1.1.2`)

Named styles, not ad-hoc bold. Set `Normal` font + size before content; apply
`Heading 1/2/3` as named styles; page numbers in the footer; a TOC field shell
for ≥4 headings (tell the user to press F9). Supplements: `docx-tables`,
`docx-styles`, `docx-images`, `docx-toc`.

```python
from docx import Document
from docx.shared import Pt
doc = Document()
doc.styles["Normal"].font.name = "Calibri"; doc.styles["Normal"].font.size = Pt(11)
doc.add_heading("Title", level=0); doc.add_heading("Section", level=1)
doc.add_paragraph("Lead sentence.")
doc.save("/workspace/out/example.docx")
```

### `pdf` — report (`reportlab==4.2.5`)

Flowable model: build a `story` list (`Paragraph`/`Spacer`/`LongTable`/`Image`/
`PageBreak`); body font ≥10pt explicit; `LongTable(repeatRows=1)` for tables
that span pages; page numbers via `onLaterPages`. Supplements: `pdf-flowables`,
`pdf-pagination`, `pdf-images`.

```python
import importlib.util, subprocess, sys
if importlib.util.find_spec("reportlab") is None:  # not preinstalled — install first
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "reportlab==4.2.5"], check=True)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph
s = getSampleStyleSheet()
doc = SimpleDocTemplate("/workspace/out/report.pdf", pagesize=A4, title="Report")
doc.build([Paragraph("Title", s["Heading1"]), Paragraph("Body.", s["Normal"])])
```

### `pptx` — slides (`python-pptx==1.0.2`)

Use slide layouts, not free-floating text boxes; one idea per slide; readable
font sizes. Supplements: `pptx-layouts`, `pptx-charts`, `pptx-theme`.

```python
import importlib.util, subprocess, sys
if importlib.util.find_spec("pptx") is None:  # not preinstalled — install first
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "python-pptx==1.0.2"], check=True)
from pptx import Presentation
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Title"; slide.placeholders[1].text = "Subtitle"
prs.save("/workspace/out/deck.pptx")
```

### `xlsx` — workbook (`openpyxl==3.1.5`)

Header row + typed cells; column widths; formulas as strings (`"=SUM(B2:B9)"`);
number formats for currency/percent. Supplements: `xlsx-formulas`,
`xlsx-formatting`, `xlsx-charts`.

```python
from openpyxl import Workbook
wb = Workbook(); ws = wb.active; ws.append(["Item", "Qty"]); ws.append(["A", 3])
ws["B4"] = "=SUM(B2:B3)"
wb.save("/workspace/out/sheet.xlsx")
```

### `md` — Markdown (stdlib)

Plain text with Markdown structure. No library — write the string to disk.

```python
from pathlib import Path
Path("/workspace/out/notes.md").write_text("# Title\n\nLead paragraph.\n")
```

### `txt` — plain text (stdlib)

Same, without Markdown syntax. Wrap to a sane width; no markup.

```python
from pathlib import Path
Path("/workspace/out/notes.txt").write_text("Title\n\nLead paragraph.\n")
```

## After the run

When `code_execution` returns successfully, tell the user: the filename you
wrote, anything to refresh on open (e.g. a Word TOC needs F9), and any
limitation you hit. A partial PASS is honest; a silent PASS on a broken file is
not.

## If `code_execution` raises

A Python traceback comes back as a tool error. Read it, fix the code, run again
— the loop's tool-error recovery handles the round-trip. Do not catch the error
inside your generated code. Typical fixes live in the format's supplements.
