import os
import snowflake.connector
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# LangChain & Redis
from langchain_redis import RedisVectorStore, RedisConfig
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import ConfluenceLoader, GitLoader
#from langchain_community.document_loaders.github import GithubLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from sentence_transformers import CrossEncoder

app = FastAPI()
#embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key="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")
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-base-en-v1.5",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={"normalize_embeddings": True} # Change to 'cuda' if you have an NVIDIA GPU
)
# --- REDIS SETUP ---
redis_config = RedisConfig(
    index_name="bofa_enterprise_catalog",
    redis_url="redis://localhost:6379",
    distance_metric="COSINE", 
    embedding_dimensions=768, # 
    indexing_algorithm="FLAT", # Simplest for MVP
    metadata_schema=[
        {"name": "source_type", "type": "tag"},
        {"name": "title", "type": "text"}
    ]
)
vector_store = RedisVectorStore(embeddings, config=redis_config)

from langchain_groq import ChatGroq
from langchain_classic.chains import RetrievalQA

llm = ChatGroq(
    groq_api_key="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",
    model_name="llama-3.3-70b-versatile",
    temperature=0
)



prompt = ChatPromptTemplate.from_template("""
You are a Credit Union Enterprise Data Catalog Assistant.

Use ONLY the provided context.

You help with:

• Tables
• Columns
• Lineage
• SQL
• Confluence documentation
• Application architeacture, overview and contact
• Population logic and details of the mentioned table in stg, core and mart layers


Rules:

If the user asks about a specific table, column, lineage, SQL, or anything else, you should:
1. Search the context for relevant information.
2. If you find relevant information, use it to answer the question.
3. If you don't find relevant information, say "I don't know based on the provided context.
                                          
If the user asks about the architecture of the application, refer to the confluence source_type and retrieve the details about the architecture.
                                          
If the user asks about population logic of any table or column in stg, core and mart layer, refer to confluence source_type and github source_type and fetch the required information.

If the user asks on description, purpose of tables or description, datatypes of columns, refer to tables_info, columns_info section in snowflake source_type and fetch the required information.

If the user asks about lineage, refer to lineage_info section in snowflake source_type and fetch the required information and if possible refer to the corresponding population logic in the sqls in gitbub source_type. 

Context:
{context}

Question:
{question}

Answer:
""")

reranker = CrossEncoder('BAAI/bge-reranker-base')

# --- CUSTOM SNOWFLAKE LOADER (3.13 FIX) ---
def get_snowflake_docs():
    docs = []
    ctx = snowflake.connector.connect(
        user='DW66307',
        password='Appaswamy@1007',
        account='JCTDKBZ-DW66307',
        warehouse='CU_WH',
        database='CU_DB',
        schema='METADATA'
    )
    
    # We consolidate your Lineage, Column, and Table info into one query or multiple
    queries = {
        "lineage": "SELECT table_name, lineage_path FROM lineage_table",
        "columns": "SELECT table_name, column_name, data_type FROM columns_table",
        "ddls": "SELECT table_name, ddl_text FROM ddl_metadata"
    }
    
    try:
        cur = ctx.cursor()
        table_info = """SELECT table_name, layer, purpose, description, contents 
        FROM tables_info"""
        source_tag = "table_details"
        cur.execute(table_info)
        for row in cur:
        # Format: "Table: X | Info: Y"
            content = f"""Source: Snowflake
            Type: {source_tag}
            Details: 
            Table_name - {row[0]}, 
            Layer - {row[1]}, 
            Purpose - {row[2]}, 
            Description - {row[3]}, 
            Contents - {row[4]}"""
            docs.append(Document(
                page_content=content,
                    metadata={
                        "source_type": f"snowflake_{source_tag}",
                        "title": f"Snowflake: Details of table {row[0]} in the layer {row[1]}"
                    }
                ))
        
        column_info = """SELECT t.table_name, c.column_name, c.data_type, c.description
        FROM columns_info c
        INNER JOIN tables_info t ON c.table_id = t.table_id
        ORDER BY t.table_id, c.column_id"""
        source_tag = "column_details"
        cur.execute(column_info)
        for row in cur:
        # Format: "Table: X | Info: Y"
            content = f"""Source: Snowflake
            Type: {source_tag}
            Details: 
            Table Name - {row[0]}, 
            Column Name - {row[1]}, 
            Data Type - {row[2]}, 
            Description - {row[3]}"""
            
            docs.append(Document(
                page_content=content,
                    metadata={
                        "source_type": f"snowflake_{source_tag}",
                        "title": f"Snowflake: Details of column {row[1]} in table {row[0]}"
                    }
                ))
        
        lineage_info = """SELECT source_table_name, source_layer, target_table_name, target_layer, link_type
        FROM lineage_info"""
        source_tag = "lineage_details"
        cur.execute(lineage_info)
        for row in cur:
        # Format: "Table: X | Info: Y"
            content = f"""Source: Snowflake
            Type: {source_tag}
            Details: 
            Source Table - {row[0]}, 
            Source Layer - {row[1]}, 
            Target Table - {row[2]}, 
            Target Layer - {row[3]}, 
            Link Type - {row[4]}"""
            docs.append(Document(
                page_content=content,
                    metadata={
                        "source_type": f"snowflake_{source_tag}",
                        "title": f"Snowflake: Details of lineage from {row[0]} to {row[2]}"
                    }
                ))

        

    finally:
        ctx.close()
    return docs

