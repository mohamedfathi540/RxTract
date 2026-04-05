import csv
import os
import logging
import re
from typing import List, Optional, Tuple, Dict
from thefuzz import process, fuzz

logger = logging.getLogger("uvicorn.error")

class MedicineMatcher:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MedicineMatcher, cls).__new__(cls)
            cls._instance.medicines = []
            cls._instance.medicine_map = {}
            cls._instance.ingredient_map = {} # brand.lower() -> ingredient
            cls._instance.word_index = {} # word -> set of canonical names
            cls._instance.drug_types = {
                "tab", "tabs", "tablet", "tablets",
                "cap", "caps", "capsule", "capsules",
                "syr", "syrup", "susp", "suspension",
                "sp", "s.p.", "s.p",
                "amp", "amps", "ampoule", "ampoules",
                "vial", "vials",
                "cream", "oint", "ointment", "gel", "lotion", "top", "topical",
                "supp", "suppository", "suppositories",
                "sach", "sachets", "drops", "drop",
                "mg", "gm", "ml", "g", "iu", "mcg"
            }
            cls._instance._initialized = False

            # Load settings from .env via Config
            from Helpers.Config import get_settings
            _settings = get_settings()
            cls._instance.ENABLED = bool(getattr(_settings, "MEDICINE_MATCHER_ENABLED", False))
            cls._instance.token_set_threshold = int(getattr(_settings, "MEDICINE_MATCHER_TOKEN_SET_THRESHOLD", 90))
            cls._instance.partial_threshold = int(getattr(_settings, "MEDICINE_MATCHER_PARTIAL_THRESHOLD", 90))
            cls._instance.first_word_threshold = int(getattr(_settings, "MEDICINE_MATCHER_FIRST_WORD_THRESHOLD", 88))

            logger.info(
                "MedicineMatcher config: ENABLED=%s, token_set=%d, partial=%d, first_word=%d",
                cls._instance.ENABLED,
                cls._instance.token_set_threshold,
                cls._instance.partial_threshold,
                cls._instance.first_word_threshold,
            )
        return cls._instance

    def __init__(self):
        if not self.ENABLED:
            self._initialized = True
            return
        if self._initialized:
            return
            
        self._load_data()
        self._initialized = True

    def _add_medicine(self, name: str) -> bool:
        """Helper to add a medicine and index its words."""
        name_lower = name.lower()
        if name_lower not in self.medicine_map:
            self.medicines.append(name)
            self.medicine_map[name_lower] = name
            
            # Index only the first 2 alphabetical words to avoid generic descriptions (like 'center', 'children')
            words = re.split(r'[^a-z0-9]', name_lower)
            valid_words = [w for w in words if len(w) >= 3 and w.isalpha()]
            for w in set(valid_words[:2]):
                if w not in self.word_index:
                    self.word_index[w] = set()
                self.word_index[w].add(name)
            return True
        return False

    def _load_data(self):
        """Load medicines from the PostgreSQL database."""
        from Helpers.Config import get_settings
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from Models.DB_Schemes.minirag.Schemes.Medicine import Medicine
        
        # Build connection string
        app_settings = get_settings()
        db_url = f"postgresql://{app_settings.POSTGRES_USER}:{app_settings.POSTGRES_PASSWORD}@{app_settings.POSTGRES_HOST}:{app_settings.POSTGRES_PORT}/{app_settings.POSTGRES_MAIN_DB}"
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        session = SessionLocal()
        try:
            # Load all trade names and active ingredients from DB
            medicines = session.query(Medicine.trade_name, Medicine.active_ingredient).all()
            
            count = 0
            for med in medicines:
                name = med.trade_name.strip()
                if not name or len(name) <= 2:
                    continue
                    
                if self._add_medicine(name):
                    count += 1
                    
                # Store the active ingredient directly mapping from DB
                if med.active_ingredient and med.active_ingredient != "Unknown":
                    self.register_ingredient(name, med.active_ingredient)
                    
                # Add first word as candidate for better matching
                first_word = name.split()[0]
                clean_first = "".join(filter(str.isalnum, first_word))
                if len(clean_first) > 3:
                    if clean_first.lower() not in self.medicine_map:
                        self._add_medicine(clean_first)
                        self.medicine_map[clean_first.lower()] = name # Map back to full name
            
            # 3. Fallback List (Hardcoded commonly used)
            fallback_list = [
                "Augmentin", "Moxclav", "Megamox", "Hibiotic",
                "Phenadon", "Phinex", "Rhinex",
                "Cataflam", "Voltaren",
                "Antinal",
                "Kongestal", "Comtrex",
                "Panadol", "Brufen",
                "Flagyl", "Amrizole",
                "Nexium", "Omeprazole",
                "Ciprocin", "Xithrone",
                "Glucophage", "Concor",
                "Ventolin",
                "Amaryl", "Symbicort", "Prednisolone", "Aspocid"
            ]
            
            fallback_count = 0
            for name in fallback_list:
                if self._add_medicine(name):
                    fallback_count += 1
            
            logger.info(f"Loaded {count} medicines from PostgreSQL. MedicineMatcher initialized with {len(self.medicines)} total unique medicines.")
        except Exception as e:
            logger.error(f"Failed to load medicines from DB: {e}")
        finally:
            session.close()

    def get_active_ingredient(self, name: str) -> Optional[str]:
        """Get the active ingredient for a known brand name."""
        if not self.ENABLED:
            return None
        return self.ingredient_map.get(name.lower())

    def register_ingredient(self, brand: str, ingredient: str):
        """Map a brand name to an active ingredient."""
        if not self.ENABLED:
            return
        brand_lower = brand.lower()
        self.ingredient_map[brand_lower] = ingredient
        
        # Also map the canonical name from the CSV if we have one for this brand
        # This ensures that if "Augmentin" -> "Augmentin 875mg...", the full name also gets the ingredient
        canonical = self.medicine_map.get(brand_lower)
        if canonical:
            self.ingredient_map[canonical.lower()] = ingredient
        
    def find_best_match(self, query: str, threshold: int = None) -> Optional[str]:
        """
        Find the best fuzzy match for the query.
        Uses multiple matching strategies for aggressive correction.
        Returns the matched name if detection confidence >= threshold, else None.
        """
        if not self.ENABLED:
            return None
        if threshold is None:
            threshold = self.token_set_threshold
        if not query or len(query) < 4:  # Increased minimum length to avoid matching random short letters
            return None
            
        q_lower = query.lower().strip()
        
        # --- Block generic single words from aggressive matching ---
        # If the extracted name is literally just a form (like "Lotion", "Syrup", "Tablet"), do not match it to a specific brand.
        if q_lower in self.drug_types or q_lower in ["urine", "bag", "blood", "test"]:
             logger.warning(f"Blocked generic term '{query}' from fuzzy matching.")
             return None

        # Strip trailing dosage info for matching (e.g., "Augmentin 625mg" -> "Augmentin")
        q_clean = re.sub(r'\s*\d+\s*(mg|gm|g|ml|mcg|iu|%|units?)\s*(/\s*\d+\s*(mg|gm|g|ml|mcg))?\s*$', '', q_lower, flags=re.IGNORECASE).strip()
        
        # Direct exact match
        if q_lower in self.medicine_map:
            return self.medicine_map[q_lower]
        if q_clean and q_clean in self.medicine_map:
            return self.medicine_map[q_clean]
            
        # Try first word match (common for prescriptions: "Augmentin 1g" -> first word "augmentin")
        first_word = q_clean.split()[0] if q_clean else q_lower.split()[0]
        if first_word and len(first_word) >= 3 and first_word in self.medicine_map:
            return self.medicine_map[first_word]
        
        try:
            # Strategy 1: token_set_ratio on full query (handles word reordering)
            # Increased required score to 85 (was 70) to prevent "Waca" -> "MACA" (which scored 75)
            result = process.extractOne(q_clean or query, self.medicines, scorer=fuzz.token_set_ratio)
            if result and len(result) >= 2 and result[1] >= threshold: 
                # Safety check: Ensure the matched name isn't drastically longer than the query (prevents "Lotion" -> "ACM LOTION ANTI-HAIR LOSS")
                if len(result[0]) <= len(query) * 2.5: 
                    logger.info(f"Fuzzy Match (token_set): '{query}' -> '{result[0]}' (Score: {result[1]})")
                    return self.medicine_map.get(result[0].lower(), result[0])
            
            # Strategy 2: partial_ratio (handles substring matches, e.g., "Augmant" in "Augmentin")
            result2 = process.extractOne(q_clean or query, self.medicines, scorer=fuzz.partial_ratio)
            if result2 and len(result2) >= 2 and result2[1] >= self.partial_threshold:
                matched_str = result2[0]
                query_str = q_clean or query
                # STRICT SECURITY: Prevent matching ridiculously short DB entries
                # The matched string MUST be at least 5 chars AND at least 50% the length of the query
                if len(matched_str) >= 5 and len(matched_str) >= (len(query_str) * 0.5):
                    logger.info(f"Fuzzy Match (partial): '{query}' -> '{matched_str}' (Score: {result2[1]})")
                    return self.medicine_map.get(matched_str.lower(), matched_str)
                else:
                    logger.debug(f"Blocked dangerous partial match: '{query_str}' -> '{matched_str}' (too short)")
            
            # Strategy 3: ratio on first word only (handles "Augmantin tab" -> "Augmentin")
            # Increased required score to 88 (was 75) and added a stricter length requirement
            if first_word and len(first_word) >= 5:  # Changed from 4 to 5 to prevent short word snapping
                result3 = process.extractOne(first_word, self.medicines, scorer=fuzz.ratio)
                if result3 and len(result3) >= 2 and result3[1] >= self.first_word_threshold:
                    logger.info(f"Fuzzy Match (first_word): '{query}' -> '{result3[0]}' (Score: {result3[1]})")
                    return self.medicine_map.get(result3[0].lower(), result3[0])
                    
        except Exception as e:
            logger.error(f"Fuzzy match error for '{query}': {e}")
        
        return None

    def get_candidates(self, query: str, limit: int = 3) -> List[str]:
        """
        Return the top *limit* closest medicine-name candidates for *query*.
        Uses direct substring matching plus fuzzy token_set_ratio.
        """
        if not self.ENABLED:
            return []
        if not query or len(query) < 2:
            return []

        q_clean = re.sub(
            r'\s*\d+\s*(mg|gm|g|ml|mcg|iu|%|units?).*$',
            '', query.lower(),
        ).strip()
        
        q_target = q_clean or query.lower()

        try:
            # 1. Substring matching (matches anywhere in the full string)
            substring_matches = []
            for med in self.medicines:
                if q_target in med.lower():
                    canonical = self.medicine_map.get(med.lower(), med)
                    if canonical not in substring_matches:
                        substring_matches.append(canonical)
                        
            # 2. Fuzzy fallback matching
            results = process.extract(
                q_target, self.medicines,
                scorer=fuzz.token_set_ratio, limit=limit * 2,
            )
            
            # Combine them, keeping substring matches at the top priority
            candidates = list(substring_matches)
            for res_tuple in results:
                name, score = res_tuple[0], res_tuple[1]
                if score >= 50:
                    canonical = self.medicine_map.get(name.lower(), name)
                    if canonical not in candidates:
                        candidates.append(canonical)
                        
            return candidates[:limit]
        except Exception as e:
            logger.error("Candidate match error for '%s': %s", query, e)
            return []

    def find_medicines_by_ingredient(self, ingredient: str, limit: int = 5) -> List[str]:
        """
        Search the database for medicines containing the given active ingredient.
        """
        if not self.ENABLED:
            return []
        if not ingredient or ingredient.lower() == "unknown":
            return []
            
        ingredient_lower = ingredient.lower()
        # Split complex ingredients like "Amoxicillin + Clavulanic acid"
        parts = [p.strip() for p in re.split(r'[+&/|,]', ingredient_lower) if len(p.strip()) > 3]
        
        matches = []
        seen = set()
        
        # Simple heuristic: for each part of the ingredient, look for it in medicine names
        for med_name in self.medicines:
            med_lower = med_name.lower()
            
            # Avoid matching the exact same brand if possible (though we'll filter later)
            # If all parts are found in the name, it's likely a match
            matches_all = True
            for part in parts:
                if part not in med_lower:
                    matches_all = False
                    break
            
            if matches_all and med_name not in seen:
                # Get the full canonical name
                canonical = self.medicine_map.get(med_lower, med_name)
                if canonical not in seen:
                    matches.append(canonical)
                    seen.add(canonical)
                if len(matches) >= limit:
                    break
        
        return set(matches) # Avoid duplicates returning list, oops matches is returning list

    def extract_medicines_from_text(self, text: str) -> List[dict]:
        """
        Algorithmic extraction of medicines from raw OCR text.
        Finds drug types and uses word-level indexing combined with fuzzy matching
        to forcefully match parts of names against the database.
        """
        if not self.ENABLED:
            return []
        if not text or not text.strip():
            return []

        # Tokenize preserving some punctuation to split words loosely
        raw_words = text.split()
        words = []
        for rw in raw_words:
            clean = re.sub(r'[^a-zA-Z0-9]', '', rw).lower()
            if clean:
                words.append(clean)

        def is_valid_name_part(w: str) -> bool:
            if w in self.drug_types: return False
            if re.match(r'^\d+[a-z]*$', w): return False # skip 500mg, 10g, etc.
            stop_words = {
                "patient", "name", "dr", "doctor", "unknown", "drug", 
                "date", "dated", "age", "aged", "years", "year", "weight", "weighing",
                "kg", "includes", "four", "medications", "every", "hours", "hour",
                "center", "address", "emergency", "contact", "numbers", "provided",
                "bottom", "nose", "two", "the", "for", "and", "from", "image", "prescription"
            }
            if w in stop_words: return False
            return True

        candidates = set()
        
        # 1. Search near drug_types (like tab, cap, syr)
        # Look backwards up to 3 words
        for i, word in enumerate(words):
            if word in self.drug_types:
                start = max(0, i - 3)
                for j in range(start, i):
                    w = words[j]
                    if len(w) >= 3 and is_valid_name_part(w):
                        # Find matches in word_index
                        for index_w, meds in self.word_index.items():
                            if w == index_w or fuzz.ratio(w, index_w) >= 80:
                                best_med = min(meds, key=len)
                                candidates.add(best_med)

        # 2. General scan of all words >= 4 length against the word index
        for w in words:
            if len(w) >= 4 and is_valid_name_part(w):
                for index_w, meds in self.word_index.items():
                    if w == index_w or fuzz.ratio(w, index_w) >= 85:
                        best_med = min(meds, key=len)
                        candidates.add(best_med)

        results = []
        seen = set()

        for cand in candidates:
            canonical = self.medicine_map.get(cand.lower(), cand)
            if canonical not in seen:
                active = self.get_active_ingredient(canonical) or "Unknown"
                # Try to extract dosage and form from nearby text
                dosage, form = self.extract_dosage_and_form(text, canonical)
                results.append({
                    "name": canonical,
                    "active_ingredient": active,
                    "dosage": dosage,
                    "form": form,
                })
                seen.add(canonical)

        logger.info(f"Algorithmic extraction found {len(results)} medicines.")
        return results

    @staticmethod
    def extract_dosage_from_string(text: str) -> str:
        """
        Extract dosage/strength from a string (e.g., '100mg', '1g', '250mg/5ml').
        """
        if not text:
            return "Unknown"
        # Match patterns like: 100mg, 1g, 500 mg, 250mg/5ml, 0.5g, 20mcg, 1000iu, 5%
        pattern = r'(\d+(?:\.\d+)?\s*(?:mg|gm|g|ml|mcg|iu|%|units?)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:mg|gm|g|ml|mcg))?)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "Unknown"

    @staticmethod
    def extract_form_from_string(text: str) -> str:
        """
        Extract pharmaceutical form from a string.
        """
        if not text:
            return "Unknown"
        text_lower = text.lower()
        form_map = {
            r'\b(?:tab|tabs|tablet|tablets)\b': 'tablet',
            r'\b(?:cap|caps|capsule|capsules)\b': 'capsule',
            r'\b(?:syr|syrup)\b': 'syrup',
            r'\b(?:susp|suspension)\b': 'suspension',
            r'\b(?:supp|suppository|suppositories|sub)\b': 'suppository',
            r'\b(?:amp|amps|ampoule|ampoules)\b': 'ampoule',
            r'\b(?:inj|injection)\b': 'injection',
            r'\b(?:cream)\b': 'cream',
            r'\b(?:oint|ointment)\b': 'ointment',
            r'\b(?:gel)\b': 'gel',
            r'\b(?:lotion)\b': 'lotion',
            r'\b(?:drops?|eye\s*drops?|ear\s*drops?)\b': 'drops',
            r'\b(?:sach|sachets?)\b': 'sachet',
            r'\b(?:spray|nasal\s*spray)\b': 'spray',
            r'\b(?:inhaler)\b': 'inhaler',
            r'\b(?:vial|vials)\b': 'vial',
            r'\b(?:solution|sol)\b': 'solution',
            r'\b(?:topical|top)\b': 'topical',
            r'\b(?:patch|patches)\b': 'patch',
            r'\b(?:powder)\b': 'powder',
            r'\b(?:sp|s\.p\.?|s\.p)\b': 'suppository',
        }
        for pattern, form_name in form_map.items():
            if re.search(pattern, text_lower):
                return form_name
        return "Unknown"

    def extract_dosage_and_form(self, full_text: str, medicine_name: str) -> Tuple[str, str]:
        """
        Search the full OCR text for dosage and form near a medicine name.
        """
        dosage = "Unknown"
        form = "Unknown"
        
        if not full_text or not medicine_name:
            return dosage, form
        
        # Find the medicine name in the text and look at nearby context
        name_lower = medicine_name.lower().split()[0]  # Use first word
        text_lower = full_text.lower()
        
        idx = text_lower.find(name_lower)
        if idx == -1:
            # Try fuzzy find
            for i in range(len(text_lower) - len(name_lower) + 1):
                chunk = text_lower[i:i + len(name_lower)]
                if fuzz.ratio(name_lower, chunk) >= 80:
                    idx = i
                    break
        
        if idx >= 0:
            # Get context window around the medicine name (100 chars after)
            context = full_text[idx:idx + 100]
            dosage = self.extract_dosage_from_string(context)
            form = self.extract_form_from_string(context)
        return dosage, form

    def get_database_pool_for_llm(self, ocr_text: str, max_items: int = 100) -> str:
        """
        Creates a dynamic subset of the database containing potential matches
        for the LLM to use for self-correction.
        """
        if not ocr_text:
            return "No database records retrieved."

        # Extract meaningful words from OCR text
        words = [w for w in re.split(r'[^a-zA-Z0-9]', ocr_text.lower()) if len(w) >= 3]
        pool = set()

        for word in words:
            # 1. Add matches from the word index
            if word in self.word_index:
                pool.update(self.word_index[word])

            # 2. Add substring matches (fast scan)
            for med in self.medicines:
                if word in med.lower():
                    canonical = self.medicine_map.get(med.lower(), med)
                    pool.add(canonical)
                    if len(pool) >= max_items:
                        break
            if len(pool) >= max_items:
                break

        if not pool:
            return "No close database matches found."

        limited_pool = list(pool)[:max_items]
        return "\n".join([f"- {name}" for name in limited_pool])


