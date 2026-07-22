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
Nexium/Controloc/Protofix → Esomeprazole / Pantoprazole
Ciprocin/Ciprofloxacin → Ciprofloxacin
Xithrone/Zithrokan → Azithromycin
Glucophage/Cidophage → Metformin
Concor/Biso → Bisoprolol
Ventolin/Farcolin → Salbutamol
Actifolic → Folic Acid
Milga/Milv/Mil9a → Vitamin B12 + B6 + B1
Thiotacid/Thictacid/Thioctacid → Thioctic Acid
Fastcur/Fastcure/Fastkur → Omeprazole
Mucosta → Rebamipide
"""

# --- Arabic Medicine Name Reference Table ---
# Used by both prompts to resolve common Arabic brand name spellings.
ARABIC_MEDICINE_REFERENCE = """
باندول / بنادول        → Panadol (Paracetamol)
كونجستال               → Kongestal (Paracetamol + Chlorpheniramine + Pseudoephedrine)
فلاجيل                 → Flagyl (Metronidazole)
أوجمنتين / اوجمنتين   → Augmentin (Amoxicillin + Clavulanic acid)
سيبروسين / سيبروفلوكساسين → Ciprocin (Ciprofloxacin)
فولتارين / كتافلام     → Voltaren / Cataflam (Diclofenac)
نيكسيوم / نكسيوم       → Nexium (Esomeprazole)
فينتولين / فارسولين     → Ventolin (Salbutamol)
جلوكوفاج               → Glucophage (Metformin)
بروفين                 → Brufen (Ibuprofen)
كونكور                 → Concor (Bisoprolol)
كتافاست / كتافلام      → Catafast / Cataflam (Diclofenac)
زيثروكان / زيثرومكس    → Zithrokan / Zithromax (Azithromycin)
أنتينال / انتينال       → Antinal (Nifuroxazide)
بيوفيرا / ميلجا        → Milga (Vitamin B complex)
سيتال / باراسيتامول    → Cetal / Paracetamol
كولشيسين               → Colchicine
ديكلوفيناك             → Diclofenac
ليفوكسين / تافانيك     → Levoxin / Tavanic (Levofloxacin)
رانيتيدين              → Ranitidine
أوميبرازول             → Omeprazole
فاست كور / فاستكور     → Fastcur (Omeprazole)
ميوكوستا / موكوستا     → Mucosta (Rebamipide)
بروتوفكس / بروتوفيكس    → Protofix (Pantoprazole)
"""

# --- 1. VISION PROMPT (TRANSCRIPTION ONLY - NO JSON) ---
vision_extraction_prompt = Template("""
You are a highly precise OCR transcription engine. 

YOUR ONLY TASK: Transcribe the text from the prescription image EXACTLY as written. DO NOT act as a pharmacist. DO NOT try to correct misspellings. DO NOT guess or infer medicine names.

=== CRITICAL RULES ===
1. TRANSCRIBE EXACTLY WHAT YOU SEE. If a word is misspelled, looks like gibberish, or has weird letters (e.g. "Anselex", "Conventin", "Axomyelin"), output it EXACTLY as written.
2. DO NOT guess common medicine names. NEVER output "Concor", "Augmentin", or other common brands unless those exact letters are clearly and undeniably visible.
3. DO NOT skip or ignore any Arabic text. Arabic is just as valid as English. Transcribe Arabic words exactly as handwritten (e.g., "قرص", "بعد العشاء").
4. If an Arabic word EXACTLY matches a name from the reference table below, you may output BOTH the Arabic and the English equivalent side-by-side (e.g. "باندول (Panadol)").
5. Transcribe ALL English text, dosages (mg, gm, ml), and forms (tab, cap, syrup).

=== ARABIC MEDICINE REFERENCE TABLE ===
$arabic_medicine_reference

