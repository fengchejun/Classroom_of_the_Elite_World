"""Import extracted JSON data directly into the database and CHARACTER_LIBRARY."""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import async_session, init_db
from src.core.event_bus.bus import EventBus


CHARACTER_LIBRARY = {}
LOCATIONS = {}

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


async def import_worldview():
    path = OUTPUT_DIR / "worldview_extracted.json"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    dest = Path(__file__).resolve().parent.parent / "src" / "config" / "data" / "worldview_extracted.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data["data"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Worldview saved to: {dest}")


async def import_characters():
    path = OUTPUT_DIR / "characters_extracted.json"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for entry in data["data"]:
        name = entry.get("name", "")
        if name and name not in CHARACTER_LIBRARY:
            CHARACTER_LIBRARY[name] = {
                "role_id": entry.get("role_id", f"imported_{name}"),
                "class_name": entry.get("class_name", "D"),
                "enrollment_year": entry.get("enrollment_year", "2024"),
                "traits": entry.get("traits", []),
                "public_info": entry.get("public_info", []),
                "secrets": entry.get("secrets", []),
                "relations": entry.get("relations", []),
            }
            count += 1
    print(f"  Characters loaded into library: {count} new (total: {len(CHARACTER_LIBRARY)})")


async def import_locations():
    path = OUTPUT_DIR / "locations_extracted.json"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for entry in data["data"]:
        lid = entry.get("location_id", "")
        if lid and lid not in LOCATIONS:
            LOCATIONS[lid] = {
                "location_id": lid,
                "name": entry.get("name", lid),
                "description": entry.get("description", ""),
                "tags": entry.get("tags", []),
                "connected_to": entry.get("connected_to", []),
                "zone_id": entry.get("zone_id", ""),
            }
            count += 1
    print(f"  Locations loaded: {count} new (total: {len(LOCATIONS)})")


async def import_events():
    path = OUTPUT_DIR / "events_enriched.json"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("data", {})
    print(f"  Events to import: {len(events)}")

    async with async_session() as db:
        bus = EventBus(db)
        count = 0
        errors = 0
        for event_id, definition in events.items():
            try:
                await bus._upsert_event(event_id, definition)
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"    ERROR [{event_id}]: {e}")

        await db.commit()
        print(f"  Events imported: {count} (errors: {errors})")


async def main():
    print("Initializing database...")
    await init_db()

    print("\nImporting worldview...")
    await import_worldview()

    print("\nImporting characters...")
    await import_characters()

    print("\nImporting locations...")
    await import_locations()

    print("\nImporting events...")
    await import_events()

    # Verify
    import sqlite3
    conn = sqlite3.connect("elite_simulator.db")
    events_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    print(f"\n{'='*50}")
    print(f"  Import complete!")
    print(f"  Events in DB: {events_count}")
    print(f"  Characters in library: {len(CHARACTER_LIBRARY)}")
    print(f"  Locations in memory: {len(LOCATIONS)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
