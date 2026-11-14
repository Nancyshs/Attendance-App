"""Excel exports and Excel/CSV imports."""
from __future__ import annotations

import csv
import io
from datetime import datetime, time
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..core.timeutil import to_local

HEADER_FILL = PatternFill("solid", fgColor="00332A")
HEADER_FONT = Font(bold=True, color="FFFFFF")
STATUS_FILLS = {
    "present": "DCFCE7",
    "late": "FEF3C7",
    "absent": "FEE2E2",
    "excused": "E9EED9",
}


def _style_header(ws, row: int = 1) -> None:
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws, minimum: int = 10, maximum: int = 48) -> None:
    for col in ws.columns:
        width = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(minimum, min(maximum, width + 2))


def _hhmm(iso: str | None) -> str:
    if not iso:
        return ""
    return to_local(datetime.fromisoformat(iso.replace("Z", "+00:00"))).strftime("%H:%M")


STATUS_EN = {
    "present": "Present", "late": "Late", "absent": "Absent", "excused": "Excused",
    "not_arrived": "Not arrived", "upcoming": "Upcoming", "no_training": "No training",
}

STATUS_AR = {
    "present": "حاضر", "late": "متأخر", "absent": "غائب", "excused": "بعذر",
    "not_arrived": "لم يصل", "upcoming": "قادم", "no_training": "لا يوجد تدريب",
}

# Arabic column titles accepted when importing (mapped to the canonical keys the importers use)
HEADER_ALIASES = {
    "الاسم": "full_name", "اسم_المتدرب": "full_name", "الاسم_بالكامل": "full_name",
    "البريد_الإلكتروني": "email", "البريد": "email", "الإيميل": "email",
    "الهاتف": "phone", "الموبايل": "phone", "رقم_الهاتف": "phone", "التليفون": "phone", "رقم_التليفون": "phone",
    "المحافظة": "governorate", "محافظة": "governorate",
    "الجهة": "organization", "جهه": "organization",
    "رقم_البطاقة": "national_id", "البطاقة": "national_id", "الرقم_القومي": "national_id",
    "الوظيفة": "job_title", "وظيفه": "job_title", "المسمى_الوظيفي": "job_title",
    "المجموعة": "group_name", "رقم_الباج": "badge_id", "الباج": "badge_id", "الكود": "badge_id",
    "التاريخ": "date", "من": "start", "وقت_البدء": "start", "البداية": "start",
    "إلى": "end", "الى": "end", "وقت_الانتهاء": "end", "النهاية": "end",
    "العنوان": "title", "عنوان_المحاضرة": "title", "المحاضرة": "title",
    "المحاضر": "trainer", "القاعة": "room",
    "group": "group_name",
}


