import os
import fitz
import shutil
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from ai_service.rag import query_docs, add_pdf_text, delete_pdf_chunks
from pydantic import BaseModel
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from config_db import SessionLocal, engine
from models import Base, Message, Conversation
from sqlalchemy.orm import Session

load_dotenv()

Base.metadata.create_all(bind=engine)

openai_client = OpenAI(base_url=os.getenv("BASE_URL"), api_key=os.getenv("API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    conversation_id: int
    question: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "API is running"}

@app.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):

    user_msg = Message(
        conversation_id=req.conversation_id,
        role="user",
        content=req.question
    )

    db.add(user_msg)

    conversation = db.query(Conversation).filter(
        Conversation.id == req.conversation_id
    ).first()

    if conversation and conversation.title == "New Chat":
        conversation.title = req.question[:20]

    context = query_docs(req.question)
    print("CONTEXT:", context)
    history = (
        db.query(Message)
        .filter(Message.conversation_id == req.conversation_id)
        .order_by(Message.id.asc())
        .all()
    )

    chat_history = [
        {
            "role": msg.role,
            "content": msg.content
        }
        for msg in history[-10:]
    ]

    system_prompt = """
        Bạn là AI Assistant chuyên hỗ trợ người dùng.

        QUY TẮC BẮT BUỘC:
        - CONTEXT được trích xuất từ các file PDF, mỗi đoạn có nhãn [FILE: tên_file]
        - Nếu CONTEXT có thông tin liên quan:
        + Ưu tiên dùng CONTEXT, trích đúng nội dung
        + PHẢI ghi rõ nguồn: "Theo file **tên_file**,..." hoặc cuối câu trả lời ghi "(Nguồn: tên_file)"
        + Không tự diễn giải sai nội dung
        - Nếu CONTEXT không có thông tin liên quan hoặc rỗng:
        + Được dùng kiến thức chung
        + PHẢI nói rõ: "Thông tin này không có trong tài liệu đã upload. Dựa trên kiến thức chung:..."
        - Không tự thêm thông tin lịch sử
        - Nếu không chắc chắn hãy nói rõ
        - Trả lời bằng markdown đẹp, rõ ràng và chính xác
        - Với code phải có comment giải thích
        """

    user_prompt = f"""
    === CONTEXT ===
    {context}

    === USER QUESTION ===
    {req.question}
    """

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    messages.extend(chat_history)

    messages.append({
        "role": "user",
        "content": user_prompt
    })

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3
    )

    answer = response.choices[0].message.content

    ai_msg = Message(
        conversation_id=req.conversation_id,
        role="assistant",
        content=answer
    )

    db.add(ai_msg)

    db.commit()

    return {"answer": answer}

@app.post("/conversations")
def create_conversation(db: Session = Depends(get_db)):
    conv = Conversation(title="New Chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return conv

@app.get("/conversations")
def get_conversations(db: Session = Depends(get_db)):
    return db.query(Conversation).all()

@app.get("/conversations/{id}/messages")
def get_messages(id: int, db: Session = Depends(get_db)):
    return db.query(Message).filter(Message.conversation_id == id).all()

@app.delete("/conversations/{id}")
def delete_conversation(id: int, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.query(Message).filter(Message.conversation_id == id).delete()
    db.delete(conv)
    db.commit()
    return {"message": "Deleted"}

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
     # Validate file
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Chỉ hỗ trợ file PDF"
        )

    # Tạo thư mục uploads nếu chưa có
    os.makedirs("uploads", exist_ok=True)

    # Đường dẫn file
    filename = os.path.basename(file.filename)
    file_path = f"uploads/{filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()

          # Thêm log này để kiểm tra
        print("EXTRACTED TEXT SAMPLE:", text[:1000])
        print("TOTAL LENGTH:", len(text))

    except Exception as e:
         if os.path.exists(file_path):
            os.remove(file_path)
    
         raise HTTPException(
            status_code=400,
            detail=f"Lỗi đọc PDF: {str(e)}"
        )

    # Validate text
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="PDF không có nội dung"
        )

    # Thêm vào vector DB
    add_pdf_text(
        text=text,
        file_name=filename
    )

    return {
        "message": "Upload thành công",
        "file": filename,
        "preview": text[:500]
    }


class DeleteFileRequest(BaseModel):
    filename: str

@app.post("/delete_file")
def delete_file(req: DeleteFileRequest):
    uploads_dir = "uploads"
    filename = os.path.basename(req.filename)
    file_path = os.path.join(uploads_dir, filename)

    # 1. Xóa khỏi ChromaDB trước
    try:
        delete_pdf_chunks(filename)
        print(f"Deleted chunks of {filename} from ChromaDB")
    except Exception as e:
        print(f"Lỗi xóa ChromaDB: {e}")

    # 2. Xóa file vật lý
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi xóa file: {str(e)}")

    return {"message": "File deleted"}