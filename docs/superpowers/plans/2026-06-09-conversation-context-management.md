# Conversation Context Management Plan

## Goal

Build a production-oriented chat context layer for the audit assistant:

- Keep recent multi-turn conversation messages in model calls.
- Maintain a rolling compressed summary for older turns.
- Include full text from files uploaded for the current user turn only.
- Include historical attachment summaries instead of full historical file text.
- Keep retrieved RAG evidence in the system prompt.
- Enforce a deterministic context budget before calling the LLM.

## Implementation

1. Add tests for context assembly, memory compression, and answer service message payloads.
2. Add a `conversation_memories` table and SQLAlchemy model.
3. Add `chat_context` services for budget handling, deterministic summarization, and message assembly.
4. Wire `answer_question` to send full message lists instead of only system + current question.
5. Update chat route to pass the current conversation and user message id, then refresh rolling memory after the assistant reply is stored.
6. Run backend tests, lint, and frontend build checks.

