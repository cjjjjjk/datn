"""
Agent Tools - LangChain-compatible wrappers around MCP server functions.

Each function here is decorated with @tool so LangGraph's ToolNode
can call them automatically when the LLM requests them.

Tools available:
  - tool_get_student_list         : List students for a parent
  - tool_get_student_performance  : Aggregate learning stats for a student
  - tool_get_chapter_progress     : Chapter-level progress breakdown
  - tool_analyze_weak_points      : Identify knowledge gaps
  - tool_get_curriculum_tree      : Explore available content structure
  - tool_recommend_exercises      : Find exercises from CSV bank
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool

from mcp_server.schema import ExerciseType
from mcp_server.server import (
    get_chapter_progress,
    get_curriculum_tree,
    get_exercises_by_topic,
    get_student_list,
    get_student_performance,
    get_weak_topics,
    import_exercises_to_db,
    search_exercises_csv,
)


# ─────────────────────────────────────────────────────────────────
# Tool 1: List students for a parent
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_get_student_list(parent_id: str) -> str:
    """List all students (children) registered under a parent account.

    Use this when you need to know which children a parent has,
    or to find the child_id before calling other tools.

    Args:
        parent_id: UUID of the parent user.
    """
    try:
        children = await get_student_list(parent_id)
        if not children:
            return "No students found for this parent account."

        lines = [f"Students registered under parent {parent_id}:\n"]
        for i, child in enumerate(children, 1):
            lines.append(f"  {i}. {child.name} | Grade {child.grade_id} | ID: {child.id}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving student list: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Tool 2: Get aggregate learning performance
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_get_student_performance(child_id: str) -> str:
    """Get aggregated learning performance metrics for a student.

    Returns total exercises attempted, accuracy rate, stars earned,
    and a list of weak topics that need improvement.

    Use this when the parent asks 'How is my child doing?'
    or when you need overall performance data.

    Args:
        child_id: UUID of the student.
    """
    try:
        perf = await get_student_performance(child_id)
        weak = ", ".join(perf.weak_topics) if perf.weak_topics else "None identified"

        return (
            f"Learning performance for {perf.child.name} (Grade {perf.child.grade_id}):\n"
            f"  Total exercises done: {perf.total_exercises_done}\n"
            f"  Correct answers: {perf.total_correct}\n"
            f"  Overall accuracy: {perf.accuracy_rate * 100:.0f}%\n"
            f"  Total stars earned: {perf.total_stars}\n"
            f"  Topics needing improvement: {weak}"
        )
    except Exception as e:
        return f"Error retrieving performance data: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Tool 3: Chapter-level progress breakdown
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_get_chapter_progress(child_id: str, subject_id: str) -> str:
    """Get chapter-by-chapter progress for a student in a specific subject.

    Returns each chapter with its completion percentage and stars earned.
    Use this when you need a detailed breakdown by chapter.

    Args:
        child_id:   UUID of the student.
        subject_id: UUID of the subject.
    """
    try:
        chapters = await get_chapter_progress(child_id, subject_id)
        if not chapters:
            return "No chapter progress data found for this subject."

        lines = ["Chapter progress breakdown:\n"]
        for ch in chapters:
            pct = ch.completion_rate * 100
            lines.append(
                f"  {ch.order_index}. {ch.title}\n"
                f"     Progress: {pct:.0f}% ({ch.completed}/{ch.total_exercises} exercises)"
                f" | Stars: {ch.stars_total}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving chapter progress: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Tool 4: Analyze knowledge gaps
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_analyze_weak_points(child_id: str) -> str:
    """Identify topics where the student's accuracy is below 60%.

    Use this when the parent asks 'What does my child struggle with?'
    or before recommending targeted practice exercises.

    Args:
        child_id: UUID of the student.
    """
    try:
        weak = await get_weak_topics(child_id)
        if not weak:
            return (
                "No significant weak points detected. "
                "The student has maintained above 60% accuracy across all attempted topics."
            )

        lines = ["Topics with accuracy below 60% (need improvement):\n"]
        for i, topic in enumerate(weak, 1):
            lines.append(f"  {i}. {topic}")
        lines.append("\nRecommendation: Focus practice on these topics, starting from easier exercises.")
        return "\n".join(lines)
    except Exception as e:
        return f"Error analyzing weak points: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Tool 5: Explore curriculum structure
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_get_curriculum_tree(grade_id: int) -> str:
    """Explore the full curriculum structure (subjects, chapters, topics) for a grade.

    Use this to understand what content is available in the system,
    useful before recommending study paths or searching exercises.

    Args:
        grade_id: Grade level (1, 2, or 3).
    """
    try:
        topics = await get_curriculum_tree(grade_id)
        if not topics:
            return f"No curriculum content found for Grade {grade_id}."

        # Group topics by chapter
        chapters: dict[str, list[str]] = {}
        for t in topics:
            if t.chapter_title not in chapters:
                chapters[t.chapter_title] = []
            chapters[t.chapter_title].append(t.title)

        lines = [f"Curriculum structure for Grade {grade_id}:\n"]
        for ch_title, topic_titles in chapters.items():
            lines.append(f"  Chapter: {ch_title}")
            for tt in topic_titles:
                lines.append(f"    - {tt}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving curriculum: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Tool 6: Find exercises from CSV bank
# ─────────────────────────────────────────────────────────────────


@tool
async def tool_recommend_exercises(
    grade: int,
    chapter_title: str = "",
    topic_title: str = "",
    exercise_type: str = "",
    difficulty: int = 0,
    limit: int = 5,
) -> str:
    """Search the exercise bank (CSV files) for exercises matching criteria.

    Use this to recommend targeted exercises for a student's weak topics,
    or when a parent wants practice exercises for a specific area.

    Args:
        grade:          Grade level (1, 2, or 3).
        chapter_title:  Filter by chapter name (partial match). Leave empty for all.
        topic_title:    Filter by topic name (partial match). Leave empty for all.
        exercise_type:  "mcq" or "fill". Leave empty for all types.
        difficulty:     1 (easy), 2 (medium), 3 (hard). 0 = all difficulties.
        limit:          Maximum number of exercises to return (default 5).
    """
    try:
        ex_type = ExerciseType(exercise_type) if exercise_type else None
        diff = difficulty if difficulty > 0 else None

        exercises = await search_exercises_csv(
            grade=grade,
            chapter_title=chapter_title or None,
            topic_title=topic_title or None,
            exercise_type=ex_type,
            difficulty=diff,
            limit=limit,
        )

        if not exercises:
            return "No exercises found matching the specified criteria."

        lines = [f"Found {len(exercises)} matching exercises:\n"]
        for i, ex in enumerate(exercises, 1):
            type_label = "Multiple Choice" if ex.type == ExerciseType.MCQ else "Fill in Blank"
            diff_label = {1: "Easy", 2: "Medium", 3: "Hard"}.get(ex.difficulty, "?")
            lines.append(
                f"  {i}. [{type_label} | {diff_label}] {ex.question_text[:80]}\n"
                f"     Location: {ex.chapter_title} > {ex.topic_title}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching exercises: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Master tool list (used by LangGraph ToolNode and LLM binding)
# ─────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    tool_get_student_list,
    tool_get_student_performance,
    tool_get_chapter_progress,
    tool_analyze_weak_points,
    tool_get_curriculum_tree,
    tool_recommend_exercises,
]
