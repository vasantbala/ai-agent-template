import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from memory.embedding import EmbeddingClient
from memory.store import MemoryStore, Memory

DOCS_DIR = Path("docs")   # directory containing .md files
TENANT_ID = "docs-agent"


def split_by_heading(text: str) -> list[str]:
    """Split markdown into sections on h1/h2/h3 headings."""
    sections = re.split(r'\n(?=#{1,3} )', text.strip())
    return [s.strip() for s in sections if s.strip()]


def load_chunks(directory: Path) -> list[tuple[str, str]]:
    """Return (label, chunk) pairs for every .md file found recursively."""
    chunks = []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        for i, section in enumerate(split_by_heading(text)):
            chunks.append((f"{path.name}§{i + 1}", section))
    return chunks


async def seed():
    settings = get_settings()
    embedder = EmbeddingClient(
        settings.embedding,
        llm_api_key=settings.llm.api_key,
        llm_provider=settings.llm.provider,
        llm_base_url=settings.llm.base_url,
    )
    store = MemoryStore(settings.memory, embedder)

    await store.ensure_collection(dimensions=settings.embedding.dimensions)

    chunks = load_chunks(DOCS_DIR)
    if not chunks:
        print(f"No .md files found under {DOCS_DIR}")
        return

    for i, (label, chunk) in enumerate(chunks):
        await store.store(Memory(
            text=chunk,
            tenant_id=TENANT_ID,
            session_id="seed",
        ))
        print(f"Seeded [{i + 1}/{len(chunks)}]: {label} ({len(chunk)} chars)")

    print(f"\nDone — {len(chunks)} chunks from {DOCS_DIR} stored under tenant '{TENANT_ID}'")


asyncio.run(seed())