=== FORMAT ===
DO NOT format as JSON. Output plain text EXACTLY as seen.
Write medicines as a numbered list, one per line:
Rx 1:
[Transcription of medicine 1]
Rx 2:
[Transcription of medicine 2]
""".strip())


# Inject the arabic reference into the vision prompt substitution keys
vision_extraction_prompt_with_arabic = Template(
    vision_extraction_prompt.safe_substitute(
        arabic_medicine_reference=ARABIC_MEDICINE_REFERENCE
    ).replace("$arabic_medicine_reference", ARABIC_MEDICINE_REFERENCE)
)

# --- 2. TEXT PROMPT (TRANSLATION & JSON FORMATTING) ---
text_extraction_prompt = Template("""
You are a Senior Egyptian Pharmacist and Medical Data Analyst.

=== TASK ===
Extract ALL medicines from the OCR text below. The text may contain Arabic names, English names, or a mix.

=== ARABIC NAME RESOLUTION (CRITICAL) ===
Arabic medicine names are FIRST-CLASS citizens. Apply this resolution order:

STEP 1 — Check the Arabic Reference Table below. If the Arabic word matches, use the English brand name.
STEP 2 — If no match, use phonetic knowledge: Arabic drug names are often Arabicised Latin (e.g., "أوجمنتين" → "Augmentin", "فلاجيل" → "Flagyl").
STEP 3 — If still uncertain, output the Arabic name EXACTLY as written in the "name" field. NEVER drop it.

=== ENGLISH NAME RULES (CRITICAL) ===
1. If the medicine name is written in English (e.g., "Praxilene", "Dapa plus", "Lantus"), YOU MUST OUTPUT THE EXACT ENGLISH BRAND NAME in the "name" field.
2. DO NOT replace an English brand name with its active ingredient (e.g., do not change "Lantus" to "Insulin Glargine" in the name field).
3. DO NOT replace an English brand name with another brand name (e.g., do not change "Glaptive" to "Glucophage").
4. ONLY use the "name_ar" field if the original text was actually written in Arabic script. If it was English, leave "name_ar" empty.

=== ARABIC MEDICINE REFERENCE TABLE ===
$arabic_medicine_reference

=== EXTRACTION RULES ===
- **CRITICAL COMPLETENESS**: You MUST extract EVERY SINGLE medicine listed in the OCR text. If the OCR text has a numbered list (e.g., 1, 2, 3...), your JSON array MUST contain exactly that many items. DO NOT SKIP any items.
- **Unrecognized Names**: If a name looks weird, misspelled, or unrecognized (e.g., "D. Dep", "Moventor"), YOU MUST STILL EXTRACT IT exactly as written. NEVER drop an item just because you don't recognize it.
- **Ignore Noise**: Treat ($$, @, RI, *, #) as noise — skip them.
- **NEVER DROP a medicine**: If you see an Arabic or English word near a dosage or clinical sign, capture it.
- **Bilingual Forms**: Always translate dosage UNITS and FORMS to English (e.g., "قرص" → "tablet", "حقن" → "injection", "شراب" → "syrup", "مجم" → "mg", "جرام" → "g").
- **Dosage & Form**: ALWAYS extract dosage (e.g., 500mg) and form (e.g., tablet).
- **Contextual Specialty**: Identify doctor's specialty from the header. Use it to guide ambiguous name resolution.
- **Smart Candidates**: For highly ambiguous names, provide 2–3 alternative brand name candidates.
- **LLM Self-Correction**: Compare OCR text against the REFERENCE LIST below. Fix clear misspellings using reference spelling.

=== BRAND NAME REFERENCE LIST ===
$common_medicines_list

---
OCR TEXT:
$ocr_text
---

=== OUTPUT ===
Return ONLY a valid JSON object. No text before or after.

{
  "doctor_specialty": "Detected specialty or 'Unknown'",
  "medicines": [
    {
      "name": "Exact brand name from text (English or translated from Arabic). DO NOT hallucinate other names.",
      "name_ar": "Arabic name as written (leave empty if written in English)",
      "active_ingredient": "Generic name or 'Unknown'",
      "dosage": "e.g. 500mg",
      "form": "e.g. tablet",
      "candidates": ["AltBrand1", "AltBrand2"]
    }
  ]
}
""".strip())
