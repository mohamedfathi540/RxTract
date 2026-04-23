# SRC/Services/MedicineDBService.py
"""
MedicineDBService — request-scoped service for deep ingredient-based DB lookups.

This complements the in-memory MedicineMatcher singleton.  Use this when
a session is already available (e.g., inside an endpoint or agent tool) and
the fast in-memory lookup returned no results.
"""

import logging
import re
from typing import Any

from sqlalchemy.future import select
from sqlalchemy import or_

from Models.DB_Schemes.minirag.Schemes.Medicine import Medicine

logger = logging.getLogger("uvicorn.error")


class MedicineDBService:
    """
    Deep SQL ingredient search.

    Usage pattern (in endpoints that have a session, or agent tools):

        # 1. Fast in-memory lookup first
        results = app.medicine_matcher.find_medicines_by_ingredient(ingredient)

        # 2. Fallback to DB if needed
        if not results:
            db_svc = MedicineDBService(db_session)
            results = await db_svc.search_by_ingredient(ingredient)
    """

    def __init__(self, db_session: Any):
        # Accepts an already-open AsyncSession (not a factory)
        self.session = db_session

    async def search_by_ingredient(self, ingredient: str, limit: int = 5) -> list[str]:
        """
        SQL wildcard search against Medicine.active_ingredient.

        Splits composite ingredients (e.g. "Amoxicillin + Clavulanic acid")
        and builds OR filters so that any part matches.

        Args:
            ingredient: Active ingredient string, possibly composite.
            limit:      Maximum number of trade names to return.

        Returns:
            List of matching trade_name strings.
        """
        if not ingredient or ingredient.lower() == "unknown":
            return []

        parts = [
            p.strip()
            for p in re.split(r'[+&/|,]', ingredient)
            if len(p.strip()) > 3
        ]
        if not parts:
            return []

        filters = [Medicine.active_ingredient.ilike(f"%{p}%") for p in parts]
        stmt = (
            select(Medicine.trade_name)
            .where(or_(*filters))
            .limit(limit)
        )

        try:
            result = await self.session.execute(stmt)
            names = [row[0] for row in result.fetchall() if row[0]]
            logger.info(
                "[MedicineDBService] ingredient=%r → %d results", ingredient, len(names)
            )
            return names
        except Exception as e:
            logger.error("[MedicineDBService] search_by_ingredient failed: %s", e)
            return []
