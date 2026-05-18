from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()

try:
    engine = create_engine(os.getenv("DATABASE_URL"))
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Kết nối thành công!", result.scalar())
except Exception as e:
    print("Kết nối thất bại:", e)
    
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()