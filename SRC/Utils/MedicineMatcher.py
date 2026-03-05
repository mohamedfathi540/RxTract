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
        return cls._instance

    def __init__(self):
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
        """Load medicines from CSVs and fallback list."""
        
        # 1. Load from Primary CSV (Pharmacy_Products.csv)
        # Using relative path assuming this file is in SRC/Utils
        csv_path = os.path.join(
            os.path.dirname(__file__), 
            "../Assets/Files/1/Pharmacy_Products.csv"
        )
        csv_path = os.path.abspath(csv_path)

        count = 0
        if os.path.exists(csv_path):
            try:
                with open(csv_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("name")
                        if name:
                            name = name.strip()
                            if self._add_medicine(name):
                                count += 1
                            
                            # Add first word as candidate for better matching
                            first_word = name.split()[0]
                            clean_first = "".join(filter(str.isalnum, first_word))
                            if len(clean_first) > 3:
                                if clean_first.lower() not in self.medicine_map:
                                    self._add_medicine(clean_first)
                                    self.medicine_map[clean_first.lower()] = name # Map back to full name
                logger.info(f"Loaded {count} medicines from Pharmacy_Products.csv")
            except Exception as e:
                logger.error(f"Failed to load {csv_path}: {e}")
        else:
            logger.warning(f"Pharmacy_Products.csv not found at {csv_path}")

        # 2. Load from Scraped CSV (eda_medicines.csv) if exists
        eda_path = os.path.join(
            os.path.dirname(__file__),
            "../Assets/Files/eda_medicines.csv"
        )
        eda_path = os.path.abspath(eda_path)

        if os.path.exists(eda_path):
            try:
                eda_count = 0
                with open(eda_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Assumes 'Trade Name' or 'name' column
                        name = row.get("Trade Name") or row.get("name")
                        if name:
                            name = name.strip()
                            if self._add_medicine(name):
                                eda_count += 1
                logger.info(f"Loaded {eda_count} medicines from eda_medicines.csv")
            except Exception as e:
                logger.error(f"Failed to load {eda_path}: {e}")

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
        
        logger.info(f"MedicineMatcher initialized with {len(self.medicines)} total unique medicines.")

    def get_active_ingredient(self, name: str) -> Optional[str]:
        """Get the active ingredient for a known brand name."""
        return self.ingredient_map.get(name.lower())

    def register_ingredient(self, brand: str, ingredient: str):
        """Map a brand name to an active ingredient."""
        brand_lower = brand.lower()
        self.ingredient_map[brand_lower] = ingredient
        
        # Also map the canonical name from the CSV if we have one for this brand
        # This ensures that if "Augmentin" -> "Augmentin 875mg...", the full name also gets the ingredient
        canonical = self.medicine_map.get(brand_lower)
        if canonical:
            self.ingredient_map[canonical.lower()] = ingredient
        
    def find_best_match(self, query: str, threshold: int = 85) -> Optional[str]:
        """
        Find the best fuzzy match for the query.
        Returns the matched name if detection confidence >= threshold, else None.
        """
        if not query or len(query) < 3:
            return None
            
        q_lower = query.lower()
        if q_lower in self.medicine_map:
            return self.medicine_map[q_lower]
            
        # Extract matches
        # extractOne returns (match, score, index) or just (match, score) depending on version
        # process.extractOne("query", choices)
        
        try:
            # Use token_set_ratio to avoid replacing short names like 'Safe' with huge strings
            result = process.extractOne(query, self.medicines, scorer=fuzz.token_set_ratio)
            
            if result:
                if len(result) >= 2:
                    match_name = result[0]
                    score = result[1]
                    
                    if score >= 85: # Use high threshold for short string safety
                        logger.info(f"Fuzzy Match: '{query}' -> '{match_name}' (Score: {score})")
                        return self.medicine_map.get(match_name.lower(), match_name)
        except Exception as e:
            logger.error(f"Fuzzy match error for '{query}': {e}")
        
        return None
    def find_medicines_by_ingredient(self, ingredient: str, limit: int = 5) -> List[str]:
        """
        Search the database for medicines containing the given active ingredient.
        """
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
                    if len(w) >= 4 and is_valid_name_part(w):
                        # Find matches in word_index
                        for index_w, meds in self.word_index.items():
                            if w == index_w or fuzz.ratio(w, index_w) >= 90:
                                best_med = min(meds, key=len)
                                candidates.add(best_med)

        # 2. General scan of all words >= 5 length against the word index
        for w in words:
            if len(w) >= 5 and is_valid_name_part(w):
                for index_w, meds in self.word_index.items():
                    if w == index_w or fuzz.ratio(w, index_w) >= 95:
                        best_med = min(meds, key=len)
                        candidates.add(best_med)

        results = []
        seen = set()

        for cand in candidates:
            canonical = self.medicine_map.get(cand.lower(), cand)
            if canonical not in seen:
                active = self.get_active_ingredient(canonical) or "Unknown"
                results.append({
                    "name": canonical,
                    "active_ingredient": active
                })
                seen.add(canonical)

        logger.info(f"Algorithmic extraction found {len(results)} medicines.")
        return results

