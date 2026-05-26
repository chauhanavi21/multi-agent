"""Smoke test — verifies Phase 2 wiring without needing Ollama running.

Run: python -m app.smoke_test
"""
import asyncio
from app.agents import registry


async def main():
    print("=== Agent registry ===")
    for w in registry.list_workers():
        print(f"  {w.spec.name:20} {w.spec.display_name:25} actions={w.spec.actions}")

    print()
    print("=== Capabilities prompt (what the manager sees) ===")
    print(registry.capabilities_prompt())

    print()
    print("=== DB tables ===")
    from app.db.models import engine
    from sqlalchemy import inspect
    insp = inspect(engine)
    for t in sorted(insp.get_table_names()):
        cols = [c["name"] for c in insp.get_columns(t)]
        print(f"  {t:22} {cols}")

    print()
    print("OK — wiring looks good. Run the server with: uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    asyncio.run(main())