def workbook_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def attendance_workbook(report: dict[str, Any], lang: str = "ar") -> bytes:
    P = lambda en, ar: ar if lang == "ar" else en  # noqa: E731
    wb = Workbook()
    ws = wb.active
    ws.title = P("Summary", "الملخص")
    ws.append(
        [P("Badge", "الباج"), P("Name", "الاسم"), P("Group", "المجموعة"), P("Present", "حاضر"), P("Late", "متأخر"), P("Absent", "غائب"), P("Excused", "بعذر"), P("Early leave", "انصراف مبكر"), P("Missing check-out", "بدون انصراف"),
         P("Attendance %", "نسبة الحضور %"), P("Avg hours/day", "متوسط الساعات/يوم")]
    )
    _style_header(ws)
    for item in report["trainees"]:
        t, s = item["trainee"], item["summary"]
        ws.append(
            [t["badge_id"], t["full_name"], t["group_name"] or "", s["present"], s["late"], s["absent"], s["excused"],
             s["early_leave"], s["incomplete"], s["attendance_pct"], s["avg_hours"]]
        )
    ws.freeze_panes = "C2"
    _autosize(ws)

    detail = wb.create_sheet(P("Daily detail", "التفاصيل اليومية"))
    detail.append([P("Date", "التاريخ"), P("Badge", "الباج"), P("Name", "الاسم"), P("Status", "الحالة"), P("Check-in", "الحضور"), P("Check-out", "الانصراف"), P("Hours", "الساعات"), P("Early leave", "انصراف مبكر"), P("Manual", "يدوي"), P("Note", "ملاحظة")])
    _style_header(detail)
    for item in report["trainees"]:
        t = item["trainee"]
        for cell in item["cells"]:
            if cell["status"] in ("upcoming",):
                continue
            hours = round(cell["worked_minutes"] / 60, 2) if cell["worked_minutes"] is not None else ""
            detail.append(
                [cell["date"], t["badge_id"], t["full_name"], (STATUS_AR if lang == "ar" else STATUS_EN).get(cell["status"], cell["status"]),
                 _hhmm(cell["check_in_at"]), _hhmm(cell["check_out_at"]), hours,
                 P("Yes", "نعم") if cell["early_leave"] else "", P("Yes", "نعم") if cell["is_manual"] else "", cell["note"] or ""]
            )
            fill = STATUS_FILLS.get(cell["status"])
            if fill:
                detail.cell(row=detail.max_row, column=4).fill = PatternFill("solid", fgColor=fill)
    detail.freeze_panes = "A2"
    detail.auto_filter.ref = detail.dimensions
    _autosize(detail)

    grid = wb.create_sheet(P("Grid", "الجدول"))
    grid.append([P("Badge", "الباج"), P("Name", "الاسم")] + [d["date"] for d in report["days"]])
    _style_header(grid)
    letters = (
        {"present": "ح", "late": "ت", "absent": "غ", "excused": "ع", "not_arrived": "-", "upcoming": ""}
        if lang == "ar"
        else {"present": "P", "late": "L", "absent": "A", "excused": "E", "not_arrived": "-", "upcoming": ""}
    )
    for item in report["trainees"]:
        t = item["trainee"]
        grid.append([t["badge_id"], t["full_name"]] + [letters.get(c["status"], "") for c in item["cells"]])
        for i, c in enumerate(item["cells"], start=3):
            fill = STATUS_FILLS.get(c["status"])
            if fill:
                grid.cell(row=grid.max_row, column=i).fill = PatternFill("solid", fgColor=fill)
            grid.cell(row=grid.max_row, column=i).alignment = Alignment(horizontal="center")
    grid.freeze_panes = "C2"
    _autosize(grid, maximum=30)
    return workbook_bytes(wb)


def _percent_label(value: float) -> str:
    number = round(float(value), 1)
    if number == int(number):
        return f"{int(number)}%"
    return f"{number}%"


def _percent_style(avg: float | None) -> tuple[PatternFill, Font]:
    if avg is None:
        return PatternFill("solid", fgColor="F1F5F9"), Font(bold=True, color="64748B")
    if avg >= 4.2:
        return PatternFill("solid", fgColor="D1FAE5"), Font(bold=True, color="065F46")
    if avg >= 3.5:
        return PatternFill("solid", fgColor="FEF3C7"), Font(bold=True, color="92400E")
    return PatternFill("solid", fgColor="FEE2E2"), Font(bold=True, color="991B1B")


