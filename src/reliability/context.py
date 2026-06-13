from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def _estimate_tokens(messages: list[BaseMessage]) -> int:
    total_chars = sum(
        len(m.content) if isinstance(m.content, str) else 0
        for m in messages
    )
    return total_chars // 4


class ContextManager:
    def __init__(
        self,
        llm: object,
        threshold_tokens: int,
        preserve_last_n: int = 4,
    ) -> None:
        self._llm = llm
        self._threshold = threshold_tokens
        self._preserve_last_n = preserve_last_n

    async def maybe_summarise(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if _estimate_tokens(messages) <= self._threshold:
            return messages

        # Always keep: system message (if first) + last N messages.
        system_msgs: list[BaseMessage] = []
        rest: list[BaseMessage] = messages

        if messages and isinstance(messages[0], SystemMessage):
            system_msgs = [messages[0]]
            rest = messages[1:]

        tail = rest[-self._preserve_last_n:] if len(rest) > self._preserve_last_n else rest
        middle = rest[: len(rest) - len(tail)]

        if not middle:
            return messages

        summary_text = await self._summarise_chunk(middle)
        summary_msg = AIMessage(content=f"[Summary of earlier conversation]: {summary_text}")
        return system_msgs + [summary_msg] + tail

    async def _summarise_chunk(self, messages: list[BaseMessage]) -> str:
        text_parts = [
            f"{type(m).__name__}: {m.content}"
            for m in messages
            if isinstance(m.content, str)
        ]
        conversation_text = "\n".join(text_parts)

        prompt = [
            {
                "role": "user",
                "content": (
                    "Summarise the following conversation in 2-3 sentences, "
                    "preserving key facts and decisions:\n\n" + conversation_text
                ),
            }
        ]
        response = await self._llm.complete(prompt)  # type: ignore[union-attr]
        return response.choices[0].message.content or ""
