"""
Extract structured data (characters, locations, worldview, events) from
《实力至上主义教室》full novel series via DeepSeek API.

Usage:
    py scripts/extract_novel_data.py          # run full extraction
    py scripts/extract_novel_data.py --dry-run  # count volumes only
    py scripts/extract_novel_data.py --type characters  # extract one type
    py scripts/extract_novel_data.py --resume  # skip volumes with cached results

Output: scripts/output/{characters,locations,worldview,events}_extracted.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ---- config ----

NOVEL_BASE = Path(r"C:\Users\FengCheJun\Desktop\爬取小说\我的小说正文")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
CACHE_DIR = OUTPUT_DIR / ".cache"

DEEPSEEK_API_KEY = "sk-a027465f568346db99147bb047d7a643"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-chat"
LLM_MAX_TOKENS = 8192
LLM_TEMPERATURE = 0.3  # low temperature for structured extraction

RATE_LIMIT_SEC = 3.0  # pause between API calls
MAX_RETRIES = 3

# Anchor: May 1st, Year 1 (一年级5月1日)
# enrollment_year mapping:
#   "2024" = same cohort as protagonist (Y1 at anchor)
#   "2023" = one year above (Y2 at anchor)
#   "2022" = two years above (Y3 at anchor, graduated after anchor year)
#   "2025" = one year below (not yet enrolled at anchor)
#   "2026" = two years below (not yet enrolled at anchor)

# ---- helpers ----

def get_volumes() -> list[tuple[str, Path]]:
    """Return sorted list of (volume_name, volume_path)."""
    vols = []
    for d in sorted(NOVEL_BASE.iterdir()):
        if d.is_dir():
            vols.append((d.name, d))
    return vols


def read_volume(vol_path: Path) -> str:
    """Concatenate all .txt files in a volume directory, sorted by filename."""
    files = sorted(f for f in vol_path.iterdir() if f.suffix.lower() == ".txt")
    parts = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
            parts.append(f"=== {fp.stem} ===\n\n{text}\n")
        except Exception as e:
            print(f"  [WARN] Failed to read {fp.name}: {e}")
    return "\n".join(parts)


def read_keywords_only(vol_path: Path) -> str:
    """Read only KEYWORDS/glossary files from a volume."""
    files = sorted(f for f in vol_path.iterdir()
                   if f.suffix.lower() == ".txt" and "keyword" in f.stem.lower())
    parts = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
            parts.append(f"=== {fp.stem} ===\n\n{text}\n")
        except Exception:
            pass
    return "\n".join(parts)


def chunk_text(text: str, max_chars: int = 80000) -> list[str]:
    """Split text into chunks at chapter boundaries if too long."""
    if len(text) <= max_chars:
        return [text]
    chapters = re.split(r'(=== \d+_.*? ===)', text)
    chunks = []
    current = ""
    i = 0
    while i < len(chapters):
        if len(current) + len(chapters[i]) > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += chapters[i]
        i += 1
    if current.strip():
        chunks.append(current.strip())
    return chunks


def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = LLM_MAX_TOKENS) -> str | None:
    """Call DeepSeek API, return response text or None on failure."""
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=LLM_TEMPERATURE,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"    API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt * 2)
    return None


def extract_json_from_response(text: str) -> dict | None:
    """Extract JSON object from LLM response that may contain markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract from ```json ... ``` fence
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the outermost { or [
    for start, end in [('{', '}'), ('[', ']')]:
        idx_start = text.find(start)
        idx_end = text.rfind(end)
        if idx_start != -1 and idx_end > idx_start:
            try:
                return json.loads(text[idx_start:idx_end + 1])
            except json.JSONDecodeError:
                pass

    print(f"    [WARN] Could not parse JSON from response (first 200 chars): {text[:200]}")
    return None


def save_json(data, filename: str):
    """Save data to OUTPUT_DIR/filename with pretty formatting."""
    path = OUTPUT_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {path}")


def cache_path(vol_name: str, data_type: str) -> Path:
    """Path for per-volume cached extraction result."""
    safe = re.sub(r'[^\w\-.]', '_', vol_name)
    return CACHE_DIR / f"{safe}_{data_type}.json"


def load_cache(vol_name: str, data_type: str) -> dict | None:
    """Load cached extraction result for a volume."""
    cp = cache_path(vol_name, data_type)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_cache(vol_name: str, data_type: str, data: dict):
    """Cache per-volume extraction result."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp = cache_path(vol_name, data_type)
    cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- prompts ----

WORLDVIEW_SYSTEM_PROMPT = """你是一个数据提取专家。你的任务是从《实力至上主义教室》小说的术语解释/世界观设定章节中提取结构化的世界观信息。

**时间锚点**：一年级5月1日（入学一个月后，D班点数归零）。

**输出格式**（严格JSON，不要添加任何解释或markdown）：
{
  "type": "worldview",
  "data": {
    "school_name": "高度育成高等学校",
    "founding_principles": "学校的创立理念和真实目的...",
    "class_system": {
      "description": "四个班级按实力竞争的机制...",
      "classes": ["A", "B", "C", "D"],
      "ranking_mechanism": "班级点数的评定和升降规则..."
    },
    "s_point_system": {
      "description": "S点数的完整规则...",
      "monthly_allocation": "每月分配公式",
      "transfer_rules": ["可转让", "可交易"],
      "usage_scope": "可在校园内所有设施使用"
    },
    "special_exam_overview": "特别考试的总体说明...",
    "rules": [
      {"name": "规则名称", "content": "规则内容...", "source": "出处说明"}
    ]
  }
}

提取规则：
1. 优先从术语解释章节提取（通常带有KEYWORDS字样）
2. 记录所有校园制度、规则体系、考试制度
3. 以5月1日时已知的规则为准，后续新增规则标注出处
4. 规则信息要完整，不要遗漏细节"""

CHARACTER_SYSTEM_PROMPT = """你是一个数据提取专家。从《实力至上主义教室》小说中提取角色信息。

**时间锚点**：一年级5月1日（入学一个月后）。所有角色关系以此时间为准。
**入学年份体系**（以主角绫小路清隆=2024为基准）：
- "2024"：与主角同级（锚点时读一年级）
- "2023"：高主角一级（锚点时读二年级）
- "2022"：高主角两级（锚点时读三年级）
- "2025"：低主角一级（锚点时未入学）
- "2026"：低主角两级（锚点时未入学）

**输出格式**（严格JSON数组，不要添加任何解释或markdown）：
{
  "type": "characters",
  "data": [
    {
      "name": "角色全名",
      "role_id": "pinyin_or_en_snake_case",
      "class_name": "A/B/C/D 或 毕业生/未入学",
      "enrollment_year": "2024",
      "traits": ["性格标签1", "性格标签2", ...],
      "public_info": [
        {"label": "外貌", "content": "..."},
        {"label": "身份", "content": "一年D班学生..."},
        {"label": "性格", "content": "..."}
      ],
      "secrets": [
        {"info_id": "unique_id", "content": "不为人知的秘密...", "known_by": ["who_knows"]}
      ],
      "relations": [
        {"to": "对方角色名", "type": "trust/hostile/rival/subservient/crush/friend/neutral", "reason": "5月1日时两人关系的因果描述"}
      ]
    }
  ]
}

提取规则：
1. 只提取有名字（全名）且有台词/有存在感的角色，路人忽略
2. role_id用英文或拼音，小写+下划线，如"horikita_suzune"
3. class_name：D班学生填"D"，C班填"C"，依此类推；毕业生填"已毕业"，未入学填"未入学"
4. 对5月1日时尚未登场的角色，合理推断其当时的状态和所在
5. relations只记录5月1日时已存在的关系
6. secrets的known_by用role_id列表
7. public_info每条用label+content格式，3-6条"""

COMBINED_SYSTEM_PROMPT = """你是一个数据提取专家。从《实力至上主义教室》小说中同时提取角色和地点信息。

**时间锚点**：一年级5月1日（入学一个月后，D班点数归零）。
**入学年份体系**（以主角绫小路清隆=2024为基准）：
- "2024"：与主角同级（锚点时读一年级）
- "2023"：高主角一级（锚点时读二年级）
- "2022"：高主角两级（锚点时读三年级）
- "2025"：低主角一级（锚点时未入学）
- "2026"：低主角两级（锚点时未入学）

**输出格式**（严格JSON，同时包含characters和locations两个key，不要添加任何解释或markdown）：
{
  "characters": [
    {
      "name": "角色全名",
      "role_id": "pinyin_or_en_snake_case",
      "class_name": "A/B/C/D",
      "enrollment_year": "2024",
      "traits": ["性格标签1", "性格标签2", ...],
      "public_info": [
        {"label": "外貌", "content": "..."},
        {"label": "身份", "content": "一年D班学生..."},
        {"label": "性格", "content": "..."}
      ],
      "secrets": [
        {"info_id": "unique_snake_case_id", "content": "不为人知的秘密...", "known_by": ["role_id"]}
      ],
      "relations": [
        {"to": "对方角色全名", "type": "trust/hostile/rival/subservient/crush/friend/neutral/family", "reason": "简洁说明5月1日时的关系"}
      ]
    }
  ],
  "locations": [
    {
      "location_id": "english_snake_case_id",
      "name": "地点中文名",
      "description": "从小说原文提炼的环境描写（氛围、用途、位置等）",
      "tags": ["indoor/outdoor", "quiet/noisy/secluded/restricted/..."],
      "connected_to": ["相邻地点location_id"],
      "zone_id": "teaching_building/sports_area/dormitory/campus/off_campus"
    }
  ]
}

提取规则：
- 角色：只提取有全名且有存在感的角色；relations只记录5月1日时已存在的关系；secrets用有意义的info_id
- 地点：提取所有校园及周边重要场所；description要有小说原文的场景感；connected_to用location_id
- 时间：5月1日时尚未登场角色，推断其当时应有状态"""

EVENT_SYSTEM_PROMPT = """你是一个数据提取专家。从《实力至上主义教室》小说中提取重要事件/考试信息。

**时间体系**：主角绫小路清隆于2024年4月入学。一年级=2024-04至2025-03，二年级=2025-04至2026-03，三年级=2026-04起。
时间槽：morning（早上）/ noon（中午）/ dusk（傍晚）/ evening（晚上）/ late_night（深夜）。

**输出格式**（严格JSON对象，key为event_id，不要添加任何解释或markdown）：
{
  "type": "events",
  "data": {
    "event_id_here": {
      "name": "事件中文名称",
      "type": "ai_guided_choice 或 fixed_story 或 silent_fixed",
      "trigger_conditions": {
        "required_date": "YYYY-MM-DD",
        "required_time_slot": "morning/noon/dusk/evening/late_night (可选)",
        "required_location": "location_id (可选)",
        "prerequisite_events": ["前置事件id列表 (可选)"]
      },
      "foreshadow_start_date": "YYYY-MM-DD (可选)",
      "foreshadow_probability": 0.3,
      "foreshadow_prompt": "铺垫期LLM引导文本 (可选)",
      "transition_date": "YYYY-MM-DD (可选)",
      "ai_setup_prompt": "事件触发时的强制演出描写指令 (可选)",
      "active_start_date": "YYYY-MM-DD",
      "active_end_date": "YYYY-MM-DD",
      "active_prompt": "事件活跃期间的LLM上下文注入文本 (可选)",
      "rules_appendix": "关联规则书key (可选)",
      "options": [],
      "silent_effects": {}
    }
  }
}

提取规则：
1. 只提取重要事件：特别考试、班级对抗、重大冲突、角色转折点
2. event_id用英文snake_case
3. 日期必须推断出精确的YYYY-MM-DD，如果原文只提月份，推测一个合理日期
4. 时段根据事件发生的时间段推断（morning/noon/dusk/evening/late_night）
5. 地点用location_id（英文snake_case）
6. type判定：玩家有选择的=ai_guided_choice，纯剧情推进=fixed_story，幕后自动生效=silent_fixed
7. 如果事件有明确的考试规则，记录rules_appendix对应的规则key
8. 选项类事件（ai_guided_choice）的options可先留空数组"""

# ---- extractors ----

def extract_worldview() -> dict:
    """Extract worldview from KEYWORDS chapters across all volumes."""
    print("\n" + "=" * 60)
    print("  Phase 1: Extracting WORLDVIEW from KEYWORDS chapters")
    print("=" * 60)

    # Collect all KEYWORDS chapters
    all_keywords = ""
    vols = get_volumes()
    for vname, vpath in vols:
        kw = read_keywords_only(vpath)
        if kw.strip():
            all_keywords += f"\n=== 来自 {vname} ===\n{kw}\n"

    # Also include first 2 volumes for context
    for vname, vpath in vols[:2]:
        text = read_volume(vpath)
        all_keywords += f"\n=== {vname} 正文摘要 ===\n{text[:30000]}\n"

    print(f"  Total worldview source: {len(all_keywords)} chars")

    # Chunk if needed (unlikely for keywords, but be safe)
    chunks = chunk_text(all_keywords, max_chars=100000)
    print(f"  Processing {len(chunks)} chunk(s)...")

    all_rules = []
    merged_data = {}

    for ci, chunk in enumerate(chunks):
        user_prompt = f"请从以下小说术语解释和世界观设定中提取结构化数据：\n\n{chunk}"
        if len(chunks) > 1:
            user_prompt += f"\n\n（这是第{ci+1}/{len(chunks)}部分，请提取本部分包含的世界观信息）"

        resp = call_deepseek(WORLDVIEW_SYSTEM_PROMPT, user_prompt)
        if resp is None:
            print(f"  [ERROR] Failed on chunk {ci+1}")
            continue

        parsed = extract_json_from_response(resp)
        if parsed:
            data = parsed.get("data", parsed)
            if ci == 0:
                merged_data = data
            else:
                # Merge rules
                new_rules = data.get("rules", [])
                existing = merged_data.get("rules", [])
                existing_names = {r.get("name") for r in existing}
                for r in new_rules:
                    if r.get("name") not in existing_names:
                        existing.append(r)
                merged_data["rules"] = existing
                # Take more detailed descriptions
                for key in ["school_name", "founding_principles", "class_system",
                           "s_point_system", "special_exam_overview"]:
                    if data.get(key) and (not merged_data.get(key) or
                       len(str(data[key])) > len(str(merged_data[key]))):
                        merged_data[key] = data[key]

        time.sleep(RATE_LIMIT_SEC)

    result = {"type": "worldview", "data": merged_data}
    save_cache("__all__", "worldview", result)
    return result


def extract_characters_and_locations_per_volume(vol_name: str, vol_path: Path) -> tuple[list, list]:
    """Extract characters and locations from a single volume (combined API call)."""
    text = read_volume(vol_path)
    print(f"  Volume text: {len(text):,} chars")

    # Check cache
    cached_chars = load_cache(vol_name, "characters")
    cached_locs = load_cache(vol_name, "locations")

    if cached_chars and cached_locs:
        print(f"  [CACHE HIT] {len(cached_chars.get('data',[]))} chars, {len(cached_locs.get('data',[]))} locs")
        return cached_chars.get("data", []), cached_locs.get("data", [])

    # For large volumes, sample front + back (most new chars/locations in early parts)
    extract_text = text[:50000] + "\n...\n" + text[-30000:] if len(text) > 80000 else text

    print(f"  Extracting characters + locations (combined)...")
    user_prompt = f"请从以下小说内容中同时提取所有角色和地点：\n\n{extract_text}"
    resp = call_deepseek(COMBINED_SYSTEM_PROMPT, user_prompt, max_tokens=LLM_MAX_TOKENS)

    chars = []
    locs = []
    if resp:
        parsed = extract_json_from_response(resp)
        if parsed:
            chars = parsed.get("characters", [])
            locs = parsed.get("locations", [])
            print(f"    Found {len(chars)} characters, {len(locs)} locations")
            save_cache(vol_name, "characters", {"type": "characters", "data": chars})
            save_cache(vol_name, "locations", {"type": "locations", "data": locs})
        else:
            print(f"    Failed to parse combined response")
            save_cache(vol_name, "characters", {"type": "characters", "data": []})
            save_cache(vol_name, "locations", {"type": "locations", "data": []})
    else:
        save_cache(vol_name, "characters", {"type": "characters", "data": []})
        save_cache(vol_name, "locations", {"type": "locations", "data": []})

    return chars, locs


def extract_events_per_volume(vol_name: str, vol_path: Path) -> list:
    """Extract events from a single volume."""
    text = read_volume(vol_path)

    cached = load_cache(vol_name, "events")
    if cached:
        print(f"  [CACHE HIT] Using cached events ({len(cached.get('data', {}))} events)")
        return cached.get("data", {})

    # Events are distributed throughout, need full text
    # Chunk if too long
    chunks = chunk_text(text, max_chars=90000)
    all_events = {}

    for ci, chunk in enumerate(chunks):
        user_prompt = f"请从以下小说内容中提取所有重要事件/特别考试：\n\n{chunk}"
        if len(chunks) > 1:
            user_prompt += f"\n\n（第{ci+1}/{len(chunks)}部分）"

        print(f"  Extracting events (chunk {ci+1}/{len(chunks)})...")
        resp = call_deepseek(EVENT_SYSTEM_PROMPT, user_prompt, max_tokens=LLM_MAX_TOKENS)
        if resp:
            parsed = extract_json_from_response(resp)
            if parsed:
                events = parsed.get("data", {})
                print(f"    Found {len(events)} events in chunk {ci+1}")
                all_events.update(events)

        time.sleep(RATE_LIMIT_SEC)

    result = {"type": "events", "data": all_events}
    save_cache(vol_name, "events", result)
    return all_events


# ---- mergers ----

def merge_characters(all_chars: list[dict]) -> list[dict]:
    """Merge characters across volumes: deduplicate by name, merge info."""
    merged: dict[str, dict] = {}

    for char in all_chars:
        name = char.get("name", "").strip()
        if not name:
            continue

        if name not in merged:
            merged[name] = {
                "name": name,
                "role_id": char.get("role_id", ""),
                "class_name": char.get("class_name", "D"),
                "enrollment_year": char.get("enrollment_year", "2024"),
                "traits": [],
                "public_info": [],
                "secrets": [],
                "relations": [],
            }

        existing = merged[name]

        # Use the more specific role_id if available
        if char.get("role_id") and (not existing["role_id"] or
           existing["role_id"].startswith("unknown")):
            existing["role_id"] = char["role_id"]

        # enrollment_year: prefer non-default
        if char.get("enrollment_year") and existing.get("enrollment_year") == "2024":
            existing["enrollment_year"] = char["enrollment_year"]

        # class_name: prefer non-D
        if char.get("class_name") and char["class_name"] != "D":
            if existing["class_name"] == "D" or existing["class_name"] == char["class_name"]:
                existing["class_name"] = char["class_name"]

        # Merge traits (deduplicate)
        for t in char.get("traits", []):
            if t not in existing["traits"]:
                existing["traits"].append(t)

        # Merge public_info (deduplicate by label)
        existing_labels = {p["label"] for p in existing["public_info"] if isinstance(p, dict)}
        for p in char.get("public_info", []):
            if isinstance(p, dict) and p.get("label") not in existing_labels:
                existing["public_info"].append(p)
                existing_labels.add(p["label"])

        # Merge secrets (deduplicate by info_id)
        existing_secrets = {s["info_id"] for s in existing["secrets"] if isinstance(s, dict)}
        for s in char.get("secrets", []):
            if isinstance(s, dict) and s.get("info_id") not in existing_secrets:
                existing["secrets"].append(s)
                existing_secrets.add(s["info_id"])

        # Merge relations (deduplicate by to+type)
        existing_rels = {(r["to"], r["type"]) for r in existing["relations"] if isinstance(r, dict)}
        for r in char.get("relations", []):
            if isinstance(r, dict) and (r["to"], r["type"]) not in existing_rels:
                existing["relations"].append(r)
                existing_rels.add((r["to"], r["type"]))

    return list(merged.values())


def merge_locations(all_locs: list[dict]) -> list[dict]:
    """Merge locations across volumes: deduplicate by location_id."""
    merged: dict[str, dict] = {}

    for loc in all_locs:
        lid = loc.get("location_id", "").strip().lower()
        if not lid:
            continue

        if lid not in merged:
            merged[lid] = {
                "location_id": lid,
                "name": loc.get("name", lid),
                "description": loc.get("description", ""),
                "tags": loc.get("tags", []),
                "connected_to": loc.get("connected_to", []),
                "zone_id": loc.get("zone_id", ""),
            }
        else:
            existing = merged[lid]
            # Keep the longer description
            if len(loc.get("description", "")) > len(existing["description"]):
                existing["description"] = loc["description"]
            # Merge tags
            for t in loc.get("tags", []):
                if t not in existing["tags"]:
                    existing["tags"].append(t)
            # Merge connected_to
            for c in loc.get("connected_to", []):
                if c not in existing["connected_to"]:
                    existing["connected_to"].append(c)
            # Better name
            if loc.get("name") and len(loc["name"]) > len(existing["name"]):
                existing["name"] = loc["name"]
            # Zone
            if loc.get("zone_id") and not existing["zone_id"]:
                existing["zone_id"] = loc["zone_id"]

    return list(merged.values())


def merge_events(all_events: list[dict]) -> dict:
    """Merge events across volumes: dict keyed by event_id."""
    merged: dict[str, dict] = {}

    for events_dict in all_events:
        if isinstance(events_dict, list):
            # Convert list to dict
            for item in events_dict:
                eid = item.get("event_id", item.get("name", ""))
                if eid:
                    merged[eid] = item
        elif isinstance(events_dict, dict):
            for eid, edata in events_dict.items():
                if eid not in merged:
                    merged[eid] = edata
                else:
                    # Merge: keep the one with more fields filled
                    existing = merged[eid]
                    for key, val in edata.items():
                        if val and not existing.get(key):
                            existing[key] = val

    return merged


# ---- main ----

def main():
    parser = argparse.ArgumentParser(description="Extract novel data via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Only list volumes, no API calls")
    parser.add_argument("--type", choices=["characters", "locations", "worldview", "events"],
                       help="Extract only a specific type")
    parser.add_argument("--resume", action="store_true", help="Skip volumes with cached results")
    parser.add_argument("--start-from", type=int, default=0,
                       help="Start from volume index (0-based)")
    parser.add_argument("--end-at", type=int, default=999,
                       help="End at volume index (exclusive)")
    args = parser.parse_args()

    # Ensure output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    vols = get_volumes()
    print(f"Found {len(vols)} volume directories")
    if args.dry_run:
        for i, (vname, vpath) in enumerate(vols):
            files = list(vpath.glob("*.txt"))
            size = sum(f.stat().st_size for f in files)
            print(f"  [{i:2d}] {vname}: {len(files)} files, {size/1024:.0f} KB")
        return

    extract_type = args.type
    resume = args.resume
    start_idx = max(0, args.start_from)
    end_idx = min(len(vols), args.end_at)
    vols = vols[start_idx:end_idx]

    all_characters = []
    all_locations = []
    all_events = []

    # ---- Phase 1: Worldview ----
    if extract_type in (None, "worldview"):
        worldview = extract_worldview()
        save_json(worldview, "worldview_extracted.json")

    if extract_type and extract_type != "worldview":
        # Skip phases if only extracting worldview
        pass

    # ---- Phase 2: Characters + Locations per volume ----
    if extract_type in (None, "characters", "locations"):
        print("\n" + "=" * 60)
        print("  Phase 2: Extracting CHARACTERS & LOCATIONS per volume")
        print("=" * 60)

        for i, (vname, vpath) in enumerate(vols):
            print(f"\n--- [{i+1}/{len(vols)}] {vname} ---")

            chars, locs = extract_characters_and_locations_per_volume(vname, vpath)
            all_characters.extend(chars)
            all_locations.extend(locs)

            # Progress save every 5 volumes
            if (i + 1) % 5 == 0:
                merged_chars = merge_characters(all_characters)
                merged_locs = merge_locations(all_locations)
                save_json({"type": "characters", "data": merged_chars},
                         "characters_extracted_partial.json")
                save_json({"type": "locations", "data": merged_locs},
                         "locations_extracted_partial.json")
                print(f"  [CHECKPOINT] Merged: {len(merged_chars)} chars, {len(merged_locs)} locs")

            time.sleep(RATE_LIMIT_SEC * 0.5)

    # ---- Phase 3: Events per volume ----
    if extract_type in (None, "events"):
        print("\n" + "=" * 60)
        print("  Phase 3: Extracting EVENTS per volume")
        print("=" * 60)

        for i, (vname, vpath) in enumerate(vols):
            print(f"\n--- [{i+1}/{len(vols)}] {vname} ---")

            events = extract_events_per_volume(vname, vpath)
            all_events.append(events)

            # Progress save every 5 volumes
            if (i + 1) % 5 == 0:
                merged_events = merge_events(all_events)
                save_json({"type": "events", "data": merged_events},
                         "events_extracted_partial.json")
                print(f"  [CHECKPOINT] Merged: {len(merged_events)} events")

            time.sleep(RATE_LIMIT_SEC * 0.5)

    # ---- Phase 4: Final Merge & Output ----
    print("\n" + "=" * 60)
    print("  Phase 4: Final Merge & Output")
    print("=" * 60)

    if extract_type in (None, "characters", "locations"):
        merged_chars = merge_characters(all_characters)
        merged_locs = merge_locations(all_locations)

        print(f"\n  Final characters: {len(merged_chars)}")
        print(f"  Final locations: {len(merged_locs)}")

        save_json({"type": "characters", "data": merged_chars}, "characters_extracted.json")
        save_json({"type": "locations", "data": merged_locs}, "locations_extracted.json")

        # Print character summary
        print("\n  Character roster:")
        for c in sorted(merged_chars, key=lambda x: (x["class_name"], x["name"])):
            print(f"    [{c['class_name']}班] {c['name']} ({c['enrollment_year']}级) "
                  f"- {', '.join(c.get('traits', [])[:4])}")

    if extract_type in (None, "events"):
        merged_events = merge_events(all_events)
        print(f"\n  Final events: {len(merged_events)}")
        save_json({"type": "events", "data": merged_events}, "events_extracted.json")

        # Print event summary
        print("\n  Event list:")
        for eid, edata in sorted(merged_events.items()):
            tc = edata.get("trigger_conditions", {})
            date = tc.get("required_date", "?")
            loc = tc.get("required_location", "?")
            etype = edata.get("type", "?")
            print(f"    [{etype}] {edata.get('name', eid)} @ {date} {loc}")

    print("\n" + "=" * 60)
    print("  Extraction complete!")
    print("  Output files:")
    for f in ["worldview_extracted.json", "characters_extracted.json",
              "locations_extracted.json", "events_extracted.json"]:
        fp = OUTPUT_DIR / f
        if fp.exists():
            print(f"    {fp} ({fp.stat().st_size:,} bytes)")
    print("=" * 60)


if __name__ == "__main__":
    main()
