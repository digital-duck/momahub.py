"""Convert markdown text to a PDF file using fpdf2."""
from __future__ import annotations

from pathlib import Path


def markdown_to_pdf(md_text: str, output_path: str, title: str = "") -> Path:
    """Write *md_text* (simple markdown) to a PDF at *output_path*."""
    from fpdf import FPDF  # type: ignore

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    if title:
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    in_code_block = False

    def _write_block(text: str, h: float = 6) -> None:
        pdf.set_x(pdf.l_margin)
        w = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.multi_cell(w, h, text)

    for line in md_text.split("\n"):
        stripped = line.strip()

        # Fenced code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            pdf.set_font("Courier", size=9)
            _write_block(line, 5)
            pdf.set_font("Helvetica", size=11)
            continue

        if not stripped:
            pdf.ln(4)
            continue

        # Headings
        if stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 8, stripped[4:], new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(0, 10, stripped[3:], new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 17)
            pdf.cell(0, 12, stripped[2:], new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            _write_block(f"    - {stripped[2:]}")
        else:
            _write_block(stripped)

    out = Path(output_path)
    pdf.output(str(out))
    return out
