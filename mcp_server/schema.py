"""
MCP Server Schema - Data models for tools and API contracts.

Defines Pydantic models aligned with the HocGioi database schema:
- exercises table (type: mcq | fill)
- CSV exercise import format
- Content hierarchy: grades -> subjects -> chapters -> topics
- Student performance data
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────
# Enums matching database enum types
# ─────────────────────────────────────────────────────────────────


class ExerciseType(str, Enum):
    """Exercise question type - matches exercise_type enum in Supabase."""
    MCQ = "mcq"
    FILL = "fill"


class Difficulty(int, Enum):
    """Exercise difficulty level: 1 (easy), 2 (medium), 3 (hard)."""
    EASY = 1
    MEDIUM = 2
    HARD = 3


class UserRole(str, Enum):
    """User role in the system."""
    PARENT = "parent"
    ADMIN = "admin"
    TEACHER = "teacher"


# ─────────────────────────────────────────────────────────────────
# Exercise schemas matching ExerciseCard component props
# ─────────────────────────────────────────────────────────────────


class McqOption(BaseModel):
    """A single option in a multiple-choice question.

    Matches: exercises.options JSONB -> [{text: string, image?: string}]
    """
    text: str = Field(..., min_length=1, description="Option text content")
    image: Optional[str] = Field(None, description="Optional image URL (Supabase Storage)")


class McqExercise(BaseModel):
    """Multiple-choice question with 4 options, 1 correct answer.

    Matches: mcq-exercise.tsx component
    DB: options = [{text}, {text}, {text}, {text}], correct_answer = 0-3 (index)
    """
    type: ExerciseType = ExerciseType.MCQ
    question_text: str = Field(..., min_length=1, description="Question content")
    question_image: Optional[str] = Field(None, description="Question image URL")
    options: list[McqOption] = Field(..., min_length=4, max_length=4, description="Exactly 4 answer options")
    correct_option: int = Field(..., ge=0, le=3, description="Index of correct answer (0-3)")
    explanation: Optional[str] = Field(None, description="Answer explanation")
    difficulty: Difficulty = Field(Difficulty.EASY, description="Difficulty level 1-3")

    @field_validator("options")
    @classmethod
    def must_have_4_options(cls, v: list[McqOption]) -> list[McqOption]:
        if len(v) != 4:
            raise ValueError("MCQ must have exactly 4 options")
        return v


class FillExercise(BaseModel):
    """Fill-in-the-blank question.

    Matches: fill-exercise.tsx component
    DB: options = null, correct_answer = ["answer", "variant1", ...]
    """
    type: ExerciseType = ExerciseType.FILL
    question_text: str = Field(..., min_length=1, description="Question with blank placeholder")
    question_image: Optional[str] = Field(None, description="Question image URL")
    fill_answer: str = Field(..., min_length=1, description="Primary correct answer")
    fill_variants: list[str] = Field(default_factory=list, description="Alternative accepted answers")
    explanation: Optional[str] = Field(None, description="Answer explanation")
    difficulty: Difficulty = Field(Difficulty.EASY, description="Difficulty level 1-3")


# ─────────────────────────────────────────────────────────────────
# CSV import format matching HocGioi's exercise import pipeline
# ─────────────────────────────────────────────────────────────────


class CsvExerciseRow(BaseModel):
    """One row from a CSV exercise file.

    Column format: grade, chapter_title, chapter_order, topic_title, topic_order,
                   type, question_text, question_image, option_1..4, correct_option,
                   fill_answer, fill_variants, explanation, difficulty
    """
    grade: int = Field(..., ge=1, le=3, description="Grade level (1-3)")
    chapter_title: str = Field(..., description="Chapter name")
    chapter_order: int = Field(..., ge=1, description="Chapter order index")
    topic_title: str = Field(..., description="Topic name")
    topic_order: int = Field(..., ge=1, description="Topic order index")
    type: ExerciseType
    question_text: str = Field(..., min_length=1)
    question_image: Optional[str] = None
    option_1: Optional[str] = None
    option_2: Optional[str] = None
    option_3: Optional[str] = None
    option_4: Optional[str] = None
    correct_option: Optional[int] = Field(None, ge=1, le=4, description="1-4 (CSV uses 1-based index)")
    fill_answer: Optional[str] = None
    fill_variants: Optional[str] = None
    explanation: Optional[str] = None
    difficulty: Difficulty = Difficulty.EASY


# ─────────────────────────────────────────────────────────────────
# Content hierarchy models: grades -> subjects -> chapters -> topics
# ─────────────────────────────────────────────────────────────────


class TopicInfo(BaseModel):
    """Topic information for agent lookup."""
    id: str
    title: str
    chapter_title: str
    chapter_id: str
    order_index: int


class ChapterInfo(BaseModel):
    """Chapter information with student progress data."""
    id: str
    title: str
    order_index: int
    total_exercises: int = 0
    completed: int = 0
    stars_total: int = 0

    @property
    def completion_rate(self) -> float:
        if self.total_exercises == 0:
            return 0.0
        return self.completed / self.total_exercises


# ─────────────────────────────────────────────────────────────────
# Student / Child info models matching the children table
# ─────────────────────────────────────────────────────────────────


class ChildInfo(BaseModel):
    """Student information - excludes sensitive PII per Decree 13/2023.

    Contains only: name, grade, avatar emoji.
    Does NOT contain: email, phone number, date of birth, photos.
    """
    id: str
    name: str
    grade_id: int = Field(..., ge=1, le=3)
    avatar_emoji: str = ""
    parent_id: str


class ChildPerformance(BaseModel):
    """Aggregated learning performance of a student."""
    child: ChildInfo
    total_exercises_done: int = 0
    total_correct: int = 0
    total_stars: int = 0
    accuracy_rate: float = 0.0
    chapters_progress: list[ChapterInfo] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list, description="Topics with accuracy below threshold")


# ─────────────────────────────────────────────────────────────────
# Agent API request / response schemas
# ─────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class AgentRequest(BaseModel):
    """Request from Next.js frontend to the Agent API."""
    message: str = Field(..., min_length=1, description="User message")
    child_id: Optional[str] = Field(None, description="Student ID if context is for a specific child")
    parent_id: Optional[str] = Field(None, description="Parent user ID")
    conversation_history: list[ChatMessage] = Field(
        default_factory=list, description="Prior conversation turns"
    )
    persona: Optional[str] = Field(
        None,
        pattern="^(consultant|tutor)$",
        description="Agent persona: consultant (parent view) or tutor (student view)",
    )


class AgentResponse(BaseModel):
    """Response from the Agent API back to Next.js frontend."""
    message: str = Field(..., description="Agent response text")
    suggested_exercises: list[McqExercise | FillExercise] = Field(
        default_factory=list, description="Recommended exercises (if any)"
    )
    performance_summary: Optional[ChildPerformance] = Field(
        None, description="Learning report (if requested)"
    )
    action_taken: Optional[str] = Field(
        None, description="Action the agent performed (e.g. 'imported_exercises')"
    )
