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
from Models.DB_Schemes.minirag.Schemes.Project import Project
from Models.DB_Schemes.minirag.Schemes.Asset import Asset
import uuid

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
                "image_url": str | None,   # URL to the persistent image file
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

                # Fetch Asset to retrieve the persistent image URL
                asset_result = await session.execute(
                    select(Asset)
                    .where(Asset.asset_project_id == pid)
                    .where(Asset.asset_type == "prescription")
                    .limit(1)
                )
                asset = asset_result.scalars().first()
                image_url = None
                if asset and asset.asset_config:
                    image_url = asset.asset_config.get("image_url")

            medicines = []
            for c in chunks:
                meta = c.chunk_metadata
                if meta and meta.get("source") == "prescription_ocr":
                    med_data = dict(meta)
                    if "name" not in med_data and "medicine_name" in med_data:
                        med_data["name"] = med_data["medicine_name"]
                    medicines.append(med_data)
            ocr_text = " ".join(c.chunk_text for c in chunks if c.chunk_text)

            logger.info(
                "[PrescriptionDBService] project_id=%d: %d chunks, %d medicines",
                pid, len(chunks), len(medicines),
            )
            return {"medicines": medicines, "ocr_text": ocr_text, "image_url": image_url}

        except Exception as e:
            logger.error("[PrescriptionDBService] DB fetch failed for project_id=%r: %s", project_id, e)
            return {"medicines": [], "ocr_text": "", "image_url": None}

    async def get_history(self, user_id: int) -> list:
        """Return all non-deleted projects that belong to this user."""
        from sqlalchemy import desc
        try:
            async with self._db() as session:
                result = await session.execute(
                    select(Project)
                    .where(Project.user_id == user_id)
                    .where(Project.is_deleted == False)
                    .order_by(desc(Project.update_at))
                    .limit(100)
                )
                projects = result.scalars().all()
                return [
                    {
                        "id": str(p.project_id),
                        "title": p.title,
                        "is_pinned": p.is_pinned,
                        "created_at": p.create_at.isoformat() if p.create_at else None,
                        "updated_at": p.update_at.isoformat() if p.update_at else None,
                        "share_token": p.share_token
                    }
                    for p in projects
                ]
        except Exception as e:
            logger.error("[PrescriptionDBService] get_history failed: %s", e)
            return []

    async def rename_prescription(self, project_id: str, title: str, user_id: int | None = None) -> bool:
        try:
            pid = int(project_id)
            async with self._db() as session:
                query = select(Project).where(Project.project_id == pid)
                if user_id is not None:
                    query = query.where(Project.user_id == user_id)
                result = await session.execute(query)
                project = result.scalars().first()
                if project:
                    project.title = title
                    await session.commit()
                    return True
                return False
        except Exception as e:
            logger.error("[PrescriptionDBService] rename_prescription failed: %s", e)
            return False

    async def toggle_pin(self, project_id: str, user_id: int | None = None) -> bool:
        try:
            pid = int(project_id)
            async with self._db() as session:
                query = select(Project).where(Project.project_id == pid)
                if user_id is not None:
                    query = query.where(Project.user_id == user_id)
                result = await session.execute(query)
                project = result.scalars().first()
                if project:
                    project.is_pinned = not project.is_pinned
                    await session.commit()
                    return project.is_pinned
                return False
        except Exception as e:
            logger.error("[PrescriptionDBService] toggle_pin failed: %s", e)
            return False

    async def soft_delete(self, project_id: str, user_id: int | None = None) -> bool:
        try:
            pid = int(project_id)
            async with self._db() as session:
                query = select(Project).where(Project.project_id == pid)
                if user_id is not None:
                    query = query.where(Project.user_id == user_id)
                result = await session.execute(query)
                project = result.scalars().first()
                if project:
                    project.is_deleted = True
                    await session.commit()
                    return True
                return False
        except Exception as e:
            logger.error("[PrescriptionDBService] soft_delete failed: %s", e)
            return False

    async def generate_share_token(self, project_id: str, user_id: int | None = None) -> str:
        try:
            pid = int(project_id)
            async with self._db() as session:
                query = select(Project).where(Project.project_id == pid)
                if user_id is not None:
                    query = query.where(Project.user_id == user_id)
                result = await session.execute(query)
                project = result.scalars().first()
                if project:
                    if not project.share_token:
                        project.share_token = str(uuid.uuid4())
                        await session.commit()
                    return project.share_token
                return ""
        except Exception as e:
            logger.error("[PrescriptionDBService] generate_share_token failed: %s", e)
            return ""

    async def get_prescription_by_token(self, token: str) -> dict | None:
        try:
            async with self._db() as session:
                result = await session.execute(select(Project).where(Project.share_token == token))
                project = result.scalars().first()
                if project:
                    data = await self.get_prescription(str(project.project_id))
                    data["title"] = project.title
                    return data
                return None
        except Exception as e:
            logger.error("[PrescriptionDBService] get_prescription_by_token failed: %s", e)
            return None
