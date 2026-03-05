import asyncio
import os
import sys

# Add the SRC directory to the system path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Explicitly load .env file
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    import dotenv
    dotenv.load_dotenv(env_path)

from Helpers.Config import get_settings
from Stores.LLM.LLMProviderFactory import LLMProviderFactory
from Stores.VectorDB.VectorDBProviderFactory import VectorDBProviderFactory
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from Models.Project_Model import projectModel
from Models.Chunk_Model import ChunkModel
from Controllers.NLPController import NLPController
from Stores.LLM.Templates.template_parser import template_parser as TemplateParser

async def main():
    settings = get_settings()

    # Database Setup
    postgres_connection = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DB}"
    db_engine = create_async_engine(postgres_connection)
    db_client = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    # Factory & Client Setup
    llm_factory = LLMProviderFactory(settings)
    vectordb_factory = VectorDBProviderFactory(config=settings, db_client=db_client)

    # Initialize Clients
    try:
        embedding_client = llm_factory.create(provider=settings.EMBEDDING_BACKEND)
        embedding_client.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID, embedding_size=settings.EMBEDDING_SIZE)
        
        # Generation client is needed for NLPController init, though maybe not used for embedding directly
        generation_client = llm_factory.create(provider=settings.GENRATION_BACKEND)
        generation_client.set_genration_model(model_id=settings.GENRATION_MODEL_ID)

        vectordb_client = vectordb_factory.create(provider=settings.VECTORDB_BACKEND)
        await vectordb_client.connect()
        
        template_parser = TemplateParser(language=settings.PRIMARY_LANGUAGE, default_language=settings.DEFUALT_LANGUAGE)

        # Controller
        nlp_controller = NLPController(
            genration_client=generation_client,
            embedding_client=embedding_client,
            vectordb_client=vectordb_client,
            template_parser=template_parser
        )

        # Models
        project_model_instance = await projectModel.create_instance(db_client)
        chunk_model_instance = await ChunkModel.create_instance(db_client)

        # 1. Get all projects
        projects, total_pages = await project_model_instance.get_all_projects(page=1, page_size=1000)
        print(f"Found {len(projects)} projects.")

        for project in projects:
            print(f"Processing Project: {project.project_name} (ID: {project.project_id})")
            
            # 2. Get all chunks for the project
            total_chunks = await chunk_model_instance.get_total_chunks_count(project_id=project.project_id)
            print(f"  - Total chunks: {total_chunks}")
            
            if total_chunks == 0:
                print("  - No chunks to process.")
                continue

            page_size = 100
            total_chunk_pages = (total_chunks + page_size - 1) // page_size

            for page in range(1, total_chunk_pages + 1):
                chunks = await chunk_model_instance.get_project_chunks(project_id=project.project_id, page_no=page, page_size=page_size)
                if not chunks:
                    break
                
                chunk_ids = [c.chunk_id for c in chunks]
                
                print(f"  - Embedding page {page}/{total_chunk_pages} ({len(chunks)} chunks)...")
                
                # 3. Index into Vector DB
                success, msg = await nlp_controller.index_into_vector_db(
                    project=project,
                    chunks=chunks,
                    chunks_ids=chunk_ids,
                    do_reset=False 
                )
                
                if success:
                    print(f"    -> Success")
                else:
                    print(f"    -> FAILED: {msg}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
           await vectordb_client.disconnect()
        except:
           pass
        await db_engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
