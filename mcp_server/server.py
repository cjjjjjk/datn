"""
MCP Server - Tools for fetching data from the HocGioi Supabase database.

This module provides functions that the AI agent can call to retrieve
student learning data without going through the Next.js API layer.
Each function follows the MCP tool pattern: structured input, structured output.

Available tools:
  1. get_student_list         - List all children for a parent
  2. get_student_performance  - Aggregate performance metrics for one student
  3. get_chapter_progress     - Chapter-level progress for a student in one subject
  4. get_weak_topics          - Identify topics with accuracy below threshold
  5. get_curriculum_tree      - Full subjects/chapters/topics tree for a grade
  6. get_exercises_by_topic   - Exercises under a specific topic
  7. search_exercises_csv     - Search exercises from local CSV files
  8. import_exercises_to_db   - Write new exercises into the database
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from supabase import Client, create_client

from config import get_settings
from mcp_server.schema import (
    ChapterInfo,
    ChildInfo,
    ChildPerformance,
    CsvExerciseRow,
    ExerciseType,
    TopicInfo,
)


# ─────────────────────────────────────────────────────────────────
# Supabase client singleton (service role - bypasses RLS)
# ─────────────────────────────────────────────────────────────────

_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    """Create or return the cached Supabase service-role client."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


# ─────────────────────────────────────────────────────────────────
# Tool 1: get_student_list
# ─────────────────────────────────────────────────────────────────


async def get_student_list(parent_id: str) -> list[ChildInfo]:
    """Return all children (students) belonging to a parent account.

    Args:
        parent_id: UUID of the parent user.

    Returns:
        List of ChildInfo objects. Empty list if no children found.
    """
    sb = get_supabase()

    result = sb.table("children").select(
        "id, name, grade_id, avatar_emoji, parent_id"
    ).eq("parent_id", parent_id).execute()

    children = []
    for row in result.data or []:
        children.append(
            ChildInfo(
                id=row["id"],
                name=row["name"],
                grade_id=row["grade_id"],
                avatar_emoji=row.get("avatar_emoji") or "",
                parent_id=row["parent_id"],
            )
        )
    return children


# ─────────────────────────────────────────────────────────────────
# Tool 2: get_student_performance
# ─────────────────────────────────────────────────────────────────


async def get_student_performance(child_id: str) -> ChildPerformance:
    """Fetch aggregated learning performance for a student.

    Queries the progress table to compute:
    - Total exercises attempted
    - Number correct / overall accuracy rate
    - Total stars earned
    - List of weak topic names (accuracy < 60%)

    Args:
        child_id: UUID of the student.

    Returns:
        ChildPerformance with all metrics populated.
    """
    sb = get_supabase()

    # Fetch basic child info
    child_res = sb.table("children").select(
        "id, name, grade_id, avatar_emoji, parent_id"
    ).eq("id", child_id).single().execute()

    child = ChildInfo(**child_res.data)

    # Fetch all progress records for this student
    progress_res = sb.table("progress").select(
        "exercise_id, is_correct, stars_earned, attempts"
    ).eq("child_id", child_id).execute()

    records = progress_res.data or []
    total_done = len(records)
    total_correct = sum(1 for r in records if r["is_correct"])
    total_stars = sum(r["stars_earned"] for r in records)
    accuracy = total_correct / total_done if total_done > 0 else 0.0

    # Identify weak topics from the progress data
    weak_topics = await _analyze_weak_topics(child_id, records)

    return ChildPerformance(
        child=child,
        total_exercises_done=total_done,
        total_correct=total_correct,
        total_stars=total_stars,
        accuracy_rate=round(accuracy, 2),
        weak_topics=weak_topics,
    )


# ─────────────────────────────────────────────────────────────────
# Tool 3: get_chapter_progress
# ─────────────────────────────────────────────────────────────────