def survey_workbook(report: dict[str, Any], lang: str = "ar") -> bytes:
    """One sheet laid out like the feedback page: each lecture, then its questions and percentages."""
    P = lambda en, ar: ar if lang == "ar" else en  # noqa: E731
    wb = Workbook()
    ws = wb.active
    ws.title = P("Feedback", "التقييمات")
    ws.append([
        P("Session", "المحاضرة"),
        P("Date", "التاريخ"),
        P("Trainer", "المدرب"),
        P("Session percentage", "نسبة الجلسة"),
        P("Question", "السؤال"),
        P("Question percentage", "نسبة السؤال"),
        P("Answers", "الإجابات"),
    ])
    _style_header(ws)
    ws.row_dimensions[1].height = 28
    hairline = Side(style="thin", color="E2E8F0")
    lecture_line = Side(style="medium", color="D5E0D2")
    zebra = PatternFill("solid", fgColor="F3F8F6")
    plain = PatternFill("solid", fgColor="FFFFFF")

    for index, session in enumerate(report["sessions"]):
        questions = session["questions"] or [None]
        start = ws.max_row + 1
        fill = zebra if index % 2 else plain
        when = f"{session['day']}\n{session['start_time']}–{session['end_time']}"
        session_percent = _percent_label(session["percent"]) if session.get("percent") is not None else "—"
        for question in questions:
            if question is None:
                text, percent, count = "—", "—", session["responses"]
            elif question.get("type") == "choice" and question.get("choices"):
                total = max(1, int(question["count"] or 0))
                text = question["text"]
                count = question["count"]
                percent = "\n".join(
                    f"{label}  {round(int(n) / total * 100)}%" for label, n in question["choices"].items()
                )
            else:
                text = question["text"]
                count = question["count"]
                percent = _percent_label(question["percent"]) if question.get("percent") is not None else "—"
            ws.append([session["title"], when, session["trainer_name"] or "—", session_percent, text, percent, count])
            row_no = ws.max_row
            last = question is questions[-1]
            for col in range(1, 8):
                cell = ws.cell(row_no, col)
                cell.fill = fill
                cell.border = Border(bottom=lecture_line if last else hairline)
                cell.alignment = Alignment(
                    horizontal="center" if col in (4, 6, 7) else "right",
                    vertical="center",
                    wrap_text=True,
                )
            if question is not None and question.get("type") != "choice":
                tone, font = _percent_style(question.get("avg"))
                percent_cell = ws.cell(row_no, 6)
                percent_cell.fill = tone
                percent_cell.font = font
            lines = len((question or {}).get("choices") or []) if question and question.get("type") == "choice" else 1
            ws.row_dimensions[row_no].height = max(22, 16 * lines)
        end = ws.max_row
        if end > start:
            for col in (1, 2, 3, 4):
                ws.merge_cells(start_row=start, start_column=col, end_row=end, end_column=col)
        tone, font = _percent_style(session.get("avg_rating"))
        session_cell = ws.cell(start, 4)
        session_cell.fill = tone
        session_cell.font = font

    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = lang == "ar"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"
    ws.page_setup.horizontalCentered = True
    ws.sheet_view.showGridLines = False
    for letter, width in {"A": 28, "B": 16, "C": 20, "D": 16, "E": 46, "F": 16, "G": 12}.items():
        ws.column_dimensions[letter].width = width
    return workbook_bytes(wb)


