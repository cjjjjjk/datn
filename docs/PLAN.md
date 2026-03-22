# HocGioi-Agent: 3-Month Development Plan

## Overview

This document outlines the development roadmap for HocGioi-Agent, an AI-powered
personalized learning recommendation system built on top of the HocGioi platform.

**Tech stack:** LangGraph (orchestration) + MCP (data tools) + Google Gemini + Supabase

**Goal:** A working end-to-end agent that analyzes student learning data and generates
personalized recommendations for parents and students.

---

## Month 1: Foundation and Data Layer (Weeks 1-4)

Focus: Stable base project + verified data access + basic agent loop working.

### Week 1: Project Setup and Base Structure

- [x] Initialize project structure (agents/, mcp_server/, api/, docs/)
- [x] Set up virtual environment and install dependencies
- [x] Configure environment variables (.env) for Supabase and Google AI
- [x] Write config.py with pydantic-settings
- [x] Connect to Supabase (local dev via `supabase start`)
- [x] Write mcp_server/schema.py with all Pydantic models
- [x] Write first version of mcp_server/server.py with basic query functions
- [x] Write test_mcp.py to manually verify data retrieval
- [ ] Run `supabase start` and confirm Supabase is accessible locally

### Week 2: MCP Tools - Data Retrieval

- [x] Tool: `get_student_list` - fetch children for a parent
- [x] Tool: `get_student_performance` - aggregate learning metrics
- [x] Tool: `get_chapter_progress` - chapter-level breakdown using RPC
- [x] Tool: `get_weak_topics` - identify topics with accuracy < 60%
- [x] Tool: `get_curriculum_tree` - traverse subjects/chapters/topics
- [x] Tool: `get_exercises_by_topic` - fetch exercises for a topic
- [x] Tool: `search_exercises_csv` - query local CSV exercise bank
- [ ] Write unit tests for each MCP server function (test with real local DB)
- [ ] Test `test_mcp.py` with real parent_id and child_id from Supabase

### Week 3: LangGraph Agent - Base Loop

- [x] Define AgentState TypedDict
- [x] Implement `classify_input` node (fast LLM, 1-word output)
- [x] Implement `agent_process` node (smart LLM with tool binding)
- [x] Wire up ToolNode with all MCP tools
- [x] Define `should_use_tools` conditional edge (agent <-> tools loop)
- [x] Compile graph and expose via `get_graph()` / `run_agent()`
- [ ] Manual test: send sample messages and trace the LangGraph execution
- [ ] Verify tool execution flow end-to-end (classify -> agent -> tool -> respond)

### Week 4: FastAPI Server and Integration

- [x] Implement `POST /api/chat` - synchronous response
- [x] Implement `POST /api/chat/stream` - SSE streaming response
- [x] Implement `GET /api/health` - health check
- [x] Implement `GET /api/tools` - list available tools
- [x] Add CORS middleware for Next.js frontend
- [ ] Manual test with `curl` or Postman
- [ ] Test streaming endpoint with browser EventSource
- [ ] First git commit: base project running end-to-end

---

## Month 2: Agent Intelligence and Recommendation Logic (Weeks 5-10)

Focus: Build the full recommendation pipeline; improve agent quality.

### Week 5: Parent Intent Processing

- [ ] Design input types: text description from parent (e.g. "my child struggles with subtraction")
- [ ] Update `classify_input` to better detect recommendation intent
- [ ] Implement `extract_intent` helper to parse parent input into structured data
  - Extract: subject area, difficulty concern, desired outcome
- [ ] Add unit tests for intent extraction
- [ ] Update CONSULTANT_SYSTEM_PROMPT to guide this intent extraction flow

### Week 6: Student Analytics Deep Dive

- [ ] Add `get_topic_accuracy_breakdown` tool - per-topic accuracy with trend
- [ ] Add `get_recent_progress` tool - last N exercise attempts with timestamps
- [ ] Add `get_exercise_retry_pattern` tool - exercises attempted more than 2 times
- [ ] Compute learning velocity metric (exercises per day over last 7/30 days)
- [ ] Store intermediate analytics results in AgentState for multi-step reasoning

### Week 7: Recommendation Generation

- [ ] Implement recommendation ranking algorithm:
  - Score topics by: (1 - accuracy) * recency_weight * curriculum_position
  - Prefer topics adjacent to already-mastered ones
- [ ] Add `generate_study_plan` tool - output a 7-day study suggestion
- [ ] Add `match_exercises_to_weak_topics` helper to auto-match CSV exercises
- [ ] Format recommendations for parent-friendly output (plain text, no jargon)

