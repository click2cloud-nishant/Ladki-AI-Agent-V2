from pydantic import BaseModel
from typing import Optional

# Pydantic models for request/response
class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


class ChatResponse(BaseModel):
    response: str
    session_id: str

class ClearHistoryRequest(BaseModel):
    session_id: Optional[str] = "default"

class ClearHistoryResponse(BaseModel):
    message: str
    status: str

class SchemeInfoResponse(BaseModel):
    scheme_name: str
    state: str
    monthly_assistance: str
    age_eligibility: str
    income_limit: str
    official_website: str
    status: str