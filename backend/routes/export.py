"""
Export routes — CSV and PDF report generation.
Fixed bugs:
  - timestamp None guard
  - PDF now includes per-inspection defect breakdown
  - Uses /tmp for PDF (works on Linux + Railway)
"""
import csv
import io
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.database import get_db
from db.models   import InspectionLog

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib           import colors
    from reportlab.platypus      import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer)
    from reportlab.lib.styles    import getSampleStyleSheet
    from reportlab.lib.units     import inch
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

router = APIRouter(prefix="/export", tags=["export"])


def _fmt_ts(ts) -> str:
    """Format timestamp safely, handling None and naive datetimes."""
    if ts is None:
        return "N/A"
    try:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


# ── CSV ───────────────────────────────────────────────────────────────────────
@router.get("/csv")
def export_csv(db: Session = Depends(get_db)):
    logs = db.query(InspectionLog).order_by(InspectionLog.timestamp).all()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["ID", "Timestamp (UTC)", "Result", "Defect Count", "Defects"])

    for log in logs:
        try:
            defects   = json.loads(log.defects_json or "[]")
            defect_summary = "; ".join(
                f"{d.get('label') or d.get('class','?')} {d.get('confidence',0):.0%}"
                for d in defects
            )
        except Exception:
            defect_summary = log.defects_json or ""

        w.writerow([
            log.id,
            _fmt_ts(log.timestamp),
            log.pass_fail,
            len(json.loads(log.defects_json or "[]")),
            defect_summary,
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type = "text/csv",
        headers    = {"Content-Disposition": "attachment; filename=inspection_log.csv"},
    )


# ── PDF ───────────────────────────────────────────────────────────────────────
@router.get("/pdf")
def export_pdf(db: Session = Depends(get_db)):
    if not REPORTLAB_OK:
        return {"error": "reportlab not installed"}

    logs     = db.query(InspectionLog).order_by(InspectionLog.timestamp).all()
    total    = len(logs)
    passes   = sum(1 for l in logs if l.pass_fail == "Pass")
    fails    = total - passes
    yield_pct = f"{passes / total * 100:.1f}%" if total else "N/A"

    # Count defect classes
    class_counts: dict[str, int] = {}
    for log in logs:
        try:
            for d in json.loads(log.defects_json or "[]"):
                cls = d.get("label") or d.get("class") or "unknown"
                class_counts[cls] = class_counts.get(cls, 0) + 1
        except Exception:
            pass

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=letter,
                                leftMargin=0.75*inch, rightMargin=0.75*inch,
                                topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    story.append(Paragraph("Optical Lens Defect Detection Report", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 0.25*inch))

    # Summary table
    summary_data = [
        ["Metric", "Value"],
        ["Total Inspections", str(total)],
        ["Passed",            str(passes)],
        ["Failed",            str(fails)],
        ["Yield Rate",        yield_pct],
    ]
    for cls, cnt in class_counts.items():
        summary_data.append([f"  {cls} defects", str(cnt)])

    summary_table = Table(summary_data, colWidths=[3.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("PADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))

    # Inspection log table (last 100 records)
    story.append(Paragraph("Recent Inspections (latest 100)", styles["Heading2"]))
    story.append(Spacer(1, 0.1*inch))

    table_data = [["ID", "Timestamp (UTC)", "Result", "Defects"]]
    for log in logs[-100:]:
        try:
            defects = json.loads(log.defects_json or "[]")
            defect_str = ", ".join(
                d.get("label") or d.get("class", "?") for d in defects
            ) or "—"
        except Exception:
            defect_str = "?"

        result_str = log.pass_fail or "?"
        table_data.append([
            str(log.id),
            _fmt_ts(log.timestamp),
            result_str,
            defect_str,
        ])

    log_table = Table(table_data, colWidths=[0.5*inch, 2.2*inch, 0.8*inch, 3*inch])
    log_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("GRID",         (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("PADDING",      (0, 0), (-1, -1), 4),
        # Colour Pass/Fail cells
        *[("TEXTCOLOR", (2, i), (2, i),
           colors.HexColor("#16a34a") if row[2] == "Pass" else colors.HexColor("#dc2626"))
          for i, row in enumerate(table_data) if i > 0],
    ]))
    story.append(log_table)

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": "attachment; filename=inspection_report.pdf"},
    )
