import os
import re
import uuid
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session
from config_db import SessionLocal
from models import DocumentChunk

load_dotenv()

openai_client = OpenAI(
    api_key=os.getenv("API_KEY_EMBEDDING"),
    base_url=os.getenv("BASE_URL")
)

# ── Embeddings ──────────────────────────────────────────────────────────────

def get_openai_embeddings(texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return [item.embedding for item in response.data]

# ── Cosine similarity ────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / norm) if norm > 0 else 0.0

# ── CRUD ─────────────────────────────────────────────────────────────────────

def delete_pdf_chunks(file_name: str):
    db: Session = SessionLocal()
    try:
        deleted = db.query(DocumentChunk).filter(
            DocumentChunk.source == file_name
        ).delete()
        db.commit()
        print(f"Deleted {deleted} chunks of '{file_name}' from MySQL")
    except Exception as e:
        db.rollback()
        print(f"Lỗi delete_pdf_chunks: {e}")
    finally:
        db.close()

def query_docs(question: str) -> str:
    query_embedding = get_openai_embeddings([question])[0]

    db: Session = SessionLocal()
    try:
        # Lấy tất cả chunks (với dữ liệu lớn nên thêm pagination hoặc ANN index)
        chunks = db.query(DocumentChunk).all()
    finally:
        db.close()

    SIMILARITY_THRESHOLD = 0.3  # cosine: càng cao càng giống (ngược với distance)
    scored = []

    for chunk in chunks:
        sim = cosine_similarity(query_embedding, chunk.embedding)
        if sim < SIMILARITY_THRESHOLD:
            continue

        # Bonus nếu chunk chứa keyword từ câu hỏi
        keywords = question.lower().split()
        keyword_hits = sum(1 for kw in keywords if kw in chunk.content.lower())
        score = sim + (keyword_hits * 0.05)  # càng cao càng tốt

        header = f"[FILE: {chunk.source}]"
        if chunk.chapter and chunk.chapter not in ["unknown", "MỤC LỤC"]:
            header += f" [{chunk.chapter}]"

        scored.append((score, f"{header}\n{chunk.content}"))

    scored.sort(key=lambda x: x[0], reverse=True)
    # Giới hạn tổng số từ (tokens) context trả về, ví dụ 2000 từ
    MAX_WORDS = 2000
    contexts = []
    total_words = 0
    for _, text in scored:
        num_words = len(text.split())
        if total_words + num_words > MAX_WORDS:
            break
        contexts.append(text)
        total_words += num_words
    print(f"[RAG] Tổng số từ context trả về: {total_words}")
    return "\n\n".join(contexts)

# ── Chapter extraction (giữ nguyên logic cũ) ─────────────────────────────────

def extract_chapters(text: str) -> list[dict]:
    lines = text.split('\n')
    chapter_pattern = re.compile(
        r'^(CHƯƠNG|Chương)\s*(\d+|I{1,3}V?|VI{0,3}|nhập môn|mở đầu|kết luận)',
        re.IGNORECASE
    )

    chapters = []
    current_title = "Mở đầu"
    current_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if chapter_pattern.match(line):
            if current_lines:
                chapters.append({"title": current_title, "content": '\n'.join(current_lines)})
            full_title = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line or chapter_pattern.match(next_line) or len(next_line) > 200:
                    break
                if next_line.isupper() or len(next_line) < 100:
                    full_title += " " + next_line
                    j += 1
                else:
                    break
            i = j
            current_title = full_title
            current_lines = []
        else:
            if line:
                current_lines.append(line)
            i += 1

    if current_lines:
        chapters.append({"title": current_title, "content": '\n'.join(current_lines)})

    return chapters

# ── Ingest ────────────────────────────────────────────────────────────────────

def add_document_text(text: str, file_name: str):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chapters = extract_chapters(text)

    print(f"Detected {len(chapters)} chapters:")
    for c in chapters:
        print(f"  - {c['title'][:80]}")

    all_chunks: list[str] = []
    all_metadatas: list[dict] = []

    if len(chapters) > 1:
        for chapter in chapters:
            for chunk in splitter.split_text(chapter["content"]):
                all_chunks.append(chunk)
                all_metadatas.append({"source": file_name, "chapter": chapter["title"]})

        chapter_index = "DANH SÁCH CHƯƠNG TRONG TÀI LIỆU:\n" + "\n".join(
            [f"- {c['title']}" for c in chapters]
        )
        all_chunks.append(chapter_index)
        all_metadatas.append({"source": file_name, "chapter": "MỤC LỤC"})
    else:
        print("Không detect được chương, chunk bình thường")
        for chunk in splitter.split_text(text):
            all_chunks.append(chunk)
            all_metadatas.append({"source": file_name, "chapter": "unknown"})

    if not all_chunks:
        return

    # Embed theo batch để tránh timeout
    BATCH_SIZE = 50
    all_embeddings = []
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        all_embeddings.extend(get_openai_embeddings(batch))

    db: Session = SessionLocal()
    try:
        records = [
            DocumentChunk(
                id=str(uuid.uuid4()),
                source=meta["source"],
                chapter=meta["chapter"],
                content=chunk,
                embedding=emb  # SQLAlchemy JSON sẽ tự serialize
            )
            for chunk, meta, emb in zip(all_chunks, all_metadatas, all_embeddings)
        ]
        db.bulk_save_objects(records)
        db.commit()
        print(f"Inserted {len(records)} chunks into MySQL")
    except Exception as e:
        db.rollback()
        print(f"Lỗi insert chunks: {e}")
        raise
    finally:
        db.close()