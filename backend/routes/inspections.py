from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from db.models   import InspectionLog
from db.schemas  import InspectionResponse, StatsResponse
import json

router = APIRouter(prefix="/inspections", tags=["inspections"])


@router.get("/", response_model=list[InspectionResponse])
def get_inspections(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(InspectionLog)
        .order_by(InspectionLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    total      = db.query(InspectionLog).count()
    pass_count = db.query(InspectionLog).filter(InspectionLog.pass_fail == "Pass").count()
    fail_count = db.query(InspectionLog).filter(InspectionLog.pass_fail == "Fail").count()

    class_counts: dict[str, int] = {
        "bubble": 0, "crack": 0, "dots": 0, "scratch": 0
    }

    rows = (
        db.query(InspectionLog.defects_json)
        .filter(InspectionLog.pass_fail == "Fail")
        .all()
    )
    for (defects_json,) in rows:
        try:
            defects = json.loads(defects_json or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        for d in defects:
            # Accept both "label" (new) and "class" (legacy) keys
            cls = d.get("label") or d.get("class")
            if cls:
                class_counts[cls] = class_counts.get(cls, 0) + 1

    return StatsResponse(
        total         = total,
        pass_count    = pass_count,
        fail_count    = fail_count,
        defect_counts = class_counts,
    )
