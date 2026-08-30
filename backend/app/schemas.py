from datetime import date
from pydantic import BaseModel, Field, model_validator


class PreviewSearchRequest(BaseModel):
    date_from: date
    date_to: date
    subject_text: str | None = "dano moral"
    limit: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from deve ser anterior ou igual a date_to")
        return self


class PreviewSearchResponse(BaseModel):
    total: int | None
    items: list[dict]

class CollectSearchRequest(BaseModel):
    date_from: date
    date_to: date
    subject_text: str | None = "dano moral"

    batch_size: int = Field(
        default=500,
        ge=1,
        le=1000,
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from > self.date_to:
            raise ValueError(
                "date_from deve ser anterior ou igual a date_to"
            )

        return self


class CollectSearchResponse(BaseModel):
    search_run_id: int
    status: str
    total_found: int
    saved_new: int
    updated: int
    pages: int