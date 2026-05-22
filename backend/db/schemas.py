"""
Pydantic schemas for API responses.
"""
from pydantic import BaseModel, field_validator, computed_field
from datetime import datetime
from typing import Optional
import json


class InspectionResponse(BaseModel):
    id:           int
    timestamp:    datetime
    pass_fail:    str
    defects_json: str
    frame_path:   Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("defects_json")
    @classmethod
    def validate_json(cls, v):
        try:
            json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return "[]"
        return v

    @computed_field
    @property
    def defect_count(self) -> int:
        """Convenience field so frontend doesn't have to parse defects_json just for a count."""
        try:
            return len(json.loads(self.defects_json))
        except Exception:
            return 0


class StatsResponse(BaseModel):
    total:         int
    pass_count:    int
    fail_count:    int
    defect_counts: dict[str, int]