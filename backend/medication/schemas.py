from pydantic import BaseModel, Field


class MedicationRecognitionResponse(BaseModel):
    status: str
    recognized_med: str
    confidence: str
    is_match: bool | None = None
    message: str
    agent_decision: str | None = None


class MedicationScheduleInput(BaseModel):
    time_of_day: str
    days_of_week: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])


class CreateMedicationModel(BaseModel):
    elder_id: str
    name: str
    dosage: str | None = None
    form: str | None = None
    notes: str | None = None
    schedules: list[MedicationScheduleInput] = Field(default_factory=list)


class UpdateMedicationModel(BaseModel):
    name: str | None = None
    dosage: str | None = None
    form: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class SyncElderModel(BaseModel):
    user_id: str
    user_name: str
