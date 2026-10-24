"""Turn a Markdown brief into a readable PDF report.

Usage: python make_pdf.py <brief.md> <out.pdf> [--title "Report title"]
Headings, paragraphs, bullet lists, bold/italic and links are kept. Uses the bundled
DejaVu fonts so dashes, curly quotes and bullets render correctly.
"""

import argparse
import re
import sys
from pathlib import Path

import markdown
from fpdf import FPDF

FONTS = Path(__file__).parent / "fonts"


class Report(FPDF):
    def __init__(self, title: str):
        super().__init__()
        self.report_title = title
        self.add_font("DejaVu", "", FONTS / "DejaVuSans.ttf")
        self.add_font("DejaVu", "B", FONTS / "DejaVuSans-Bold.ttf")
        self.add_font("DejaVu", "I", FONTS / "DejaVuSans.ttf")  # no italic face bundled: render upright
        self.add_font("DejaVu", "BI", FONTS / "DejaVuSans-Bold.ttf")
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(29, 53, 87)
        self.cell(0, 8, "DUNDER MIFFLIN PAPER COMPANY · SCRANTON", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(29, 53, 87)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-14)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"{self.report_title} · page {self.page_no()}", align="C")


def to_html(md_text: str) -> str:
    html = markdown.markdown(md_text)
    # write_html would switch <code>/<pre> to a core font that can't draw Unicode; keep our font.
    return re.sub(r"</?(code|pre)>", "", html)


def build(md_text: str, out_path: Path, title: str) -> None:
    pdf = Report(title)
    pdf.add_page()
    pdf.set_font("DejaVu", size=11)
    pdf.write_html(to_html(md_text), font_family="DejaVu")
    pdf.output(str(out_path))


def first_heading(md_text: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--title")
    args = parser.parse_args(argv[1:])
    source = Path(args.source)
    if not source.is_file():
        print(f"error: {source} not found", file=sys.stderr)
        return 2
    md_text = source.read_text()
    build(md_text, Path(args.out), args.title or first_heading(md_text) or "Report")
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