async def get_chapter_progress(child_id: str, subject_id: str) -> list[ChapterInfo]:
    """Fetch chapter-level progress for a student in a specific subject.

    Calls a Supabase RPC function 'chapter_progress' to avoid N+1 queries.

    Args:
        child_id:   UUID of the student.
        subject_id: UUID of the subject (e.g. Grade 1 Math).

    Returns:
        List of ChapterInfo with completion and star counts.
    """
    sb = get_supabase()

    result = sb.rpc(
        "chapter_progress",
        {"p_child_id": child_id, "p_subject_id": subject_id},
    ).execute()

    chapters = []
    for row in result.data or []:
        chapters.append(
            ChapterInfo(
                id=row["chapter_id"],
                title=row["chapter_title"],
                order_index=row["order_index"],
                total_exercises=row["total_exercises"],
                completed=row["completed"],
                stars_total=row["stars_total"],
            )
        )

    return chapters


# ─────────────────────────────────────────────────────────────────
# Tool 4: get_weak_topics (public interface)
# ─────────────────────────────────────────────────────────────────


async def get_weak_topics(child_id: str) -> list[str]:
    """Identify topics where the student's accuracy is below 60%.

    Args:
        child_id: UUID of the student.

    Returns:
        List of topic title strings. Empty list if no weak topics.
    """
    sb = get_supabase()

    progress_res = sb.table("progress").select(
        "exercise_id, is_correct, stars_earned, attempts"
    ).eq("child_id", child_id).execute()

    return await _analyze_weak_topics(child_id, progress_res.data or [])


async def _analyze_weak_topics(
    child_id: str, progress_records: list[dict[str, Any]]
) -> list[str]:
    """Internal helper: compute weak topics from progress records.

    Logic:
      - Map each exercise to its topic via the exercises table
      - Compute per-topic accuracy (correct / total)
      - Return topics where accuracy < 60%

    Args:
        child_id:         UUID of the student (unused but kept for tracing).
        progress_records: Rows from the progress table.

    Returns:
        List of weak topic title strings.
    """
    if not progress_records:
        return []

    sb = get_supabase()

    # Collect all exercise IDs from the progress records
    exercise_ids = [r["exercise_id"] for r in progress_records]

    # Fetch topic_id for each exercise in one query
    exercises_res = sb.table("exercises").select(
        "id, topic_id"
    ).in_("id", exercise_ids).execute()

    # Build mapping: exercise_id -> topic_id
    ex_to_topic: dict[str, str] = {}
    for ex in exercises_res.data or []:
        ex_to_topic[ex["id"]] = ex["topic_id"]

    # Compute accuracy per topic
    topic_stats: dict[str, dict[str, int]] = {}
    for rec in progress_records:
        topic_id = ex_to_topic.get(rec["exercise_id"])
        if not topic_id:
            continue
        if topic_id not in topic_stats:
            topic_stats[topic_id] = {"correct": 0, "total": 0}
        topic_stats[topic_id]["total"] += 1
        if rec["is_correct"]:
            topic_stats[topic_id]["correct"] += 1

    # Select topics with accuracy < 60%
    weak_topic_ids = [
        tid
        for tid, stats in topic_stats.items()
        if stats["total"] > 0 and stats["correct"] / stats["total"] < 0.6
    ]

    if not weak_topic_ids:
        return []

    # Resolve topic IDs to titles
    topics_res = sb.table("topics").select(
        "id, title"
    ).in_("id", weak_topic_ids).execute()

    return [t["title"] for t in topics_res.data or []]


# ─────────────────────────────────────────────────────────────────
# Tool 5: get_curriculum_tree
# ─────────────────────────────────────────────────────────────────


