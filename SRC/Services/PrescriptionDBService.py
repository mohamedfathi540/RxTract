# SRC/Services/PrescriptionDBService.py
"""
PrescriptionDBService — request-scoped service for fetching prescription data.

This service wraps raw DB queries against the `chunks` table, which stores
the medicine data extracted from a prescription analysis.  It is constructed
with the app's AsyncSession factory and intended to be created per-request.
"""

import logging
from typing import Any

from sqlalchemy.future import select

from Models.DB_Schemes.minirag.Schemes.Data_Chunk import dataChunk

logger = logging.getLogger("uvicorn.error")


class PrescriptionDBService:
    """
    Fetches prescription data (dataChunk rows) for a given project_id.

    Args:
        db_client: The app-level AsyncSession factory (e.g., app.db_client).
    """

    def __init__(self, db_client: Any):
        self._db = db_client

    async def get_prescription(self, project_id: str) -> dict:
        """
        Retrieve all chunks belonging to a prescription project.

        Args:
            project_id: String representation of the integer project_id.

        Returns:
            {
                "medicines": list[dict],   # one dict per medicine chunk's metadata
                "ocr_text": str,           # concatenated chunk texts
            }
        """
        try:
            pid = int(project_id)
        except (ValueError, TypeError):
            logger.warning("[PrescriptionDBService] Invalid project_id: %r", project_id)
            return {"medicines": [], "ocr_text": ""}

        try:
            async with self._db() as session:
                result = await session.execute(
                    select(dataChunk)
                    .where(dataChunk.chunk_project_id == pid)
                    .order_by(dataChunk.chunk_order)
                    .limit(50)
                )
                chunks = result.scalars().all()

            medicines = [
                c.chunk_metadata
                for c in chunks
                if c.chunk_metadata and c.chunk_metadata.get("source") == "prescription_ocr"
            ]
            ocr_text = " ".join(c.chunk_text for c in chunks if c.chunk_text)

            logger.info(
                "[PrescriptionDBService] project_id=%d: %d chunks, %d medicines",
                pid, len(chunks), len(medicines),
            )
            return {"medicines": medicines, "ocr_text": ocr_text}

        except Exception as e:
            logger.error("[PrescriptionDBService] DB fetch failed for project_id=%r: %s", project_id, e)
            return {"medicines": [], "ocr_text": ""}
