from fastapi.testclient import TestClient
from main import app
import sys
import io
import asyncio
from infrastructure.database.connection import get_async_session
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from infrastructure.database.models import Base

# Setup test DB
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    future=True
)

test_async_session_factory = async_sessionmaker(
    test_engine, expire_on_commit=False, class_=AsyncSession
)

async def override_get_async_session() -> AsyncSession: # type: ignore
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with test_async_session_factory() as session:
        yield session

app.dependency_overrides[get_async_session] = override_get_async_session

client = TestClient(app)

def test_health():
    response = client.get("/api/resumes/health")
    print("Health check response:", response.json())
    assert response.status_code == 200

def test_upload():
    # Create a dummy file
    file_content = b"Dummy resume content PDF"
    file = io.BytesIO(file_content)
    
    response = client.post(
        "/api/resumes/upload",
        files={"file": ("resume.pdf", file, "application/pdf")}
    )
    print("Upload response:", response.json())
    assert response.status_code == 200

if __name__ == "__main__":
    try:
        test_health()
        test_upload()
        print("All tests passed!")
    except Exception as e:
        print("Tests failed:", str(e))
        sys.exit(1)
