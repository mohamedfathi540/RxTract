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
            cls._instance.ingredient_map = {}  # brand.lower() -> ingredient
            cls._instance.word_index = {}       # word -> set of canonical names
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
        """
        Lightweight init — does NOT load DB data.
        Call `await MedicineMatcher.create(db_client)` at app startup instead.
        If ENABLED=False, the instance is still usable but all methods are no-ops.
        """
        if not self.ENABLED:
            self._initialized = True
            return
        # If already populated by create(), skip silently.
        if self._initialized:
            return

    # ------------------------------------------------------------------
    # Async factory — call ONCE at app startup
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls, db_client) -> "MedicineMatcher":
        """
        Async factory method that loads medicine data from PostgreSQL using
        the app's existing AsyncSession factory.  Call once during startup:

            app.medicine_matcher = await MedicineMatcher.create(app.db_client)

        Returns the singleton instance (populated).
        """
        instance = cls()          # creates / returns the singleton via __new__

        if not instance.ENABLED:
            logger.info("[MedicineMatcher] Disabled — skipping DB load.")
            instance._initialized = True
            return instance

        if instance._initialized and instance.medicines:
            logger.info("[MedicineMatcher] Already loaded — skipping duplicate create().")
            return instance

        try:
            from sqlalchemy.future import select
            from Models.DB_Schemes.minirag.Schemes.Medicine import Medicine

            async with db_client() as session:
                result = await session.execute(
                    select(Medicine.trade_name, Medicine.active_ingredient)
                )
                rows = result.fetchall()

            count = 0
            for row in rows:
                name = (row.trade_name or "").strip()
                if not name or len(name) <= 2:
                    continue

                if instance._add_medicine(name):
                    count += 1

                if row.active_ingredient and row.active_ingredient != "Unknown":
                    instance.register_ingredient(name, row.active_ingredient)

                # Index first word for quick lookups
                first_word = name.split()[0]
                clean_first = "".join(filter(str.isalnum, first_word))
                if len(clean_first) > 3 and clean_first.lower() not in instance.medicine_map:
                    instance._add_medicine(clean_first)
                    instance.medicine_map[clean_first.lower()] = name

            # Hardcoded fallback list for very common names
            for name in [
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
            ]:
                instance._add_medicine(name)

            logger.info(
                "[MedicineMatcher] Loaded %d medicines from PostgreSQL. Total unique: %d.",
                count, len(instance.medicines),
            )
            instance._initialized = True

        except Exception as e:
            logger.error("[MedicineMatcher] Failed to load medicines from DB: %s", e)
            instance._initialized = True   # mark done so we don't retry on every request

        return instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_medicine(self, name: str) -> bool:
        """Helper to add a medicine and index its words."""
        name_lower = name.lower()
        if name_lower not in self.medicine_map:
            self.medicines.append(name)
            self.medicine_map[name_lower] = name

            words = re.split(r'[^a-z0-9]', name_lower)
            valid_words = [w for w in words if len(w) >= 3 and w.isalpha()]
            for w in set(valid_words[:2]):
                if w not in self.word_index:
                    self.word_index[w] = set()
                self.word_index[w].add(name)
            return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        canonical = self.medicine_map.get(brand_lower)
        if canonical:
            self.ingredient_map[canonical.lower()] = ingredient

    def find_best_match(self, query: str, threshold: int = None) -> Tuple[Optional[str], float]:
        """
        Find the best fuzzy match for the query.

        Returns:
            (matched_name, confidence)  — confidence is in [0.0, 1.0].
            Returns (None, 0.0) when no match meets the threshold.
        """
        if not self.ENABLED:
            return None, 0.0
        if threshold is None:
            threshold = self.token_set_threshold
        if not query or len(query) < 4:
            return None, 0.0

        q_lower = query.lower().strip()

        if q_lower in self.drug_types or q_lower in {"urine", "bag", "blood", "test"}:
            logger.warning("Blocked generic term '%s' from fuzzy matching.", query)
            return None, 0.0

        q_clean = re.sub(
            r'\s*\d+\s*(mg|gm|g|ml|mcg|iu|%|units?)(\s*/\s*\d+\s*(mg|gm|g|ml|mcg))?\s*$',
            '', q_lower, flags=re.IGNORECASE
        ).strip()

        # Direct exact match → full confidence
        if q_lower in self.medicine_map:
            return self.medicine_map[q_lower], 1.0
        if q_clean and q_clean in self.medicine_map:
            return self.medicine_map[q_clean], 1.0

        # First-word exact match
        first_word = q_clean.split()[0] if q_clean else q_lower.split()[0]
        if first_word and len(first_word) >= 3 and first_word in self.medicine_map:
            return self.medicine_map[first_word], 0.97

        try:
            # Strategy 1: token_set_ratio
            result = process.extractOne(q_clean or query, self.medicines, scorer=fuzz.token_set_ratio)
            if result and len(result) >= 2 and result[1] >= threshold:
                if len(result[0]) <= len(query) * 2.5:
                    confidence = result[1] / 100.0
                    logger.info("Fuzzy Match (token_set): '%s' -> '%s' (Score: %d)", query, result[0], result[1])
                    return self.medicine_map.get(result[0].lower(), result[0]), confidence

            # Strategy 2: partial_ratio
            result2 = process.extractOne(q_clean or query, self.medicines, scorer=fuzz.partial_ratio)
            if result2 and len(result2) >= 2 and result2[1] >= self.partial_threshold:
                matched_str = result2[0]
                query_str = q_clean or query
                if len(matched_str) >= 5 and len(matched_str) >= (len(query_str) * 0.5):
                    confidence = result2[1] / 100.0
                    logger.info("Fuzzy Match (partial): '%s' -> '%s' (Score: %d)", query, matched_str, result2[1])
                    return self.medicine_map.get(matched_str.lower(), matched_str), confidence
                else:
                    logger.debug("Blocked dangerous partial match: '%s' -> '%s' (too short)", query_str, matched_str)

            # Strategy 3: ratio on first word only
            if first_word and len(first_word) >= 5:
                result3 = process.extractOne(first_word, self.medicines, scorer=fuzz.ratio)
                if result3 and len(result3) >= 2 and result3[1] >= self.first_word_threshold:
                    confidence = result3[1] / 100.0
                    logger.info("Fuzzy Match (first_word): '%s' -> '%s' (Score: %d)", query, result3[0], result3[1])
                    return self.medicine_map.get(result3[0].lower(), result3[0]), confidence

        except Exception as e:
            logger.error("Fuzzy match error for '%s': %s", query, e)

        return None, 0.0

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
            substring_matches = []
            for med in self.medicines:
                if q_target in med.lower():
                    canonical = self.medicine_map.get(med.lower(), med)
                    if canonical not in substring_matches:
                        substring_matches.append(canonical)

            results = process.extract(
                q_target, self.medicines,
                scorer=fuzz.token_set_ratio, limit=limit * 2,
            )

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
        Search the in-memory index for medicines containing the given active ingredient.
        Uses the ingredient_map populated at startup from the DB.

        For a deeper SQL-based search (when session is available), use
        MedicineDBService.search_by_ingredient() instead.
        """
        if not self.ENABLED:
            return []
        if not ingredient or ingredient.lower() == "unknown":
            return []

        ingredient_lower = ingredient.lower()
        parts = [p.strip() for p in re.split(r'[+&/|,]', ingredient_lower) if len(p.strip()) > 3]

        matches = []
        seen = set()

        # Search the ingredient_map (brand -> ingredient)
        for brand_lower, ing in self.ingredient_map.items():
            if not ing:
                continue
            ing_lower = ing.lower()
            if all(part in ing_lower for part in parts):
                canonical = self.medicine_map.get(brand_lower, brand_lower)
                if canonical not in seen:
                    matches.append(canonical)
                    seen.add(canonical)
                if len(matches) >= limit:
                    break

        return matches

    def extract_medicines_from_text(self, text: str) -> List[dict]:
        """
        Algorithmic extraction of medicines from raw OCR text.
        """
        if not self.ENABLED:
            return []
        if not text or not text.strip():
            return []

        raw_words = text.split()
        words = []
        for rw in raw_words:
            clean = re.sub(r'[^a-zA-Z0-9]', '', rw).lower()
            if clean:
                words.append(clean)

        def is_valid_name_part(w: str) -> bool:
            if w in self.drug_types: return False
            if re.match(r'^\d+[a-z]*$', w): return False
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

        for i, word in enumerate(words):
            if word in self.drug_types:
                start = max(0, i - 3)
                for j in range(start, i):
                    w = words[j]
                    if len(w) >= 3 and is_valid_name_part(w):
                        for index_w, meds in self.word_index.items():
                            if w == index_w or fuzz.ratio(w, index_w) >= 80:
                                best_med = min(meds, key=len)
                                candidates.add(best_med)

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
                dosage, form = self.extract_dosage_and_form(text, canonical)
                results.append({
                    "name": canonical,
                    "active_ingredient": active,
                    "dosage": dosage,
                    "form": form,
                })
                seen.add(canonical)

        logger.info("Algorithmic extraction found %d medicines.", len(results))
        return results

    @staticmethod
    def extract_dosage_from_string(text: str) -> str:
        if not text:
            return "Unknown"
        pattern = r'(\d+(?:\.\d+)?\s*(?:mg|gm|g|ml|mcg|iu|%|units?)(?:\s*/\s*\d+(?:\.\d+)?\s*(?:mg|gm|g|ml|mcg))?)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "Unknown"

    @staticmethod
    def extract_form_from_string(text: str) -> str:
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
        dosage = "Unknown"
        form = "Unknown"

        if not full_text or not medicine_name:
            return dosage, form

        name_lower = medicine_name.lower().split()[0]
        text_lower = full_text.lower()

        idx = text_lower.find(name_lower)
        if idx == -1:
            for i in range(len(text_lower) - len(name_lower) + 1):
                chunk = text_lower[i:i + len(name_lower)]
                if fuzz.ratio(name_lower, chunk) >= 80:
                    idx = i
                    break

        if idx >= 0:
            context = full_text[idx:idx + 100]
            dosage = self.extract_dosage_from_string(context)
            form = self.extract_form_from_string(context)
        return dosage, form

    def get_database_pool_for_llm(self, ocr_text: str, max_items: int = 100) -> str:
        if not ocr_text:
            return "No database records retrieved."

        words = [w for w in re.split(r'[^a-zA-Z0-9]', ocr_text.lower()) if len(w) >= 3]
        pool = set()

        for word in words:
            if word in self.word_index:
                pool.update(self.word_index[word])

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
