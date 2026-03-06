from string import Template


### Prescription Extraction Prompts ###


### Vision Extraction Prompt ###

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

vision_extraction_prompt = Template("""
You are a Senior Egyptian Pharmacist with 20+ years of experience reading handwritten prescriptions.
### GOAL:
Extract EVERY medication from the prescription with its dosage strength and pharmaceutical form.

### RULES:
1. **Noisy Text**: OCR often adds noise like ($$, @, #, &, /, RI). IGNORE these symbols and focus on the word next to them.
2. **Clinical Signals**: Look for words near numbers (1, 2, 3), bullets, or clinical symbols (R, R/, /, *, -).
3. **Dosage Clues**: Any word followed by "tab", "cap", "mg", "gm", "syr", "susp", "cream", "tob", "Ta6" is a medicine.
4. **Capture All**: Extract the name even if it looks misspelled or garbled (e.g., "Mil9a" -> Milga, "Thictacid" -> Thiotacid, "Dina Ta6" -> Dina).
5. **No Gatekeeping**: DO NOT skip a medicine just because it isn't in your head or in the reference list.
6. **No Filler**: Return ONLY the JSON. No explanations.
7. **Dosage Strength**: ALWAYS extract the dosage/strength if visible (e.g., "100mg", "500mg", "1g", "250mg/5ml", "20mg", "0.5g"). Look for numbers followed by mg, g, gm, ml, mcg, iu, %, units near the medicine name.
8. **Pharmaceutical Form**: ALWAYS extract the form/type (e.g., "tablet", "syrup", "capsule", "suppository", "cream", "injection", "drops", "sachet", "ampoule", "ointment", "gel", "suspension", "inhaler"). Common abbreviations: tab=tablet, cap=capsule, syr=syrup, susp=suspension, supp=suppository, amp=ampoule, inj=injection, sach=sachet.
9. **Aggressive Name Correction**: If a name looks like a known medicine but is misspelled, correct it. E.g., "Augmantin"->"Augmentin", "Cataflem"->"Cataflam", "Panadl"->"Panadol", "Brufin"->"Brufen".

### MEDICINE REFERENCE (Examples):
$common_medicines_list

### OUTPUT FORMAT (JSON ONLY — medicines FIRST, then ocr_text):
{
  "medicines": [
    {
      "name": "Brand name (e.g., Augmentin)",
      "active_ingredient": "Generic (or 'Unknown')",
      "dosage": "Strength (e.g., '625mg', '100mg', '1g') or 'Unknown'",
      "form": "Form (e.g., 'tablet', 'syrup', 'capsule', 'suppository') or 'Unknown'"
    }
  ],
  "ocr_text": "ONE short sentence (max 30 words) summarizing ONLY the medicine-related text. Do NOT include clinic names, phone numbers, addresses, or non-medical text."
}
""".strip())

### Text Extraction Prompt ###

text_extraction_prompt = Template("""
You are a Senior Egyptian Pharmacist and Medical Data Analyst with expertise in reading messy OCR output from handwritten prescriptions.
### TASK:
Extract ALL medicine brand names, ingredients, dosage strengths, and pharmaceutical forms from this OCR text.

### EXTRACTION GUIDELINES:
- **Ignore Noise**: Treat characters like ($$, @, RI, *, (, #) as noise/prefixes. Focus on the drug name.
- **Clinical Signals**: Words after "R", "R/", "/", or in numbered lists are medicines.
- **Dosage Signals**: Words followed by "tab", "cap", "mg", "gm", "syr", "cream", "Ta6", "tob" are medicines.
- **Aggressive Capture**: If a word is near a dosage or clinical sign (e.g., "Mil9a", "Thiotaid", "flde", "Dima Ta6"), capture it!
- **Ingredient Lookup**: Use the list below + your knowledge. Default to "Unknown" if unsure.
- **Dosage Strength**: ALWAYS look for numbers+units near each medicine name: "100mg", "500mg", "1g", "250mg/5ml", "20mg", "0.5g", "10ml". Extract EXACTLY as written.
- **Pharmaceutical Form**: ALWAYS identify the form/type: tablet (tab), capsule (cap), syrup (syr), suspension (susp), suppository (supp), cream, ointment (oint), gel, drops, injection (inj), ampoule (amp), sachet (sach), inhaler, spray, solution. 
- **Aggressive Name Correction**: If a name is slightly misspelled, correct it to the closest known medicine. E.g., "Augmantin"->"Augmentin", "Cataflem"->"Cataflam", "Brufin"->"Brufen".

### REFERENCE LIST:
$common_medicines_list

---
OCR TEXT:
$ocr_text
---

### OUTPUT INSTRUCTIONS:
Return ONLY a valid JSON array. No text before or after.
Format: [{"name": "Brand", "active_ingredient": "Generic", "dosage": "625mg", "form": "tablet"}]
If dosage or form is not visible, use "Unknown".
""".strip())
