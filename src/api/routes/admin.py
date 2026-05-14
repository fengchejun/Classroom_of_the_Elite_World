from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.core.event_bus.bus import EventBus
from src.core.persona_graph.character import CharacterManager
from src.models import Character, Location, Secret
from src.utils.logger import get_logger

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = get_logger(__name__)


class ImportCharactersRequest(BaseModel):
    file_path: str | None = None  # defaults to config/data/characters.json


@router.post("/import/characters")
async def import_characters(
    req: ImportCharactersRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import characters from a JSON file."""
    path = req.file_path or str(
        Path(__file__).parent.parent.parent / "config" / "data" / "characters.json"
    )

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    chars = data.get("characters", data if isinstance(data, list) else [])
    mgr = CharacterManager(db)
    imported = []
    for cdata in chars:
        char = await mgr.create_character(cdata)
        imported.append(char.role_id)

    await db.commit()
    return {"imported": len(imported), "characters": imported}


@router.post("/import/events")
async def import_events(
    db: AsyncSession = Depends(get_db),
):
    """Load events from events_config.json into the database."""
    bus = EventBus(db)
    count = await bus.load_from_config()
    await db.commit()
    return {"imported_events": count}


@router.post("/import/locations")
async def import_locations(
    db: AsyncSession = Depends(get_db),
):
    """Import locations from world_map.txt."""
    map_path = Path(__file__).parent.parent.parent / "config" / "data" / "world_map.txt"
    if not map_path.exists():
        raise HTTPException(status_code=404, detail="world_map.txt not found")

    # Simple import: create a basic set of locations
    default_locations = [
        {"location_id": "classroom_d", "name": "D班教室", "description": "高度育成高中一年D班的教室。桌椅有些陈旧，黑板上偶尔还残留着上节课的板书。教室后排靠窗的位置能看到校园的中庭。", "tags": ["indoor", "classroom"], "connected_to": ["hallway_1f", "corridor_d"]},
        {"location_id": "school_bus", "name": "校车", "description": "往返于学校和市区的校车。每天早晚各一班。车内空间不算宽敞，座位常常不够用。", "tags": ["indoor", "vehicle"], "connected_to": ["school_gate", "shopping_district"]},
        {"location_id": "school_gymnasium", "name": "体育馆", "description": "宽敞的室内体育馆，可容纳全校学生。配备了可移动的舞台和最新的音响设备。", "tags": ["indoor", "large"], "connected_to": ["school_field", "hallway_1f"]},
        {"location_id": "library", "name": "图书馆", "description": "学校的图书馆藏书丰富，从古典文学到最新期刊应有尽有。靠窗的自习区总是座无虚席。", "tags": ["indoor", "quiet"], "connected_to": ["hallway_3f"]},
        {"location_id": "cafeteria", "name": "学生食堂", "description": "学校食堂提供丰富多样的套餐，可以用个人点数支付。午餐时间总是人满为患。", "tags": ["indoor", "noisy"], "connected_to": ["hallway_1f", "school_field"]},
        {"location_id": "school_field", "name": "操场", "description": "标准的田径运动场，周围是400米的跑道。足球部和田径部经常在这里训练。", "tags": ["outdoor", "sports"], "connected_to": ["school_gymnasium", "cafeteria"]},
        {"location_id": "rooftop", "name": "天台", "description": "教学楼顶层的天台。虽然上了锁，但偶尔会有人忘记关。这里视野开阔，能俯瞰整个校园。", "tags": ["outdoor", "secluded"], "connected_to": ["hallway_5f"]},
        {"location_id": "dormitory", "name": "学生宿舍", "description": "学校为学生提供的单人宿舍。虽然不大，但设施齐全。晚上有门禁，超过规定时间需要特殊权限才能出入。", "tags": ["indoor", "private"], "connected_to": ["school_gate"]},
        {"location_id": "school_gate", "name": "校门", "description": "高度育成高中的正门。平时有保安值守，学生出入需要刷学生卡。", "tags": ["outdoor"], "connected_to": ["school_bus", "dormitory", "hallway_1f"]},
        {"location_id": "hallway_1f", "name": "一楼走廊", "description": "教学楼一楼的走廊，连接着各个功能教室和办公室。墙上贴着各种社团的海报和通知。", "tags": ["indoor", "corridor"], "connected_to": ["classroom_d", "school_gymnasium", "cafeteria", "school_gate", "hallway_3f", "hallway_5f"]},
        {"location_id": "hallway_3f", "name": "三楼走廊", "description": "教学楼三楼的走廊。这里比一楼安静得多，偶尔有小团体在这里密谈。", "tags": ["indoor", "corridor", "quiet"], "connected_to": ["hallway_1f", "library"]},
        {"location_id": "hallway_5f", "name": "五楼走廊", "description": "教学楼顶层的走廊。通往天台的门通常锁着，但这里依然是想要独处的学生的好去处。", "tags": ["indoor", "corridor", "secluded"], "connected_to": ["hallway_1f", "rooftop"]},
        {"location_id": "special_building", "name": "特别教学楼", "description": "学校深处的一栋独立建筑，用于举办特别考试和集会。平时大门紧闭。", "tags": ["indoor", "restricted"], "connected_to": ["school_field"]},
    ]

    for loc_data in default_locations:
        result = await db.execute(
            __import__("sqlalchemy").select(Location).where(
                Location.location_id == loc_data["location_id"]
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in loc_data.items():
                setattr(existing, k, v)
        else:
            db.add(Location(**loc_data))

    await db.commit()
    return {"imported_locations": len(default_locations)}


@router.get("/health")
async def admin_health():
    return {"status": "admin_ok"}
