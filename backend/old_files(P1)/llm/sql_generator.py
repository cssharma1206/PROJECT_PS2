import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:3b"


def generate_sql_from_question(question: str) -> str:
    prompt = f"""
You are a SQL expert.
Given the database table below, generate ONLY a valid SQL Server query.

Table: CommunicationsRequestStatus
Columns:
- Id (int)
- ReferenceApplicationId (int)
- ReferenceVendorId (int)
- Receiver (nvarchar)
- Sender (nvarchar)
- CCData (nvarchar)
- BccData (nvarchar)
- SubmitDate (datetime)
- AttachmentInfo (nvarchar)
- RequestData (nvarchar)
- TrackingId (nvarchar)
- Gu_id (nvarchar)
- LastStatus (nvarchar)
- UpdatedDate (datetime)
- CategoryId (int)

Rules:
- Use SQL Server syntax
- Do NOT explain
- Do NOT add markdown
- Output ONLY SQL

Question:
{question}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()
    sql = response.json()["response"].strip()

# --- SAFETY GUARDS ---
    sql = sql.split(";")[0]  # remove extra text
    if not sql.lower().startswith("select"):
      raise ValueError("Only SELECT queries are allowed")

    return sql
    