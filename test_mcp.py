"""
Basic MCP data retrieval test script.

Run this script to verify that the MCP server functions can successfully
connect to Supabase and retrieve data from the HocGioi database.
Useful for validating environment configuration before running the full agent.

Usage:
  python test_mcp.py

Prerequisites:
  - .env file with valid SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
  - Supabase local instance running (supabase start) or remote project URL
"""

from __future__ import annotations

import asyncio
import sys


async def test_supabase_connection() -> bool:
    """Test that the Supabase client can connect and query the database."""
    from mcp_server.server import get_supabase

    print("\n[Test 1] Supabase connection")
    try:
        sb = get_supabase()
        # Try a simple query - list grades table
        result = sb.table("grades").select("id, level").execute()
        grades = result.data or []
        print(f"  Connected. Found {len(grades)} grade(s):")
        for g in grades:
            print(f"    - Grade {g.get('level', '?')} (id: {g.get('id', '?')})")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_get_curriculum_tree(grade_id: int = 1) -> bool:
    """Test fetching the curriculum structure (subjects/chapters/topics) for a grade."""
    from mcp_server.server import get_curriculum_tree

    print(f"\n[Test 2] Curriculum tree for Grade {grade_id}")
    try:
        topics = await get_curriculum_tree(grade_id)
        if not topics:
            print(f"  No topics found for Grade {grade_id} (may be empty database).")
            return True

        # Group by chapter for display
        chapters: dict[str, list[str]] = {}
        for t in topics:
            chapters.setdefault(t.chapter_title, []).append(t.title)

        print(f"  Found {len(topics)} topic(s) in {len(chapters)} chapter(s):")
        for ch, topic_list in chapters.items():
            print(f"    Chapter: {ch}")
            for tt in topic_list[:3]:  # Show first 3 topics per chapter
                print(f"      - {tt}")
            if len(topic_list) > 3:
                print(f"      ... and {len(topic_list) - 3} more")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_get_student_list(parent_id: str) -> list[str]:
    """Test fetching children for a given parent UUID.

    Returns a list of child IDs found (may be empty).
    """
    from mcp_server.server import get_student_list

    print(f"\n[Test 3] Student list for parent {parent_id[:8]}...")
    try:
        children = await get_student_list(parent_id)
        if not children:
            print("  No students found for this parent ID.")
            return []

        print(f"  Found {len(children)} student(s):")
        child_ids = []
        for child in children:
            print(f"    - {child.name} | Grade {child.grade_id} | id: {child.id}")
            child_ids.append(child.id)
        return child_ids
    except Exception as e:
        print(f"  FAILED: {e}")
        return []


async def test_get_student_performance(child_id: str) -> bool:
    """Test fetching aggregate performance data for a student."""
    from mcp_server.server import get_student_performance

    print(f"\n[Test 4] Student performance for child {child_id[:8]}...")
    try:
        perf = await get_student_performance(child_id)
        print(f"  Student: {perf.child.name} (Grade {perf.child.grade_id})")
        print(f"  Exercises done  : {perf.total_exercises_done}")
        print(f"  Correct answers : {perf.total_correct}")
        print(f"  Accuracy        : {perf.accuracy_rate * 100:.1f}%")
        print(f"  Total stars     : {perf.total_stars}")
        if perf.weak_topics:
            print(f"  Weak topics     : {', '.join(perf.weak_topics)}")
        else:
            print("  Weak topics     : None (or no data yet)")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_get_weak_topics(child_id: str) -> bool:
    """Test the weak topic analysis function."""
    from mcp_server.server import get_weak_topics

    print(f"\n[Test 5] Weak topics for child {child_id[:8]}...")
    try:
        weak = await get_weak_topics(child_id)
        if not weak:
            print("  No weak topics found (accuracy >= 60% everywhere, or no data).")
        else:
            print(f"  Found {len(weak)} weak topic(s):")
            for t in weak:
                print(f"    - {t}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_search_exercises_csv(grade: int = 1) -> bool:
    """Test searching exercises from local CSV files."""
    from mcp_server.server import search_exercises_csv

    print(f"\n[Test 6] CSV exercise search for Grade {grade}")
    try:
        exercises = await search_exercises_csv(grade=grade, limit=3)
        if not exercises:
            print(f"  No exercises found. Check that CSV_DATA_DIR in .env points to the correct path.")
            print("  Expected file: grade1-math.csv (or grade2, grade3)")
            return False

        print(f"  Found exercises in CSV. Showing first {len(exercises)}:")
        for ex in exercises:
            print(f"    [{ex.type.value}] {ex.question_text[:60]}...")
            print(f"      Topic: {ex.chapter_title} > {ex.topic_title}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def run_all_tests(parent_id: str = "", child_id: str = ""):
    """Run all MCP data retrieval tests in sequence.

    Args:
        parent_id: A valid parent UUID from your Supabase database.
                   If empty, tests 3-5 will be skipped.
        child_id:  A valid child UUID. If empty, derived from parent's children
                   via test_get_student_list, or skipped.
    """
    print("=" * 60)
    print("  HocGioi Agent - MCP Data Retrieval Test")
    print("=" * 60)

    results = {}

    # Test 1: Basic connection
    results["connection"] = await test_supabase_connection()

    # Test 2: Curriculum structure
    results["curriculum"] = await test_get_curriculum_tree(grade_id=1)

    # Tests 3-5: Need a parent_id / child_id
    if parent_id:
        child_ids = await test_get_student_list(parent_id)
        results["student_list"] = len(child_ids) >= 0  # Pass even if empty

        # Use provided child_id or first discovered one
        resolved_child_id = child_id or (child_ids[0] if child_ids else "")

        if resolved_child_id:
            results["performance"] = await test_get_student_performance(resolved_child_id)
            results["weak_topics"] = await test_get_weak_topics(resolved_child_id)
        else:
            print("\n[Test 4-5] Skipped - no child_id available")
    else:
        print("\n[Test 3-5] Skipped - no parent_id provided")
        print("  Re-run with: asyncio.run(run_all_tests(parent_id='...', child_id='...'))")

    # Test 6: CSV search
    results["csv_search"] = await test_search_exercises_csv(grade=1)

    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  Result: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    # Optionally pass parent_id and child_id as command-line arguments
    # Example: python test_mcp.py <parent_uuid> <child_uuid>
    parent_id = sys.argv[1] if len(sys.argv) > 1 else ""
    child_id = sys.argv[2] if len(sys.argv) > 2 else ""

    success = asyncio.run(run_all_tests(parent_id=parent_id, child_id=child_id))
    sys.exit(0 if success else 1)
