import os
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from backend.api.heartbeat import router as heartbeat_router
from backend.api.nl_sql import router as nl_sql_router




# ---------- PATHS ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_DB_PATH = os.path.join(BASE_DIR, "..", "vectorstore")

# ---------- APP ----------
app = FastAPI()
app.include_router(heartbeat_router)
app.include_router(nl_sql_router)
# ---------- INPUT ----------
class Question(BaseModel):
    question: str


# ---------- LOAD VECTOR DB ----------
print("Loading vector database...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vector_db = FAISS.load_local(
    VECTOR_DB_PATH,
    embeddings,
    allow_dangerous_deserialization=True
)


# ---------- OLLAMA CALL ----------
def call_ollama(prompt: str) -> str:
    url = "http://localhost:11434/api/chat"

    payload = {
        "model": "qwen2.5:3b",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    try:
        r = requests.post(url, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"]
    except Exception as e:
        return f"Ollama chat failed: {e}"




# ---------- API ----------
@app.post("/ask")
def ask(payload: Question):
    query = payload.question

    # 1) Retrieve
    docs = vector_db.similarity_search(query, k=2)
    context = "\n".join(d.page_content for d in docs)

    # 2) Prompt (hallucination-safe)
    prompt = f"""
You are an internal company assistant.
Answer ONLY from the context below.
If the answer is not present, say: "Information not available in documents."

Context:
{context}

Question:
{query}

"""

    # 3) LLM
    answer = call_ollama(prompt)

    return {
        "question": query,
        "answer": answer.strip()
    }
