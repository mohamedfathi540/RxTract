# SRC/Services/RAGService.py
"""
RAGService — thin async wrapper around NLPController for agent tool use.

The agent tools need a simple `search(query, project_id?)` interface.
This service proxies to the existing NLPController without duplicating
the vector search implementation.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("uvicorn.error")


class RAGService:
    """
    Wraps NLPController to provide a simple async search interface
    suitable for injection into PharmacyAgentTools.

    Args:
        nlp_controller: An NLPController instance (constructed at startup).
        db_client:      The app-level AsyncSession factory — used to look up
                        Project objects when a project_id is provided.
    """

    def __init__(self, nlp_controller: Any, db_client: Any):
        self._nlp = nlp_controller
        self._db  = db_client

    async def search(self, query: str, project_id: Optional[int] = None) -> str:
        """
        Search the vector DB for relevant medical context.

        If project_id is provided, the search is scoped to that project's
        collection (prescription-specific RAG).  Otherwise it searches the
        global medical knowledge base.

        Args:
            query:      The medical search query.
            project_id: Optional integer project ID to scope the search.

        Returns:
            Concatenated retrieved text, or an empty string if nothing found.
        """
        try:
            if project_id is not None:
                # Scoped search: look up the Project object, then RAG over its chunks
                from sqlalchemy.future import select as sa_select
                from Models.DB_Schemes.minirag.Schemes.Project import Project

                async with self._db() as session:
                    result = await session.execute(
                        sa_select(Project).where(Project.project_id == project_id)
                    )
                    project = result.scalar_one_or_none()

                if project is None:
                    logger.warning("[RAGService] Project %d not found", project_id)
                    return ""

                answer, _, _ = await self._nlp.answer_prescription_question(
                    project=project,
                    query=query,
                    limit=5,
                )
                return answer or ""

            else:
                # Global search: use vector DB directly without project scope
                docs = await self._nlp.search_vector_db_collection(
                    project=None, query=query, limit=5
                )
                if not docs:
                    return ""
                return "\n".join(
                    d.text for d in docs if hasattr(d, "text") and d.text
                )

        except Exception as e:
            logger.error("[RAGService] search failed (project_id=%s): %s", project_id, e)
            return ""
