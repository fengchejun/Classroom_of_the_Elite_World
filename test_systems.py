"""
Diagnose: 事件系统 + 点数结算系统 是否正常触发
"""
import asyncio, json, sys
sys.path.insert(0, "src")

from src.db import init_db, async_session
from src.models.game_session import GameSession
from src.models.event import Event, EventPhase
from sqlalchemy import select

async def test_settlement():
    """Test the daily point settlement system."""
    print("=" * 60)
    print("TEST 1: daily_point_settlement()")
    print("=" * 60)
    from src.web_server import daily_point_settlement, CHARACTER_LIBRARY

    # Check a few characters' initial points
    samples = ["绫小路清隆", "堀北铃音", "须藤健", "轻井泽惠"]
    print("\n[Before settlement]")
    for name in samples:
        c = CHARACTER_LIBRARY.get(name, {})
        print(f"  {name}: PP={c.get('private_points', '?')}, habit={c.get('spending_habit', '?')}, tags={c.get('status_tags', [])}")

    # Run settlement
    result = await daily_point_settlement("2024-04-02")
    print(f"\n[Settlement result] {json.dumps(result, ensure_ascii=False)}")

    print("\n[After settlement]")
    for name in samples:
        c = CHARACTER_LIBRARY.get(name, {})
        print(f"  {name}: PP={c.get('private_points', '?')}, tags={c.get('status_tags', [])}")

    # Check if any transactions were recorded
    async with async_session() as db:
        from src.models.transaction import TransactionLog
        r = await db.execute(select(TransactionLog).limit(5))
        txs = r.scalars().all()
        print(f"\n[TransactionLog] {len(txs)} records in DB")
        for tx in txs[:5]:
            print(f"  {tx.char_name}: {tx.amount} PP ({tx.category}) on {tx.game_date}")

async def test_events():
    """Test the event system."""
    print("\n" + "=" * 60)
    print("TEST 2: Event trigger detection")
    print("=" * 60)

    async with async_session() as db:
        # Check what events exist in DB
        r = await db.execute(select(Event))
        events = r.scalars().all()
        print(f"\n[Events in DB] {len(events)} total")
        for ev in events:
            print(f"  {ev.template_id}: name={ev.name}, phase={ev.phase.value if ev.phase else '?'}, "
                  f"is_active={ev.is_active}, date={ev.required_date}, "
                  f"loc={ev.required_location}, slot={ev.required_time_slot}")

        # Import events from config if DB is empty
        if not events:
            print("\n[!] No events in DB, importing from config...")
            from src.core.event_bus.bus import EventBus
            bus = EventBus(db)
            count = await bus.load_from_config()
            await db.commit()
            print(f"[+] Imported {count} events")

            r = await db.execute(select(Event))
            events = r.scalars().all()
            print(f"[Events in DB after import] {len(events)}")

        # Check triggers for the current game state
        from src.core.event_bus.bus import EventBus
        bus = EventBus(db)
        # Get current game date from active session
        r = await db.execute(select(GameSession).where(GameSession.is_active == True).limit(1))
        gs = r.scalar_one_or_none()
        game_date = gs.game_date if gs else "2024-04-01"
        time_slot = gs.time_slot if gs else "morning"
        location_id = gs.player_location_id if gs else "classroom_d"
        print(f"\n[Current game state] date={game_date}, slot={time_slot}, loc={location_id}")

        matches = await bus.check_triggers(location_id, game_date, time_slot)
        print(f"[Trigger matches] {len(matches)} found")
        for m in matches:
            print(f"  - {m.event.name} (type={m.match_type}, priority={m.priority})")

        # Also check lifecycle advancement
        print("\n[Testing lifecycle advance to 2024-04-02]")
        advs = await bus.advance_lifecycle("2024-04-02")
        print(f"[Lifecycle advancements] {len(advs)}")
        for a in advs:
            print(f"  - {a.event_id}: {a.old_phase} -> {a.new_phase}")

async def test_date_change_detection():
    """Test whether date change detection works."""
    print("\n" + "=" * 60)
    print("TEST 3: Date change detection in _apply_state_changes")
    print("=" * 60)
    from src.web_server import _apply_state_changes

    async with async_session() as db:
        r = await db.execute(select(GameSession).where(GameSession.is_active == True).limit(1))
        gs = r.scalar_one_or_none()
        if gs is None:
            print("No active game session found")
            return
        print(f"  Before: date={gs.game_date}, slot={gs.time_slot}")

        # Test sleep_to_morning
        _apply_state_changes(gs, {"sleep_to_morning": True, "new_time_slot": "morning"})
        print(f"  After sleep_to_morning: date={gs.game_date}, slot={gs.time_slot}")
        print(f"  _pending_settlement = {getattr(gs, '_pending_settlement', None)}")

async def main():
    await init_db()
    await test_settlement()
    await test_events()
    await test_date_change_detection()
    print("\n" + "=" * 60)
    print("DIAGNOSIS COMPLETE")

if __name__ == "__main__":
    asyncio.run(main())
