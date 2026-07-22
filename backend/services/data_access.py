from __future__ import annotations

import uuid
from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import AuthUser
from models import AnswerKey, Exam, Student
from schemas import StudentMetadata


def ensure_exam_access(exam: Exam, user: AuthUser) -> Exam:
    return exam


def get_exam_or_404(db: Session, exam_id: uuid.UUID, user: AuthUser) -> Exam:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    return ensure_exam_access(exam, user)


def validate_complete_answer_key(
    exam: Exam, answers: Mapping[int | str, str]
) -> dict[int, str]:
    normalized: dict[int, str] = {}
    for raw_question, raw_answer in answers.items():
        try:
            question = int(raw_question)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid question number: {raw_question!r}",
            ) from exc
        if isinstance(raw_question, bool) or question in normalized:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate question number: {question}",
            )
        answer = str(raw_answer).strip().upper()
        allowed_answers = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: exam.options_per_question])
        if answer not in allowed_answers:
            allowed = ", ".join(allowed_answers)
            raise HTTPException(
                status_code=422,
                detail=f"Question {question} must use one of: {allowed}",
            )
        normalized[question] = answer

    expected = set(range(1, exam.total_questions + 1))
    received = set(normalized)
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing questions: {', '.join(map(str, missing))}")
        if extra:
            details.append(f"out-of-range questions: {', '.join(map(str, extra))}")
        raise HTTPException(
            status_code=422,
            detail="Answer key must include every question exactly once ("
            + "; ".join(details)
            + ")",
        )
    return dict(sorted(normalized.items()))


def replace_answer_key(
    db: Session, exam: Exam, answers: Mapping[int, str]
) -> None:
    try:
        db.execute(delete(AnswerKey).where(AnswerKey.exam_id == exam.id))
        db.add_all(
            AnswerKey(
                exam_id=exam.id,
                question_number=question,
                correct_answer=answer,
            )
            for question, answer in sorted(answers.items())
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def load_answer_key(db: Session, exam: Exam) -> dict[int, str]:
    rows = db.scalars(
        select(AnswerKey)
        .where(AnswerKey.exam_id == exam.id)
        .order_by(AnswerKey.question_number)
    ).all()
    answers = {row.question_number: row.correct_answer for row in rows}
    if len(answers) != exam.total_questions:
        raise HTTPException(
            status_code=422,
            detail="A complete answer key must be saved before scanning student sheets",
        )
    return answers


def resolve_student(
    db: Session, metadata: StudentMetadata
) -> Student:
    student: Student | None = None
    if metadata.roll_number:
        student = db.scalar(
            select(Student).where(
                Student.roll_number == metadata.roll_number,
            )
        )
    if student is None:
        student = Student(
            name=metadata.name,
            roll_number=metadata.roll_number,
            class_name=metadata.class_name,
        )
        db.add(student)
        db.flush()
        return student

    if metadata.name is not None:
        student.name = metadata.name
    if metadata.class_name is not None:
        student.class_name = metadata.class_name
    db.flush()
    return student
