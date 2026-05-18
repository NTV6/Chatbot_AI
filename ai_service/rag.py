import os
import re
import uuid
import chromadb
from openai import OpenAI
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(
    name="docs",
    embedding_function=None
)

print("Total chunks:", collection.count())
results = collection.get(limit=5)
for i, (doc, meta) in enumerate(zip(results["documents"], results["metadatas"])):
    print(f"\n--- Chunk {i+1} ---")
    print("Source:", meta.get("source"))
    print("Content:", doc[:200])

openai_client = OpenAI(
    api_key=os.getenv("API_KEY_EMBEDDING"),
    base_url=os.getenv("BASE_URL")
)

def get_openai_embeddings(texts):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )

    return [item.embedding for item in response.data]

def delete_pdf_chunks(file_name: str):
    try:
        # Tìm tất cả chunks có source = file_name
        results = collection.get(
            where={"source": file_name}
        )
        ids = results.get("ids", [])
        
        if ids:
            collection.delete(ids=ids)
            print(f"Deleted {len(ids)} chunks of '{file_name}' from ChromaDB")
        else:
            print(f"Không tìm thấy chunks nào của '{file_name}' trong ChromaDB")
            
    except Exception as e:
        print(f"Lỗi delete_pdf_chunks: {e}")

# rag.py - thêm filter theo keyword
def query_docs(question):
    query_embedding = get_openai_embeddings([question])[0]

    # Lấy nhiều hơn rồi rerank
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=15
    )

    docs = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    DISTANCE_THRESHOLD = 1.4

    scored = []
    for doc, meta, distance in zip(docs, metadatas, distances):
        if distance > DISTANCE_THRESHOLD:
            continue

        # Bonus score nếu chunk chứa keyword từ câu hỏi
        keywords = question.lower().split()
        keyword_hits = sum(1 for kw in keywords if kw in doc.lower())
        
        # Score = distance - bonus (càng thấp càng tốt)
        score = distance - (keyword_hits * 0.05)
        
        source = meta.get("source", "unknown") if meta else "unknown"
        chapter = meta.get("chapter", "") if meta else ""
        
        header = f"[FILE: {source}]"
        if chapter and chapter not in ["unknown", "MỤC LỤC"]:
            header += f" [{chapter}]"
        
        scored.append((score, f"{header}\n{doc}"))

    # Sắp xếp theo score, lấy top 6
    scored.sort(key=lambda x: x[0])
    contexts = [text for _, text in scored[:6]]

    return "\n\n".join(contexts)

def extract_chapters(text):
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
                chapters.append({
                    "title": current_title,
                    "content": '\n'.join(current_lines)
                })
            
            # Lấy tiêu đề đầy đủ: gom tất cả dòng phụ đề liên tiếp
            full_title = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # Dừng nếu: dòng rỗng, hoặc là chương mới, hoặc quá dài (đoạn văn)
                if (not next_line or 
                    chapter_pattern.match(next_line) or 
                    len(next_line) > 200):
                    break
                # Dòng phụ đề thường là CHỮ HOA hoặc ngắn < 100 ký tự
                if next_line.isupper() or len(next_line) < 100:
                    full_title += " " + next_line
                    j += 1
                else:
                    break
            
            i = j  # nhảy qua các dòng phụ đề đã gom
            current_title = full_title
            current_lines = []
        else:
            if line:
                current_lines.append(line)
            i += 1
    
    if current_lines:
        chapters.append({
            "title": current_title,
            "content": '\n'.join(current_lines)
        })
    
    return chapters


def add_pdf_text(text, file_name):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chapters = extract_chapters(text)
    print(f"Detected {len(chapters)} chapters:")
    for c in chapters:
        print(f"  - {c['title'][:80]}")

    all_chunks = []
    all_metadatas = []

    if len(chapters) > 1:
        for chapter in chapters:
            chunks = splitter.split_text(chapter["content"])
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadatas.append({
                    "source": file_name,
                    "chapter": chapter["title"]
                })

        # Chunk index với tiêu đề đầy đủ
        chapter_index = "DANH SÁCH CHƯƠNG TRONG TÀI LIỆU:\n" + "\n".join(
            [f"- {c['title']}" for c in chapters]
        )
        all_chunks.append(chapter_index)
        all_metadatas.append({
            "source": file_name,
            "chapter": "MỤC LỤC"
        })
        print("Chapter index:\n", chapter_index)
    else:
        print("Không detect được chương, chunk bình thường")
        chunks = splitter.split_text(text)
        for chunk in chunks:
            all_chunks.append(chunk)
            all_metadatas.append({"source": file_name, "chapter": "unknown"})

    if not all_chunks:
        return

    embeddings = get_openai_embeddings(all_chunks)
    ids = [str(uuid.uuid4()) for _ in all_chunks]

    collection.upsert(
        documents=all_chunks,
        ids=ids,
        embeddings=embeddings,
        metadatas=all_metadatas
    )

    print(f"Inserted {len(all_chunks)} chunks, {len(chapters)} chapters")