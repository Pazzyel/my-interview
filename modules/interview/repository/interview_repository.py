import json
from typing import Any

from sqlalchemy import delete, desc, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import InterviewAnswerORM, InterviewSessionORM
from infrastructure.database.models import ResumeORM
from modules.interview.model.interview_dto import InterviewAnswerDetailDTO, InterviewDetailDTO, InterviewHistoryItemDTO
from modules.interview.model.interview_entity import InterviewSessionEntity, SessionStatus


class InterviewRepository:
    """
    面试仓储层，负责面试会话与答案的数据库访问。
    Interview repository for interview sessions and answers.
    """

    async def create_session(
        self,
        db: AsyncSession,
        session_id: str,
        resume_id: int,
        total_questions: int,
        questions_json: str,
    ) -> None:
        insert_data: dict[str, Any] = {
            "session_id": session_id,
            "resume_id": resume_id,
            "total_questions": total_questions,
            "current_question_index": 0,
            "status": "CREATED",
            "questions_json": questions_json,
        }
        await db.execute(insert(InterviewSessionORM).values(**insert_data))

    async def update_session_status(self, db: AsyncSession, session_id: str, status: str) -> None:
        update_data: dict[str, Any] = {"status": status}
        await db.execute(
            update(InterviewSessionORM)
            .where(InterviewSessionORM.session_id == session_id)
            .values(**update_data)
        )

    async def update_evaluate_status(
        self,
        db: AsyncSession,
        session_id: str,
        evaluate_status: str,
        evaluate_error: str | None,
    ) -> None:
        update_data: dict[str, Any] = {
            "evaluate_status": evaluate_status,
            "evaluate_error": evaluate_error,
        }
        await db.execute(
            update(InterviewSessionORM)
            .where(InterviewSessionORM.session_id == session_id)
            .values(**update_data)
        )

    async def update_session_questions_json(self, db: AsyncSession, session_id: str, questions_json: str) -> None:
        await db.execute(
            update(InterviewSessionORM)
            .where(InterviewSessionORM.session_id == session_id)
            .values(questions_json=questions_json)
        )

    async def update_session_progress(
        self,
        db: AsyncSession,
        session_id: str,
        current_question_index: int,
        status: str,
        questions_json: str,
    ) -> None:
        update_data: dict[str, Any] = {
            "current_question_index": current_question_index,
            "status": status,
            "questions_json": questions_json,
        }
        await db.execute(
            update(InterviewSessionORM)
            .where(InterviewSessionORM.session_id == session_id)
            .values(**update_data)
        )

    async def save_report(
        self,
        db: AsyncSession,
        session_id: str,
        overall_score: int,
        overall_feedback: str,
        strengths_json: str,
        improvements_json: str,
        reference_answers_json: str,
    ) -> None:
        update_data: dict[str, Any] = {
            "overall_score": overall_score,
            "overall_feedback": overall_feedback,
            "strengths_json": strengths_json,
            "improvements_json": improvements_json,
            "reference_answers_json": reference_answers_json,
        }
        await db.execute(
            update(InterviewSessionORM)
            .where(InterviewSessionORM.session_id == session_id)
            .values(**update_data)
        )

    async def upsert_answer(
        self,
        db: AsyncSession,
        session_id: str,
        question_index: int,
        question: str,
        category: str,
        user_answer: str | None,
        score: int | None,
        feedback: str | None,
        reference_answer: str | None,
        key_points_json: str | None,
    ) -> None:
        """
        中文：按 session_id 与 question_index 做答案记录的插入或更新。
        English: Insert or update answer record by session_id and question_index.
        """
        # 关键步骤1：先解析会话主键，避免跨会话误更新
        # Key step 1: resolve session PK first to avoid cross-session update.
        session_stmt = select(InterviewSessionORM.id).where(InterviewSessionORM.session_id == session_id)
        session_result = await db.execute(session_stmt)
        session_pk_id: int | None = session_result.scalar_one_or_none()
        if session_pk_id is None:
            raise BusinessException(ErrorCode.INTERVIEW_SESSION_NOT_FOUND, "面试会话不存在")

        answer_stmt = (
            select(InterviewAnswerORM)
            .where(InterviewAnswerORM.session_pk_id == session_pk_id)
            .where(InterviewAnswerORM.question_index == question_index)
        )
        answer_result = await db.execute(answer_stmt)
        answer_orm: InterviewAnswerORM | None = answer_result.scalar_one_or_none()

        update_data: dict[str, Any] = {
            "question": question,
            "category": category,
            "user_answer": user_answer,
            "score": score,
            "feedback": feedback,
            "reference_answer": reference_answer,
            "key_points_json": key_points_json,
        }

        # 关键步骤2：不存在则插入，存在则更新
        # Key step 2: insert on missing row, otherwise update.
        if answer_orm is None:
            update_data["session_pk_id"] = session_pk_id
            update_data["question_index"] = question_index
            await db.execute(insert(InterviewAnswerORM).values(**update_data))
            return

        await db.execute(
            update(InterviewAnswerORM)
            .where(InterviewAnswerORM.id == answer_orm.id)
            .values(**update_data)
        )

    async def get_resume_text_by_session_id(self, db: AsyncSession, session_id: str) -> str:
        stmt = (
            select(ResumeORM.resumeText)
            .join(InterviewSessionORM, InterviewSessionORM.resume_id == ResumeORM.id)
            .where(InterviewSessionORM.session_id == session_id)
        )
        result = await db.execute(stmt)
        resume_text: str | None = result.scalar_one_or_none()
        return resume_text or ""

    async def list_historical_questions_by_resume_id(self, db: AsyncSession, resume_id: int) -> list[str]:
        """
        中文：读取同一简历历史会话中的主问题，去重后返回有限数量。
        English: Load historical main questions for the same resume, deduplicate,
        and return a bounded list.
        """
        stmt = (
            select(InterviewSessionORM.questions_json)
            .where(InterviewSessionORM.resume_id == resume_id)
            .order_by(desc(InterviewSessionORM.created_at))
            .limit(10)
        )
        result = await db.execute(stmt)
        question_json_list: list[str] = [item for item in result.scalars().all() if item]

        questions: list[str] = []
        seen: set[str] = set()
        for question_json in question_json_list:
            parsed_list: list[Any] = self._parse_json_array(question_json)
            for item in parsed_list:
                if isinstance(item, dict):
                    question_text: str = str(item.get("question", "")).strip()
                    is_follow_up: bool = bool(item.get("isFollowUp", False))
                    if question_text != "" and not is_follow_up and question_text not in seen:
                        seen.add(question_text)
                        questions.append(question_text)
        return questions[:30]

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
