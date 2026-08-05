import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from common.config import app_config
from common.dependencies import (
    knowledgebase_query_service,
    analyze_message_consumer,
    vectorize_message_consumer,
    interview_agent_service,
    evaluate_message_consumer,
    llm_provider_service,
    analyze_message_producer,
    vectorize_message_producer,
    evaluate_message_producer,
    voice_evaluate_message_producer,
    voice_evaluate_message_consumer,
    voice_evaluation_recovery_service,
    voice_runtime_manager,
    schedule_status_updater,
    question_generation_message_producer,
    question_generation_message_consumer,
    question_generation_recovery_service,
)
from common.exceptions import BusinessException
from modules.interview.router import interview_router
from modules.interview.router import interview_skill_router
from modules.knowledgebase.router import knowledgebase_router, rag_chat_router
from modules.knowledgebase.router import knowledgebase_interview_router
from modules.resume.router import resume_router
from modules.llmprovider.router import llm_provider_router
from modules.voiceinterview.router import rest_router as voice_interview_router
from modules.voiceinterview.router import websocket_router as voice_interview_websocket_router
from modules.interviewschedule.router import interview_schedule_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await llm_provider_service.initialize()
    async with AIOMySQLSaver.from_conn_string(app_config.DB_URI) as checkpointer:
        await checkpointer.setup()
        await knowledgebase_query_service.build_graph(checkpointer)
        await interview_agent_service.build_graph(checkpointer)
        producers = [
            analyze_message_producer,
            vectorize_message_producer,
            evaluate_message_producer,
            voice_evaluate_message_producer,
            question_generation_message_producer,
        ]
        consumers = [
            analyze_message_consumer,
            vectorize_message_consumer,
            evaluate_message_consumer,
            voice_evaluate_message_consumer,
            question_generation_message_consumer,
        ]
        try:
            await asyncio.gather(*(asyncio.to_thread(item.start) for item in producers))
            for consumer in consumers:
                await consumer.start()
            await voice_evaluation_recovery_service.start()
            await schedule_status_updater.start()
            await question_generation_recovery_service.start()
            logging.info("LangGraph Checkpointer 与语音面试任务已就绪")
            yield
        finally:
            await question_generation_recovery_service.shutdown()
            await schedule_status_updater.shutdown()
            await voice_runtime_manager.close_all()
            await voice_evaluation_recovery_service.shutdown()
            for consumer in reversed(consumers):
                await consumer.shutdown()
            await asyncio.gather(
                *(asyncio.to_thread(item.shutdown) for item in reversed(producers)),
                return_exceptions=True,
            )
            logging.info("后台任务与 LangGraph Checkpointer 连接已关闭")

app = FastAPI(title="Resume Analysis Service Migration", version="1.0", lifespan=lifespan)

app.include_router(resume_router.router)
app.include_router(knowledgebase_router.router)
app.include_router(rag_chat_router.router)
app.include_router(knowledgebase_interview_router.router)
app.include_router(interview_router.router)
app.include_router(interview_skill_router.router)
app.include_router(llm_provider_router.router)
app.include_router(voice_interview_router.router)
app.include_router(voice_interview_websocket_router.router)
app.include_router(interview_schedule_router.router)

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

origins = [
    # 如果你还有其他前端地址，可以继续往这里加
    "http://localhost:5173",
]



app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8072, reload=True)
