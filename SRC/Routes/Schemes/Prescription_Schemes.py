from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class MedicineInfo(BaseModel):
    name: str
    active_ingredient: str
    dosage: Optional[str] = None
    form: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    candidates: Optional[List[Dict[str, Any]]] = []  # LLM specialty-aware suggestions


class PrescriptionResponse(BaseModel):
    signal: str
    doctor_specialty: Optional[str] = "Unknown"  # Detected from prescription header
    ocr_text: str
    medicines: List[MedicineInfo]

class ExtractResponse(BaseModel):
    doctor_specialty: str
    ocr_text: str
    medicines: List[MedicineInfo]
