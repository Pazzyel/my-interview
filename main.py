import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from modules.resume.router import resume_router
from modules.knowledgebase.router import knowledgebase_router
from modules.knowledgebase.router import rag_chat_router
from common.exceptions import BusinessException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Resume Analysis Service Migration", version="1.0")

app.include_router(resume_router.router)
app.include_router(knowledgebase_router.router)
app.include_router(rag_chat_router.router)

@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    logger.error(f"Business error occurred: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=400,
        content={
            "code": 400,
            "message": exc.message,
            "data": None
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error occurred: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal Server Error",
            "data": None
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