# --- UNIFIED INGESTION ---
@app.post("/ingest")
async def run_ingestion():
    '''global vector_store 
    try:
        vector_store.drop_index(delete_documents=True)
        print("Old Redis index deleted successfully")
    except Exception as e:
        print("No existing index or already deleted:", str(e))
    
    vector_store = RedisVectorStore(embeddings, config=redis_config)'''
    all_docs = []

    # 1. Confluence
    conf_loader = ConfluenceLoader(url="https://abiramisivakumaran.atlassian.net/wiki", space_key="~71202085ca88732ba2404699a21afcc4c0dee7",
                                   api_key="ATATT3xFfGF05Bn-OViz1tAL9Atsh1S8LCVHfx-Y9HJ-MbdHWt6kN5cXfnM_3I1meXqaDYOx6Q6a_ualACL4MziAeXPgEEdVrXzxHKsHgxYCX9lRt3AtaiyK4rUa3pIkL5lkK8ua3D1YO6BZldgC42LrxM-UWXVB-hIuuPFAr9KOS0nyRMhu8Yg=7A951E20",
                                   username="abiramisivakumaran7@gmail.com",
                                   cloud=True,
                                   limit=1000,
                                   max_pages=1000)
    conf_docs = conf_loader.load()
    print("Confluence docs:", len(conf_docs))
    for d in conf_docs: d.metadata.update({"source_type": "confluence"})
    all_docs.extend(conf_docs)

    # 2. GitHub (DDLs/SQL)
    gh_loader = GitLoader(
        repo_path=r"C:\Users\Abirami\Documents\credit-union-analytics-platform",
        #access_token="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",
        branch="main"
    )
    
    gh_docs = gh_loader.load()
    print("Github docs:", len(gh_docs))
    for d in gh_docs:
        d.metadata.update({
            "source_type": "github",
            "title": f"SQL: {os.path.basename(d.metadata['source'])}"
        })
    all_docs.extend(gh_docs)

    snowflake_docs = get_snowflake_docs()
    print("Snowflake docs:", len(snowflake_docs))
    # 3. Snowflake (Using our 3.13 compatible bridge)
    all_docs.extend(snowflake_docs)

    all_docs_r = [d for d in all_docs if d.page_content.strip()]

    # Add to Redis
    vector_store.add_documents(all_docs_r)
    return {"message": f"Successfully ingested {len(all_docs_r)} documents to Redis."}

# --- API QUERY ---
class Query(BaseModel):
    text: str

@app.post("/ask")
async def ask(query: Query):
    # 1. Get 30 docs instead of 15 (Initial wide net)
    initial_docs = vector_store.similarity_search(query.text, k=30)
    
    # 2. Rerank them
    pairs = [[query.text, d.page_content] for d in initial_docs]
    scores = reranker.predict(pairs)
    
    # 3. Zip and Sort by score
    scored_docs = sorted(zip(scores, initial_docs), key=lambda x: x[0], reverse=True)
    
    # 4. Take only the top 5 high-confidence docs for the LLM
    top_docs = [doc for score, doc in scored_docs[:5]]

    # Step 2: Combine context
    context = "\n\n".join([d.page_content for d in top_docs])

    # Step 3: Create prompt
    messages = prompt.format_messages(
        context=context,
        question=query.text
    )

    # Step 4: Call LLM
    response = llm.invoke(messages)

    # Step 5: Return answer
    return {
        "answer": response.content,
        "sources": [
            {
                "title": d.metadata.get("title"),
                "source": d.metadata.get("source"),
                "type": d.metadata.get("source_type")
            }
            for d in top_docs
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)