import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from memory.embedding import EmbeddingClient
from memory.store import MemoryStore, Memory

DOCS_DIR = Path("docs")   # directory containing .md files
TENANT_ID = "docs-agent"


def load_markdown_files(directory: Path) -> list[tuple[str, str]]:
    """Return (filename, text) pairs for every .md file found recursively."""
    results = []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            results.append((path.name, text))
    return results


async def seed():
    settings = get_settings()
    embedder = EmbeddingClient(settings.embedding, llm_api_key=settings.llm.api_key)
    store = MemoryStore(settings.memory, embedder)

    await store.ensure_collection(dimensions=settings.embedding.dimensions)

    files = load_markdown_files(DOCS_DIR)
    if not files:
        print(f"No .md files found under {DOCS_DIR}")
        return

    for i, (filename, text) in enumerate(files):
        await store.store(Memory(
            text=text,
            tenant_id=TENANT_ID,
            session_id="seed",
        ))
        print(f"Seeded [{i + 1}/{len(files)}]: {filename} ({len(text)} chars)")

    print(f"\nDone — {len(files)} files stored in Qdrant under tenant '{TENANT_ID}'")


asyncio.run(seed())