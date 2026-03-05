from .BaseController import basecontroller
from .ProjectController import projectcontroller
from Models.DB_Schemes import Project , dataChunk , RetrivedDocument
from fastapi import UploadFile
from Models import ResponseSignal
import re
import os
from typing import List
from Stores.LLM.LLMEnums import DocumentTypeEnum
from Helpers.Config import get_settings
import json
from Utils.language_detect import detect_query_language




class NLPController (basecontroller) : 

    def __init__(self ,genration_client ,embedding_client ,vectordb_client,template_parser) :
        super().__init__()
        self.genration_client = genration_client
        self.embedding_client = embedding_client
        self.vectordb_client = vectordb_client  
        self.template_parser = template_parser


    def create_collection_name (self , project_id  : str) :
        return f"collection_{self.vectordb_client.default_vector_size}_{project_id}".strip()


    async def reset_vector_db_collection (self , project : Project) :
        collection_name = self.create_collection_name(project_id = project.project_id)
        return await self.vectordb_client.delete_collection(collection_name = collection_name)

    async def get_vector_collection_info ( self , project : Project) :
        collection_name = self.create_collection_name(project_id = project.project_id)
        collection_info = await self.vectordb_client.get_collection_info(collection_name = collection_name)

        return json.loads(
                json.dumps(collection_info,default=lambda x: x.__dict__)
        )
       

    async def index_into_vector_db ( self, project : Project , chunks : list [dataChunk] , 
                                chunks_ids: List[int],do_reset : bool = False) :
        
        collection_name = self.create_collection_name(project_id = project.project_id)

        texts = [c.chunk_text for c in chunks]
        metadata = [c.chunk_metadata for c in chunks]
        
        try:
            vectors = self.embedding_client.embed_text(text = texts ,document_type = DocumentTypeEnum.DOCUMENT.value )
        except Exception as e:
            return False, str(e)

        if not vectors:
            return False, "Failed to generate embeddings"

        _ = await self.vectordb_client.create_collection(collection_name = collection_name , do_reset = do_reset ,
                                                    embedding_size  = self.embedding_client.embedding_size)

        _ = await self.vectordb_client.insert_many(collection_name = collection_name , 
                                            texts = texts , vectors = vectors , 
                                            metadata = metadata,
                                            record_ids = chunks_ids)

        return True, "Success"

    async def search_vector_db_collection(self, project: Project, text: str, limit: int = 5):
        query_vector = None
        collection_name = self.create_collection_name(project_id=project.project_id)

        vector = self.embedding_client.embed_text(text=text, document_type=DocumentTypeEnum.QUERY.value)

        if not vector or len(vector) == 0:
            return False

        if isinstance(vector, list) and len(vector) > 0:
            query_vector = vector[0]

        if not query_vector:
            return False

        settings = get_settings()
        hybrid_enabled = getattr(settings, "HYBRID_SEARCH_ENABLED", False)
        hybrid_alpha = getattr(settings, "HYBRID_SEARCH_ALPHA", 0.6)
        if hybrid_enabled:
            from Stores.Sparse import BM25Index
            candidate_mult = 2
            dense_limit = max(limit * candidate_mult, 10)
            results = await self.vectordb_client.search_by_vector(
                collection_name=collection_name,
                vector=query_vector,
                limit=dense_limit,
            )
            if not results or len(results) == 0:
                return False
            bm25_hits = BM25Index.search(project.project_id, text, top_k=dense_limit)
            bm25_by_id = {cid: score for cid, score in bm25_hits}
            bm25_max = max(bm25_by_id.values()) if bm25_by_id else 1.0
            combined = []
            for doc in results:
                cid = getattr(doc, "chunk_id", None)
                bm25_norm = (bm25_by_id.get(cid, 0) / bm25_max) if bm25_max > 0 else 0.0
                score = hybrid_alpha * doc.score + (1.0 - hybrid_alpha) * bm25_norm
                combined.append(
                    RetrivedDocument(
                        text=doc.text,
                        score=score,
                        metadata=getattr(doc, "metadata", None),
                        chunk_id=cid,
                    )
                )
            combined.sort(key=lambda d: d.score, reverse=True)
            return combined[:limit]

        results = await self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=query_vector,
            limit=limit,
        )

        if not results or len(results) == 0:
            return False

        return results


    async def answer_rag_question (self , project : Project , query : str ,limit : int = 5) :


        answer, full_prompt ,chat_history = None , None , None

        #step 1 : retrive related document :
        retrieved_documents = await self.search_vector_db_collection(project = project , text = query , limit = limit)

        if not retrieved_documents or len(retrieved_documents) == 0 :
            return answer, full_prompt ,chat_history

        #step 2 : constract LLM prompt (include source metadata when available)
        system_prompt = self.template_parser.get("rag", "system_prompt", {
        "response_language": detect_query_language(query)
    })
        doc_lines = []
        for idx, doc in enumerate(retrieved_documents):
            chunk_text = self.genration_client.process_text(doc.text)
            if getattr(doc, "metadata", None) and isinstance(doc.metadata, dict):
                parts = []
                if doc.metadata.get("source"):
                    parts.append(doc.metadata["source"])
                if doc.metadata.get("page") is not None:
                    parts.append(f"page {doc.metadata['page']}")
                if doc.metadata.get("domain"):
                    parts.append(f"domain: {doc.metadata['domain']}")
                if parts:
                    chunk_text = "From: " + ", ".join(parts) + "\n" + chunk_text
            doc_lines.append(
                self.template_parser.get("rag", "document_prompt", {"doc_num": idx + 1, "chunk_text": chunk_text})
            )
        document_prompt = "\n".join(doc_lines)

        footer_prompt = self.template_parser.get("rag", "footer_prompt",{
            "query" : query
        })

        chat_history = [
            self.genration_client.construct_prompt(
                prompt = system_prompt,
                role = self.genration_client.enums.SYSTEM.value
            )
        ]

        full_prompt = "\n\n".join([document_prompt , footer_prompt])

        answer = self.genration_client.genrate_text(
            prompt = full_prompt,
            chat_history = chat_history
        )

        return answer, full_prompt ,chat_history

    async def answer_prescription_question(self, project: Project, query: str, limit: int = 5):
        """
        Like answer_rag_question but uses the prescription-specific prompt template.
        This allows the LLM to use its pharmaceutical knowledge alongside the
        retrieved prescription data.
        """
        answer, full_prompt, chat_history = None, None, None

        # Step 1: retrieve related medicine chunks
        retrieved_documents = await self.search_vector_db_collection(
            project=project, text=query, limit=limit
        )

        if not retrieved_documents or len(retrieved_documents) == 0:
            return answer, full_prompt, chat_history

        from Utils.MedicineMatcher import MedicineMatcher
        matcher = MedicineMatcher()
        
        # Step 2: construct LLM prompt using prescription-specific template
        system_prompt = self.template_parser.get("prescription_rag", "system_prompt", {
        "response_language": detect_query_language(query)
    })
        doc_lines = []
        
        # Track ingredients to find alternatives
        ingredients_found = set()
        
        for idx, doc in enumerate(retrieved_documents):
            chunk_text = self.genration_client.process_text(doc.text)
            # Include medicine metadata for richer context
            if getattr(doc, "metadata", None) and isinstance(doc.metadata, dict):
                parts = []
                med_name = doc.metadata.get("medicine_name")
                if med_name:
                    parts.append(f"Medicine: {med_name}")
                
                active_ing = doc.metadata.get("active_ingredient")
                if active_ing:
                    parts.append(f"Active Ingredient: {active_ing}")
                    if active_ing.lower() != "unknown":
                        ingredients_found.add((med_name, active_ing))
                
                if parts:
                    chunk_text = " | ".join(parts) + "\n" + chunk_text
            
            doc_lines.append(
                self.template_parser.get("prescription_rag", "document_prompt", {
                    "doc_num": idx + 1, "chunk_text": chunk_text
                })
            )

        # Step 2.5: Find real alternatives for found ingredients
        if ingredients_found:
            alt_lines = ["\n### REAL DATABASE ALTERNATIVES (RXTRACT DATABASE):"]
            for med_name, ing in ingredients_found:
                db_alts = matcher.find_medicines_by_ingredient(ing, limit=5)
                # Filter out the current medicine if it's in the list
                db_alts = [a for a in db_alts if med_name.lower() not in a.lower()]
                
                if db_alts:
                    alt_lines.append(f"- **{med_name}** ({ing}) → REAL alternatives in stock: {', '.join(db_alts)}")
            
            if len(alt_lines) > 1:
                # Add to the document prompt context
                doc_lines.append("\n".join(alt_lines))

        document_prompt = "\n".join(doc_lines)

        footer_prompt = self.template_parser.get("prescription_rag", "footer_prompt", {
            "query": query
        })

        chat_history = [
            self.genration_client.construct_prompt(
                prompt=system_prompt,
                role=self.genration_client.enums.SYSTEM.value
            )
        ]

        full_prompt = "\n\n".join([document_prompt, footer_prompt])

        answer = self.genration_client.genrate_text(
            prompt=full_prompt,
            chat_history=chat_history
        )

        return answer, full_prompt, chat_history