async def get_curriculum_tree(grade_id: int) -> list[TopicInfo]:
    """Return the full curriculum structure for a grade level.

    Traverses: subjects -> chapters -> topics for the given grade.
    Useful for the agent to understand available content.

    Args:
        grade_id: Grade level (1, 2, or 3).

    Returns:
        Flat list of TopicInfo objects sorted by order_index.
    """
    sb = get_supabase()

    # Get all subjects for this grade
    subjects_res = sb.table("subjects").select("id").eq(
        "grade_id", grade_id
    ).execute()

    if not subjects_res.data:
        return []

    subject_ids = [s["id"] for s in subjects_res.data]

    # Get all chapters in those subjects
    chapters_res = sb.table("chapters").select(
        "id, title, subject_id"
    ).in_("subject_id", subject_ids).execute()

    if not chapters_res.data:
        return []

    chapter_map: dict[str, str] = {c["id"]: c["title"] for c in chapters_res.data}
    chapter_ids = list(chapter_map.keys())

    # Get all topics in those chapters
    topics_res = sb.table("topics").select(
        "id, title, chapter_id, order_index"
    ).in_("chapter_id", chapter_ids).order("order_index").execute()

    return [
        TopicInfo(
            id=t["id"],
            title=t["title"],
            chapter_title=chapter_map.get(t["chapter_id"], ""),
            chapter_id=t["chapter_id"],
            order_index=t["order_index"],
        )
        for t in topics_res.data or []
    ]


# ─────────────────────────────────────────────────────────────────
# Tool 6: get_exercises_by_topic
# ─────────────────────────────────────────────────────────────────


async def get_exercises_by_topic(topic_id: str) -> list[dict[str, Any]]:
    """Fetch all exercises under a specific topic.

    NOTE: correct_answer is intentionally excluded from the returned fields
    when used in client-facing contexts. The agent can use this data
    internally for analysis but should not expose answers to students.

    Args:
        topic_id: UUID of the topic.

    Returns:
        List of exercise dicts with metadata but without correct answers.
    """
    sb = get_supabase()

    result = sb.table("exercises").select(
        "id, type, question_text, question_image, options, explanation, difficulty, order_index"
    ).eq("topic_id", topic_id).order("order_index").execute()

    return result.data or []


# ─────────────────────────────────────────────────────────────────
# Tool 7: search_exercises_csv
# ─────────────────────────────────────────────────────────────────


async def search_exercises_csv(
    grade: int,
    chapter_title: Optional[str] = None,
    topic_title: Optional[str] = None,
    exercise_type: Optional[ExerciseType] = None,
    difficulty: Optional[int] = None,
    limit: int = 10,
) -> list[CsvExerciseRow]:
    """Search exercises from local CSV files based on filter criteria.

    Used when the agent needs to recommend exercises to cover a student's
    knowledge gaps. CSV files are stored in the HocGioi project's public/samples.

    Args:
        grade:          Grade level (1-3).
        chapter_title:  Filter by chapter name (partial match, case-insensitive).
        topic_title:    Filter by topic name (partial match, case-insensitive).
        exercise_type:  Filter by type (mcq or fill).
        difficulty:     Filter by difficulty (1=easy, 2=medium, 3=hard).
        limit:          Maximum number of results to return.

    Returns:
        List of CsvExerciseRow matching the criteria.
    """
    settings = get_settings()
    csv_path = Path(settings.CSV_DATA_DIR) / f"grade{grade}-math.csv"

    if not csv_path.exists():
        return []

    results: list[CsvExerciseRow] = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Apply filters
            if chapter_title and chapter_title.lower() not in row.get("chapter_title", "").lower():
                continue
            if topic_title and topic_title.lower() not in row.get("topic_title", "").lower():
                continue
            if exercise_type and row.get("type") != exercise_type.value:
                continue
            if difficulty and int(row.get("difficulty", 1)) != difficulty:
                continue

            try:
                exercise = CsvExerciseRow(
                    grade=int(row["grade"]),
                    chapter_title=row["chapter_title"],
                    chapter_order=int(row["chapter_order"]),
                    topic_title=row["topic_title"],
                    topic_order=int(row["topic_order"]),
                    type=ExerciseType(row["type"]),
                    question_text=row["question_text"],
                    question_image=row.get("question_image") or None,
                    option_1=row.get("option_1") or None,
                    option_2=row.get("option_2") or None,
                    option_3=row.get("option_3") or None,
                    option_4=row.get("option_4") or None,
                    correct_option=int(row["correct_option"]) if row.get("correct_option") else None,
                    fill_answer=row.get("fill_answer") or None,
                    fill_variants=row.get("fill_variants") or None,
                    explanation=row.get("explanation") or None,
                    difficulty=int(row.get("difficulty", 1)),
                )
                results.append(exercise)
            except (ValueError, KeyError):
                continue

            if len(results) >= limit:
                break

    return results


