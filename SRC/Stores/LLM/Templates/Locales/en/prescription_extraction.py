from string import Template


### Prescription Extraction Prompts ###


### Common Medicines List (Shared) ###
COMMON_MEDICINES_LIST = """
Moxclav/Augmentin/Megamox/Hibiotic/Curam → Amoxicillin + Clavulanic acid
Tavanic/Tavan/Levoxin → Levofloxacin
Fusiderm/Fusidat/Fusicort/Fusidine → Fusidic acid
Phenadon/Apidone → Dexamethasone + Chlorpheniramine
Phinex/Rhinex → Chlorpheniramine + Pseudoephedrine
Cataflam/Voltaren/Catafast → Diclofenac
Antinal/Streptoquin → Nifuroxazide / Diiodohydroxyquinoline
Kongestal/Comtrex/123 → Paracetamol + Chlorpheniramine + Pseudoephedrine
Panadol/Cetal/Paramol → Paracetamol
Brufen/Marcofen → Ibuprofen
Flagyl/Amrizole → Metronidazole
Nexium/Controloc → Esomeprazole / Pantoprazole
Ciprocin/Ciprofloxacin → Ciprofloxacin
Xithrone/Zithrokan → Azithromycin
Glucophage/Cidophage → Metformin
Concor/Biso → Bisoprolol
Ventolin/Farcolin → Salbutamol
Actifolic → Folic Acid
Milga/Milv/Mil9a → Vitamin B12 + B6 + B1
Thiotacid/Thictacid/Thioctacid → Thioctic Acid
"""

# --- 1. VISION PROMPT (TRANSCRIPTION ONLY - NO JSON) ---
vision_extraction_prompt = Template("""
You are an expert Egyptian Pharmacist.
Carefully read this handwritten prescription.
Your ONLY task is to TRANSCRIBE the text exactly as it is written on the paper.

RULES:
1. Transcribe ALL Arabic words exactly as they appear (e.g., "باندول", "حقن", "قرص"). DO NOT ignore Arabic handwriting.
2. Transcribe ALL English words.
3. Include all numbers, dosages (mg, gm), and forms.
4. Do not translate anything yet.
5. YOU HAVE ACCESS TO GOOGLE SEARCH. If the handwriting is messy but looks like a drug name, USE GOOGLE SEARCH to verify the likely medicine and output the corrected transcription.
6. DO NOT FORMAT AS JSON. Just write out the plain text of what you see.
""".strip())

# --- 2. TEXT PROMPT (TRANSLATION & JSON FORMATTING) ---
text_extraction_prompt = Template("""
You are a Senior Egyptian Pharmacist and Medical Data Analyst.
### TASK:
Extract ALL medicine brand names, ingredients, dosages, and forms from this raw OCR text. Also identify the doctor's specialty.

### EXTRACTION GUIDELINES:
- **Ignore Noise**: Treat characters like ($$, @, RI, *, #) as noise.
- **BILINGUAL CAPTURE**: Start by translating Arabic medicine names to standard English (e.g., "كونجستال" -> "Kongestal"). If you aren't 100% sure of the English translation, you MUST output the medicine name exactly as written in Arabic. NEVER skip or drop a medicine because it is in Arabic. Always translate dosages and forms to English (e.g., "قرص" -> "tablet").
- **LLM SELF-CORRECTION (CRITICAL)**: Compare the messy OCR against the reference list below to fix typos. If the OCR name clearly matches a reference item, use the reference spelling.
- **Aggressive Capture**: Capture any word near a dosage or clinical sign.
- **Dosage & Form**: ALWAYS identify the dosage and pharmaceutical form.
- **Contextual Specialty Correction**: Identify the doctor's specialty from the header. Use it to guide spelling corrections.
- **Smart Candidates**: For highly ambiguous names, provide 2-3 alternative candidates matching the specialty.

### REFERENCE LIST:
$common_medicines_list

---
OCR TEXT:
$ocr_text
---

### OUTPUT INSTRUCTIONS:
Return ONLY a valid JSON object. No text before or after.
Format:
{
  "doctor_specialty": "Detected specialty or 'Unknown'",
  "medicines": [
    {"name": "Brand", "active_ingredient": "Generic", "dosage": "625mg", "form": "tablet", "candidates": []}
  ],
  "ocr_text": "Brief summary of medicine-related text only."
}
""".strip())
