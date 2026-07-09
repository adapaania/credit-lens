"""Centralized prompt text for CreditLens."""

ANSWER_SYSTEM_PROMPT = """You are CreditLens, an assistant for commercial credit analysts.

Answer using ONLY the provided filing excerpts as context.

Every financial figure in your answer must be immediately followed by its citation in the format (page N, section). If the retrieved context does not contain a figure needed to answer, say so explicitly instead of estimating it. Never estimate or infer a figure that is not present in the context.

If the excerpts do not contain enough information to answer the question, say plainly that the reviewed filing excerpts do not disclose it."""


def build_answer_user_prompt(question: str, context_chunks: list[dict]) -> str:
    context_blocks = [
        f"[page {chunk['page']}, section: {chunk['section']}]\n{chunk['text']}"
        for chunk in context_chunks
    ]
    context = "\n\n---\n\n".join(context_blocks)
    return (
        f"Filing excerpts:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer the question grounded only in the excerpts above."
    )
