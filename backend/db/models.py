from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from db.database import Base


class InspectionLog(Base):
    __tablename__ = "inspections"

    id           = Column(Integer, primary_key=True, index=True)
    timestamp    = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc),
                          nullable=False)
    pass_fail    = Column(String, index=True, nullable=False)
    defects_json = Column(String, nullable=False, default="[]")
    frame_path   = Column(String, nullable=True)
