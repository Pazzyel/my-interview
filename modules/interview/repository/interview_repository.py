import json
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import InterviewAnswerORM, InterviewSessionORM
from modules.interview.model.interview_dto import InterviewAnswerDetailDTO, InterviewDetailDTO, InterviewHistoryItemDTO
from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus


class InterviewRepository:
    """
    面试仓储层，负责面试会话与答案的数据库访问。
    Interview repository for interview sessions and answers.
    """

    async def find_by_resume_id(self, db: AsyncSession, resume_id: int) -> list[InterviewSessionEntity]:
        stmt = select(InterviewSessionORM).where(InterviewSessionORM.resume_id == resume_id).order_by(desc(InterviewSessionORM.created_at))
        result = await db.execute(stmt)
        orm_list: list[InterviewSessionORM] = list(result.scalars().all())
        return [self._to_session_entity(item) for item in orm_list]

    async def find_by_session_id(self, db: AsyncSession, session_id: str) -> InterviewSessionEntity | None:
        stmt = select(InterviewSessionORM).where(InterviewSessionORM.session_id == session_id)
        result = await db.execute(stmt)
        orm_obj: InterviewSessionORM | None = result.scalar_one_or_none()
        if orm_obj is None:
            return None
        return self._to_session_entity(orm_obj)

    async def find_detail_by_session_id(self, db: AsyncSession, session_id: str) -> InterviewDetailDTO | None:
        """
        按会话 ID 生成面试详情 DTO（含题目、答案、评估信息）。
        Build interview detail DTO by session ID, including questions, answers, and evaluation fields.
        """
        # 查出会话内容
        stmt = select(InterviewSessionORM).where(InterviewSessionORM.session_id == session_id)
        result = await db.execute(stmt)
        session_orm: InterviewSessionORM | None = result.scalar_one_or_none()
        if session_orm is None:
            return None

        # 查出这轮会话的回答内容
        answer_stmt = (
            select(InterviewAnswerORM)
            .where(InterviewAnswerORM.session_pk_id == session_orm.id)
            .order_by(InterviewAnswerORM.question_index.asc())
        )
        answer_result = await db.execute(answer_stmt)
        answer_orm_list: list[InterviewAnswerORM] = list(answer_result.scalars().all())

        # 组装面试详情DTO
        questions: list[Any] = self._parse_json_array(session_orm.questions_json)
        strengths: list[str] = [str(item) for item in self._parse_json_array(session_orm.strengths_json)]
        improvements: list[str] = [str(item) for item in self._parse_json_array(session_orm.improvements_json)]
        reference_answers: list[Any] = self._parse_json_array(session_orm.reference_answers_json)

        answer_detail_map: dict[int, InterviewAnswerDetailDTO] = {
            answer.question_index: self._to_answer_detail_dto(answer) for answer in answer_orm_list
        }

        answer_details: list[InterviewAnswerDetailDTO] = []
        for item in questions:
            question_index: int = int(item.get("questionIndex", 0)) if isinstance(item, dict) else 0
            if question_index in answer_detail_map:
                answer_details.append(answer_detail_map[question_index])
            elif isinstance(item, dict):
                answer_details.append(
                    InterviewAnswerDetailDTO(
                        questionIndex=question_index,
                        question=item.get("question"),
                        category=item.get("category"),
                        score=int(item.get("score", 0)) if item.get("score") is not None else 0,
                        feedback=item.get("feedback"),
                    )
                )

        for answer_orm in answer_orm_list:
            if answer_orm.question_index not in {item.questionIndex for item in answer_details}:
                answer_details.append(self._to_answer_detail_dto(answer_orm))

        return InterviewDetailDTO(
            id=session_orm.id,
            sessionId=session_orm.session_id,
            totalQuestions=session_orm.total_questions,
            status=session_orm.status.value,
            evaluateStatus=session_orm.evaluate_status,
            evaluateError=session_orm.evaluate_error,
            overallScore=session_orm.overall_score,
            overallFeedback=session_orm.overall_feedback,
            createdAt=session_orm.created_at,
            completedAt=session_orm.completed_at,
            questions=questions,
            strengths=strengths,
            improvements=improvements,
            referenceAnswers=reference_answers,
            answers=sorted(answer_details, key=lambda item: item.questionIndex),
        )

    async def delete_by_session_id(self, db: AsyncSession, session_id: str) -> None:
        session_stmt = select(InterviewSessionORM).where(InterviewSessionORM.session_id == session_id)
        session_result = await db.execute(session_stmt)
        session_orm: InterviewSessionORM | None = session_result.scalar_one_or_none()
        if session_orm is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")

        await db.execute(delete(InterviewSessionORM).where(InterviewSessionORM.id == session_orm.id))

    async def delete_by_resume_id(self, db: AsyncSession, resume_id: int) -> None:
        await db.execute(delete(InterviewSessionORM).where(InterviewSessionORM.resume_id == resume_id))

    async def find_unfinished_by_resume_id(self, db: AsyncSession, resume_id: int) -> InterviewSessionEntity | None:
        stmt = (
            select(InterviewSessionORM)
            .where(InterviewSessionORM.resume_id == resume_id)
            .where(InterviewSessionORM.status.in_(["CREATED", "IN_PROGRESS"]))
            .order_by(desc(InterviewSessionORM.created_at))
            .limit(1)
        )
        result = await db.execute(stmt)
        orm_obj: InterviewSessionORM | None = result.scalar_one_or_none()
        if orm_obj is None:
            return None
        return self._to_session_entity(orm_obj)

    async def count_by_resume_id(self, db: AsyncSession, resume_id: int) -> int:
        stmt = select(InterviewSessionORM.id).where(InterviewSessionORM.resume_id == resume_id)
        result = await db.execute(stmt)
        rows: list[int] = list(result.scalars().all())
        return len(rows)

    async def list_history_by_resume_id(self, db: AsyncSession, resume_id: int) -> list[InterviewHistoryItemDTO]:
        """
        按简历 ID 生成面试历史列表 DTO。
        Build interview history item DTO list by resume ID.
        """
        entities: list[InterviewSessionEntity] = await self.find_by_resume_id(db, resume_id)
        return [
            InterviewHistoryItemDTO(
                sessionId=item.sessionId,
                status=item.status.value,
                overallScore=item.overallScore,
                createdAt=item.createdAt,
                completedAt=item.completedAt,
            )
            for item in entities
        ]

    def _to_session_entity(self, orm_obj: InterviewSessionORM) -> InterviewSessionEntity:
        """
        将会话 ORM 对象转换为纯数据实体。
        Convert interview session ORM object to pure data entity.
        """
        return InterviewSessionEntity(
            id=orm_obj.id,
            sessionId=orm_obj.session_id,
            resumeId=orm_obj.resume_id,
            totalQuestions=orm_obj.total_questions,
            currentQuestionIndex=orm_obj.current_question_index,
            status=SessionStatus(orm_obj.status.value),
            questionsJson=orm_obj.questions_json,
            overallScore=orm_obj.overall_score,
            overallFeedback=orm_obj.overall_feedback,
            strengthsJson=orm_obj.strengths_json,
            improvementsJson=orm_obj.improvements_json,
            referenceAnswersJson=orm_obj.reference_answers_json,
            createdAt=orm_obj.created_at,
            completedAt=orm_obj.completed_at,
            evaluateStatus=orm_obj.evaluate_status,
            evaluateError=orm_obj.evaluate_error,
        )

    def _to_answer_detail_dto(self, orm_obj: InterviewAnswerORM) -> InterviewAnswerDetailDTO:
        """
        将答案 ORM 对象转换为详情 DTO（含关键点解析）。
        Convert answer ORM object into detail DTO with key-points parsing.
        """
        key_points: list[str] | None = None
        if orm_obj.key_points_json:
            parsed_key_points: list[Any] = self._parse_json_array(orm_obj.key_points_json)
            key_points = [str(item) for item in parsed_key_points]

        return InterviewAnswerDetailDTO(
            questionIndex=orm_obj.question_index,
            question=orm_obj.question,
            category=orm_obj.category,
            userAnswer=orm_obj.user_answer,
            score=orm_obj.score,
            feedback=orm_obj.feedback,
            referenceAnswer=orm_obj.reference_answer,
            keyPoints=key_points,
            answeredAt=orm_obj.answered_at,
        )

    def _parse_json_array(self, raw_json: str | None) -> list[Any]:
        """
        将 JSON 字符串安全解析为数组，失败时返回空数组。
        Safely parse JSON string into list; return empty list on invalid input.
        """
        if raw_json is None or raw_json.strip() == "":
            return []
        try:
            parsed: Any = json.loads(raw_json)
            if isinstance(parsed, list):
                return parsed
            return []
        except json.JSONDecodeError:
            return []
