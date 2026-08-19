from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str
    channel: Literal["chat", "voice"] = "chat"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    ended: bool = False


class EndRequest(BaseModel):
    session_id: str


class Analytics(BaseModel):
    session_id: str
    configuration_interest: Optional[str] = None  # "2 BHK" | "3 BHK" | "undecided" | None
    budget_signal: Optional[str] = None            # free text summary, never invented
    purpose: Optional[str] = None                  # "self-use" | "investment" | None
    timeline: Optional[str] = None
    interest_level: Literal["hot", "warm", "cold", "unknown"] = "unknown"
    language_used: Optional[str] = None             # "English" | "Hindi" | "Hinglish" | "mixed"
    site_visit_status: Literal["booked", "attempted_failed", "not_requested", "declined"] = "not_requested"
    site_visit_details: Optional[dict] = None
    follow_up_required: bool = False
    follow_up_notes: Optional[str] = None
    opted_out: bool = False
    escalated_to_human: bool = False
    escalation_reason: Optional[str] = None
    objections_raised: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    turn_count: int = 0
