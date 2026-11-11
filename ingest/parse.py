"""Parse annual-report PDFs with Docling into page-tagged text chunks and raw tables.

Usage:
    python -m ingest.parse                 # parse every PDF in data/raw not yet parsed
    python -m ingest.parse --only infosys_FY2025 --force
    python -m ingest.parse --only tcs_FY2025 --force --ocr   # PDF with a broken text layer

Writes one JSON file per report to data/processed/<company>_FY<year>.json:
    {"company", "fiscal_year", "source_file",
     "chunks": [{"page", "section", "text"}],
     "tables": [{"page", "section", "caption", "context", "rows": [[str, ...], ...]}]}

"context" is the text just before the table, which is often where the unit ("₹ in crore") is.

Page numbers are PDF page indices (1-based), not the printed page labels, so a citation
always opens the right page in a PDF viewer.
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings

COMPANIES = {"infosys", "tcs", "wipro", "hcltech", "techmahindra"}
FILENAME_RE = re.compile(r"^(?P<company>[a-z]+)_FY(?P<year>\d{4})$")
MAX_CHUNK_CHARS = 1500

# Docling labels that are body text worth indexing. Page headers/footers are noise.
TEXT_LABELS = {"text", "paragraph", "list_item", "caption", "footnote"}
HEADER_LABELS = {"section_header", "title"}


@dataclass
class Element:
    page: int
    section: str | None
    text: str


@dataclass
class ChunkOut:
    page: int
    section: str | None
    text: str


def parse_filename(path: Path) -> tuple[str, int]:
    """'infosys_FY2025.pdf' -> ('infosys', 2025). Raises ValueError on a bad name."""
    m = FILENAME_RE.match(path.stem)
    if not m or m["company"] not in COMPANIES:
        raise ValueError(
            f"{path.name}: expected <company>_FY<year>.pdf with company in {sorted(COMPANIES)}"
        )
    return m["company"], int(m["year"])


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph on sentence boundaries, hard-cutting as a last resort."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts, buf = [], ""
    for s in sentences:
        while len(s) > max_chars:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(s[:max_chars])
            s = s[max_chars:]
        if buf and len(buf) + 1 + len(s) > max_chars:
            parts.append(buf)
            buf = s
        else:
            buf = f"{buf} {s}".strip()
    if buf:
        parts.append(buf)
    return parts


def chunk_elements(elements: list[Element], max_chars: int = MAX_CHUNK_CHARS) -> list[ChunkOut]:
    """Merge consecutive elements into chunks of at most max_chars.

    A chunk never spans two pages or two sections, so every chunk has exactly one
    page to cite.
    """
    chunks: list[ChunkOut] = []
    cur: ChunkOut | None = None
    for el in elements:
        text = el.text.strip()
        if not text:
            continue
        for piece in _split_long(text, max_chars) if len(text) > max_chars else [text]:
            same_place = cur and cur.page == el.page and cur.section == el.section
            if same_place and len(cur.text) + 1 + len(piece) <= max_chars:
                cur.text += "\n" + piece
            else:
                cur = ChunkOut(el.page, el.section, piece)
                chunks.append(cur)
    return chunks


def table_to_rows(df) -> list[list[str]]:
    """DataFrame -> list of string rows, header first."""
    header = [str(c) for c in df.columns]
    body = [["" if v is None else str(v) for v in row] for row in df.itertuples(index=False)]
    return [header, *body]


def _converter(ocr: bool = False):
    # Imported here so the rest of this module (and the tests) don't need Docling.
    import torch
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Annual reports are digital PDFs, so OCR is off by default (much faster). Some PDFs have
    # a broken text layer (e.g. TCS FY2025: "Marc h 31"); --ocr reads every page from the image.
    # AUTO uses the GPU when a CUDA build of torch is installed, otherwise the CPU.
    opts = PdfPipelineOptions(
        do_ocr=ocr,
        do_table_structure=True,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.AUTO),
    )
    if ocr:
        opts.ocr_options = RapidOcrOptions(mode=OcrMode.FULL_PAGE, lang=["en"], backend="torch")
    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"device: {device}, ocr: {ocr}")
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def parse_pdf(path: Path, converter) -> dict:
    company, year = parse_filename(path)
    doc = converter.convert(path).document

    elements: list[Element] = []
    tables: list[dict] = []
    section: str | None = None
    last_text: str | None = None

    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower().split(".")[-1]
        prov = getattr(item, "prov", None)
        if not prov:
            continue
        page = prov[0].page_no

        if label == "table":
            try:
                df = item.export_to_dataframe(doc=doc)
            except TypeError:  # older Docling versions take no doc argument
                df = item.export_to_dataframe()
            if df.empty:
                continue
            tables.append(
                {
                    "page": page,
                    "section": section,
                    "caption": item.caption_text(doc) or None,
                    "context": last_text,
                    "rows": table_to_rows(df),
                }
            )
        elif label in HEADER_LABELS:
            section = item.text.strip() or section
            elements.append(Element(page, section, item.text))
        elif label in TEXT_LABELS:
            elements.append(Element(page, section, item.text))
            last_text = item.text

    return {
        "company": company,
        "fiscal_year": year,
        "source_file": path.name,
        "chunks": [asdict(c) for c in chunk_elements(elements)],
        "tables": tables,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", help="parse just this report, e.g. infosys_FY2025")
    ap.add_argument("--force", action="store_true", help="re-parse even if output exists")
    ap.add_argument("--ocr", action="store_true", help="OCR every page (broken text layers)")
    args = ap.parse_args()

    s = get_settings()
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(s.raw_dir.glob("*.pdf"))
    if args.only:
        pdfs = [p for p in pdfs if p.stem == args.only]
    if not pdfs:
        raise SystemExit(f"No matching PDFs in {s.raw_dir}")

    converter = None
    for pdf in pdfs:
        parse_filename(pdf)  # fail fast on a badly named file
        out = s.processed_dir / f"{pdf.stem}.json"
        if out.exists() and not args.force:
            print(f"skip {pdf.name} (already parsed)")
            continue
        converter = converter or _converter(ocr=args.ocr)
        print(f"parsing {pdf.name} ...", flush=True)
        result = parse_pdf(pdf, converter)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {len(result['chunks'])} chunks, {len(result['tables'])} tables -> {out.name}")


if __name__ == "__main__":
    main()