### Week 8: Exercise Generation from LLM

- [ ] Implement `generate_exercises_llm` tool using EXERCISE_GENERATOR_PROMPT
- [ ] Parse LLM JSON output into CsvExerciseRow objects
- [ ] Validate generated exercises against schema before saving
- [ ] Implement `import_exercises_to_db` end-to-end (tool 8)
- [ ] Test full flow: weak topic identified -> exercises generated -> imported to DB

### Week 9: Voice Input Support

- [ ] Research and select speech-to-text API (Google Speech or Whisper)
- [ ] Add `POST /api/transcribe` endpoint to convert audio to text
- [ ] Update `ChatRequest` schema to accept audio file or base64 input
- [ ] Integrate transcription result into the chat flow seamlessly
- [ ] Test with Vietnamese audio samples

### Week 10: Multi-turn Conversation Memory

- [ ] Design conversation state persistence (in-memory or Redis)
- [ ] Implement session management: session_id -> conversation_history
- [ ] Update `run_agent()` to load/save session context
- [ ] Add `POST /api/session` endpoint to create/reset sessions
- [ ] Test multi-turn: parent asks follow-up questions across multiple messages
- [ ] Ensure agent remembers child_id and intent throughout a session

---

## Month 3: Integration, Quality, and Deployment (Weeks 11-13)

Focus: Connect to Next.js frontend, improve output quality, prepare for demo.

### Week 11: Next.js Frontend Integration

- [ ] Create Next.js API route: `POST /api/agent/chat` (proxy to FastAPI)
- [ ] Build chat UI component for parent dashboard (consultant mode)
- [ ] Build tutor chat component for student exercise page
- [ ] Display agent tool execution status ("Fetching student data...")
- [ ] Handle streaming SSE events in the frontend (token-by-token display)
- [ ] Implement error states and retry logic in the UI

### Week 12: Quality Improvement and Evaluation

- [ ] Create evaluation dataset: 20 sample parent queries with expected outputs
- [ ] Define evaluation metrics:
  - Correctness: does the agent use real data from DB?
  - Relevance: are recommended exercises related to weak topics?
  - Clarity: is the recommendation understandable for parents?
- [ ] Run evaluation, identify failure modes
- [ ] Tune LLM prompts based on evaluation results
- [ ] Improve weak topic detection (adjust 60% threshold, add minimum attempts filter)
- [ ] Add safety guardrails: agent must not invent student data

### Week 13: Deployment and Documentation

- [ ] Write Dockerfile for the FastAPI service
- [ ] Write docker-compose.yml to run Agent Service + Supabase together
- [ ] Configure environment variables for production (Supabase hosted URL)
- [ ] Deploy to a test environment (Railway, Render, or VPS)
- [ ] Perform end-to-end integration test on deployed environment
- [ ] Write API documentation (OpenAPI/Swagger already auto-generated by FastAPI)
- [ ] Record demo video showing:
  1. Parent logs in and asks "How is my child doing?"
  2. Agent uses tools to fetch real data and generates report
  3. Parent asks for exercise recommendations
  4. Agent recommends targeted exercises based on weak topics
- [ ] Finalize thesis documentation

---

## Key Milestones

| Milestone | Target Date | Deliverable |
|-----------|-------------|-------------|
| M1: Base commit | End of Week 4 | Running agent loop + Supabase data access |
| M2: Recommendation flow | End of Week 8 | Full pipeline: parent input -> student data -> suggestions |
| M3: Voice support | End of Week 9 | Vietnamese voice input transcription |
| M4: Full session memory | End of Week 10 | Multi-turn conversation with context |
| M5: Frontend integrated | End of Week 11 | Chat UI in Next.js parent dashboard |
| M6: Demo-ready | End of Week 13 | Deployed, tested, documented |

---

## Architecture Reference

```
Parent (Next.js) <-> FastAPI Agent Service <-> LangGraph Graph
                                                     |
                                              ┌──────┴──────┐
                                              | MCP Tools   |
                                              | (server.py) |
                                              └──────┬──────┘
                                                     |
                                              Supabase DB + CSV files
```

**MCP tools act as the data layer** between the LLM agent and the database.
The agent never queries the DB directly - it calls tools which then query Supabase.

---

## Notes for Thesis

- This project demonstrates practical application of the Model Context Protocol
- LangGraph provides structured, debuggable agent flow vs. free-form agents
- The Consultant + Tutor dual-persona design addresses both parent and student UX
- All student data access goes through service-role key (bypasses RLS safely)
- Vietnamese language support is built into all prompts and responses