# ─────────────────────────────────────────────────────────────────
# Tool 8: import_exercises_to_db
# ─────────────────────────────────────────────────────────────────


async def import_exercises_to_db(
    exercises: list[CsvExerciseRow],
) -> dict[str, Any]:
    """Write a list of exercises into the Supabase database.

    Mirrors the CSV import pipeline in the HocGioi Next.js app:
    - Auto-creates chapters and topics if they don't exist yet
    - Inserts exercises in the correct format

    Args:
        exercises: List of CsvExerciseRow to import.

    Returns:
        Dict with keys: imported (int), errors (list[str])
    """
    sb = get_supabase()
    imported = 0
    errors: list[str] = []

    for ex in exercises:
        try:
            # Resolve subject by grade
            subject_res = sb.table("subjects").select("id").eq(
                "grade_id", ex.grade
            ).eq("slug", "toan").single().execute()
            subject_id = subject_res.data["id"]

            # Find or create chapter
            chapter_res = sb.table("chapters").select("id").eq(
                "subject_id", subject_id
            ).eq("title", ex.chapter_title).maybe_single().execute()

            if chapter_res.data:
                chapter_id = chapter_res.data["id"]
            else:
                new_chapter = sb.table("chapters").insert({
                    "subject_id": subject_id,
                    "title": ex.chapter_title,
                    "order_index": ex.chapter_order,
                }).execute()
                chapter_id = new_chapter.data[0]["id"]

            # Find or create topic
            topic_res = sb.table("topics").select("id").eq(
                "chapter_id", chapter_id
            ).eq("title", ex.topic_title).maybe_single().execute()

            if topic_res.data:
                topic_id = topic_res.data["id"]
            else:
                new_topic = sb.table("topics").insert({
                    "chapter_id": chapter_id,
                    "title": ex.topic_title,
                    "order_index": ex.topic_order,
                }).execute()
                topic_id = new_topic.data[0]["id"]

            # Build options and correct_answer per exercise type
            if ex.type == ExerciseType.MCQ:
                options = [
                    {"text": ex.option_1 or ""},
                    {"text": ex.option_2 or ""},
                    {"text": ex.option_3 or ""},
                    {"text": ex.option_4 or ""},
                ]
                # CSV uses 1-based index, DB uses 0-based
                correct_answer = (ex.correct_option or 1) - 1
            else:
                options = None
                variants = [ex.fill_answer or ""]
                if ex.fill_variants:
                    variants.extend(v.strip() for v in ex.fill_variants.split(","))
                correct_answer = variants

            # Determine order_index for this exercise in the topic
            count_res = sb.table("exercises").select(
                "id", count="exact"
            ).eq("topic_id", topic_id).execute()
            order_index = (count_res.count or 0) + 1

            # Insert the exercise
            sb.table("exercises").insert({
                "topic_id": topic_id,
                "type": ex.type.value,
                "question_text": ex.question_text,
                "question_image": ex.question_image,
                "options": options,
                "correct_answer": correct_answer,
                "explanation": ex.explanation,
                "difficulty": ex.difficulty,
                "order_index": order_index,
            }).execute()

            imported += 1

        except Exception as e:
            errors.append(f"Failed to import '{ex.question_text[:50]}': {str(e)}")

    return {"imported": imported, "errors": errors}
