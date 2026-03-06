from pydantic import BaseModel
from typing import Optional, List


class MedicineInfo(BaseModel):
    name: str
    active_ingredient: str
    dosage: Optional[str] = None
    form: Optional[str] = None
    image_url: Optional[str] = None


class PrescriptionResponse(BaseModel):
    signal: str
    ocr_text: str
    medicines: List[MedicineInfo]
