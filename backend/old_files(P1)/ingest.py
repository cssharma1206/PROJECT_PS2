import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "..", "data")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "..", "vectorstore")



def load_documents():
    documents = []

    for filename in os.listdir(DATA_PATH):
        if filename.endswith(".txt"):
            filepath = os.path.join(DATA_PATH, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
                documents.append(text)

    return documents


def create_vector_db():
    print("Loading documents...")
    docs = load_documents()

    print("Splitting text into chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=20
    )

    split_docs = []
    for doc in docs:
        chunks = splitter.split_text(doc)
        split_docs.extend(chunks)

    print("Creating embeddings...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    print("Building FAISS vector database...")
    vector_db = FAISS.from_texts(split_docs, embeddings)

    print("Saving vector database to disk...")
    vector_db.save_local(VECTOR_DB_PATH)

    print("Vector database created successfully!")


if __name__ == "__main__":
    create_vector_db()