def template_workbook(headers: list[str], example: list[list[Any]], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    _style_header(ws)
    for row in example:
        ws.append(row)
    _autosize(ws, minimum=14)
    return workbook_bytes(wb)


# ------------------------------------------------------------------------ importing
def read_table(filename: str, data: bytes) -> list[dict[str, Any]]:
    """Reads .xlsx or .csv into a list of dicts keyed by lower-cased, underscored headers."""
    rows: list[list[Any]]
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        rows = [list(r) for r in csv.reader(io.StringIO(text))]
    else:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    if not rows:
        return []
    headers = [str(h or "").strip().lower().replace(" ", "_") for h in rows[0]]
    headers = [HEADER_ALIASES.get(h, h) for h in headers]
    out: list[dict[str, Any]] = []
    for line_no, r in enumerate(rows[1:], start=2):
        if not any(v not in (None, "") for v in r):
            continue
        item = {headers[i]: r[i] for i in range(min(len(headers), len(r))) if headers[i]}
        item["_row"] = line_no
        out.append(item)
    return out


def _mark(value: bool | None) -> str:
    if value is None:
        return ""
    return "صح" if value else "خطأ"


_TRUE_FILL = PatternFill("solid", fgColor="D1FAE5")
_TRUE_FONT = Font(bold=True, color="065F46")
_FALSE_FILL = PatternFill("solid", fgColor="FEE2E2")
_FALSE_FONT = Font(bold=True, color="991B1B")
_DIFF_FILL = PatternFill("solid", fgColor="FEF3C7")
_DIFF_FONT = Font(bold=True, color="92400E")
_SAME_FILL = PatternFill("solid", fgColor="D1FAE5")
_SAME_FONT = Font(bold=True, color="065F46")
_TITLE_FILL = PatternFill("solid", fgColor="E7F3EF")
_TITLE_FONT = Font(bold=True, color="00332A", size=14)
_ZEBRA = PatternFill("solid", fgColor="F8FAF9")
_AMBER_SIDE = Side(style="medium", color="D97706")


def _finish_exam_sheet(ws) -> None:
    last_col = ws.max_column
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    title = ws.cell(1, 1)
    title.fill = _TITLE_FILL
    title.font = _TITLE_FONT
    title.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 32
    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:{get_column_letter(last_col)}{ws.max_row}"
    ws.sheet_view.rightToLeft = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:2"
    ws.page_setup.horizontalCentered = True
    ws.sheet_view.showGridLines = False
    for row_no, row in enumerate(ws.iter_rows(min_row=3), start=3):
        ws.row_dimensions[row_no].height = 22
        for cell in row:
            center = Alignment(horizontal="center", vertical="center")
            if cell.column <= 2:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                if row_no % 2 == 0:
                    cell.fill = _ZEBRA
            elif cell.value == "صح":
                cell.fill = _TRUE_FILL
                cell.font = _TRUE_FONT
                cell.alignment = center
            elif cell.value == "خطأ":
                cell.fill = _FALSE_FILL
                cell.font = _FALSE_FONT
                cell.alignment = center
            else:
                cell.alignment = center
    _autosize(ws, maximum=36)


def exam_workbook(report: dict[str, Any], part: str) -> bytes:
    """One workbook for a single report: before the lecture, after it, or the comparison."""
    wb = Workbook()
    ws = wb.active
    questions: list[str] = report["questions"]
    if part == "compare":
        ws.title = "المقارنة"
        ws.append([f"{report['title']}  ·  {report['day']}"])
        pairs = [item for i in range(len(questions)) for item in (f"س{i + 1} قبل", f"س{i + 1} بعد")]
        ws.append(["الكود", "الاسم", *pairs, "عدد الاختلافات"])
        _style_header(ws, 2)
        for row in report["rows"]:
            before = row["before"]["answers"] if row["before"] else [None] * len(questions)
            after = row["after"]["answers"] if row["after"] else [None] * len(questions)
            cells: list[str] = []
            different = 0
            comparable = False
            changed_pairs: list[bool] = []
            for left, right in zip(before, after):
                cells.extend([_mark(left), _mark(right)])
                changed = left is not None and right is not None and left != right
                changed_pairs.append(changed)
                if left is not None and right is not None:
                    comparable = True
                    if changed:
                        different += 1
            ws.append([row["badge_id"], row["full_name"], *cells, different if comparable else ""])
            excel_row = ws.max_row
            for index, changed in enumerate(changed_pairs):
                if not changed:
                    continue
                for offset in (0, 1):
                    cell = ws.cell(excel_row, 3 + index * 2 + offset)
                    cell.border = Border(bottom=_AMBER_SIDE, top=_AMBER_SIDE)
            count = ws.cell(excel_row, 3 + len(questions) * 2)
            if comparable:
                count.fill = _DIFF_FILL if different else _SAME_FILL
                count.font = _DIFF_FONT if different else _SAME_FONT
        _finish_exam_sheet(ws)
        return workbook_bytes(wb)

    phase = "after" if part == "after" else "before"
    ws.title = "بعد المحاضرة" if phase == "after" else "قبل المحاضرة"
    ws.append([f"{report['title']}  ·  {report['day']}"])
    ws.append(["الكود", "الاسم", *[f"س{i + 1}: {text}" for i, text in enumerate(questions)]])
    _style_header(ws, 2)
    for row in report["rows"]:
        sitting = row[phase]
        answers = sitting["answers"] if sitting else [None] * len(questions)
        ws.append([row["badge_id"], row["full_name"], *[_mark(v) for v in answers]])
    _finish_exam_sheet(ws)
    return workbook_bytes(wb)


def cell_time(value: Any) -> str | None:
    """Normalises Excel time cells / strings to HH:MM."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if text.count(":") >= 1:
        hh, mm = text.split(":")[:2]
        return f"{int(hh):02d}:{int(mm[:2]):02d}"
    return None
