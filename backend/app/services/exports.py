"""Turning a table into a file someone can open.

One shape in — a title, column headings and rows — and three ways out: CSV for
anything, an Excel workbook for working on, and a PDF for sending or filing.
Every report in the system hands over the same shape, so a new report gets all
three formats for free.
"""
import csv
import io
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LUSAKA = timezone(timedelta(hours=2))
GREEN = colors.HexColor("#0b3b1d")
LIGHT = colors.HexColor("#ecf6e8")


def _stamp() -> str:
    return datetime.now(LUSAKA).strftime("%d %b %Y, %H:%M")


def to_csv(headings: list[str], rows: list[list], title: str = "") -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    if title:
        writer.writerow([title])
        writer.writerow([f"The Green Buffet, printed {_stamp()}"])
        writer.writerow([])
    writer.writerow(headings)
    writer.writerows(rows)
    # Excel on Windows opens UTF-8 correctly only with the byte order mark.
    return out.getvalue().encode("utf-8-sig")


def to_xlsx(headings: list[str], rows: list[list], title: str = "Report") -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title[:31] or "Report"

    sheet.append([title])
    sheet["A1"].font = Font(size=14, bold=True)
    sheet.append([f"The Green Buffet, printed {_stamp()}"])
    sheet["A2"].font = Font(size=9, color="5D665E")
    sheet.append([])

    sheet.append(headings)
    head_row = sheet.max_row
    for column in range(1, len(headings) + 1):
        cell = sheet.cell(row=head_row, column=column)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="ECF6E8")
        cell.alignment = Alignment(vertical="center")

    for row in rows:
        sheet.append(row)

    # Money columns are numbers, so the person can total them themselves.
    for column in range(1, len(headings) + 1):
        widest = max(
            [len(str(headings[column - 1]))]
            + [len(str(row[column - 1])) for row in rows if len(row) >= column]
            or [10]
        )
        sheet.column_dimensions[get_column_letter(column)].width = min(max(widest + 3, 11), 42)
    sheet.freeze_panes = sheet.cell(row=head_row + 1, column=1)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def to_pdf(headings: list[str], rows: list[list], title: str = "Report", note: str = "") -> bytes:
    buffer = io.BytesIO()
    wide = len(headings) > 5
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4) if wide else A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=title, author="The Green Buffet",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("gbTitle", parent=styles["Heading1"], fontSize=16, textColor=GREEN, spaceAfter=2)
    quiet = ParagraphStyle("gbQuiet", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#5d665e"))
    cell = ParagraphStyle("gbCell", parent=styles["Normal"], fontSize=8.5, leading=11)

    story = [
        Paragraph("The Green Buffet", heading),
        Paragraph(f"{title} · printed {_stamp()}", quiet),
    ]
    if note:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(note, quiet))
    story.append(Spacer(1, 6 * mm))

    data = [[Paragraph(f"<b>{h}</b>", cell) for h in headings]]
    for row in rows:
        data.append([Paragraph(str(value), cell) for value in row])

    table = Table(data, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9f5")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e1e5dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


MEDIA = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def render(fmt: str, headings: list[str], rows: list[list], title: str, note: str = "") -> tuple[bytes, str, str]:
    """Returns the file, its media type and a filename."""
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    stamp = datetime.now(LUSAKA).strftime("%Y%m%d")
    name = f"green-buffet-{slug}-{stamp}.{fmt}"
    if fmt == "csv":
        return to_csv(headings, rows, title), MEDIA["csv"], name
    if fmt == "xlsx":
        return to_xlsx(headings, rows, title), MEDIA["xlsx"], name
    return to_pdf(headings, rows, title, note), MEDIA["pdf"], name
