"""
Enrich events_extracted.json with:
  - required_player_char  (role gate for perspective-specific events)
  - required_location     (null for background events)
  - options               (2-3 choices for ai_guided_choice events)
  - silent_effects        (consequences in standard schema)

Uses DeepSeek API to batch-process 549 events (~40-55 calls).
Caches per-batch results for resume on failure.

Usage:
    py scripts/enrich_events.py              # full enrichment
    py scripts/enrich_events.py --dry-run    # count batches only
    py scripts/enrich_events.py --batch 3    # run only batch 3
    py scripts/enrich_events.py --resume     # skip cached batches
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

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
INPUT = OUTPUT_DIR / "events_extracted.json"
CHAR_INPUT = OUTPUT_DIR / "characters_extracted.json"
OUTPUT = OUTPUT_DIR / "events_enriched.json"
CACHE_DIR = OUTPUT_DIR / ".cache" / "enrich"
BACKUP = OUTPUT_DIR / "events_extracted_pre_enrich_backup.json"

DEEPSEEK_API_KEY = "sk-a027465f568346db99147bb047d7a643"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-chat"
LLM_MAX_TOKENS = 8192
LLM_TEMPERATURE = 0.3

RATE_LIMIT_SEC = 3.0
MAX_RETRIES = 3
BATCH_SIZE = 12  # events per API call

# Known role_ids from extracted characters
VALID_ROLE_IDS = set()


# ---- helpers ----

def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = LLM_MAX_TOKENS) -> str | None:
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
            print(f"  API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt * 2)
    return None


def extract_json_from_response(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    for start, end in [('{', '}'), ('[', ']')]:
        idx_start = text.find(start)
        idx_end = text.rfind(end)
        if idx_start != -1 and idx_end > idx_start:
            try:
                return json.loads(text[idx_start:idx_end + 1])
            except json.JSONDecodeError:
                pass

    print(f"  [WARN] Could not parse JSON from response (first 200 chars): {text[:200]}")
    return None


def load_character_role_ids() -> dict[str, str]:
    """Load character name -> role_id mapping from extracted data."""
    mapping = {}
    if CHAR_INPUT.exists():
        with open(CHAR_INPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
        for char in data.get("data", []):
            name = char.get("name", "")
            role_id = char.get("role_id", "")
            class_name = char.get("class_name", "")
            if role_id and name:
                mapping[name] = role_id
                VALID_ROLE_IDS.add(role_id)
    # Always include 'player' as the generic player alias
    VALID_ROLE_IDS.add("player")
    # Add common role_ids that might appear in prompts
    VALID_ROLE_IDS.update({
        "ayanokoji_kiyotaka", "horikita_suzune", "kushida_kikyo",
        "sudo_ken", "hirata_yosuke", "karuizawa_kei",
        "ryuen_kakeru", "ishizaki_daichi", "ibuki_mio",
        "ichinose_honami", "sakayanagi_arisu", "katsuragi_kouhei",
        "kanzaki_ryuji", "tachibana_akane", "sakura_airi",
        "kouenji_rokusuke", "yamada_albert", "shiina_hiori",
        "chabashira_sae", "hoshinomiya_chie", "mashima_tomoya",
        "nagumo_miyabi", "horikita_manabu", "koenji_rokusuke",
        "yamanouch_haruki", "ike_kanji", "sotomura_hideo",
        "matsushita_chiaki", "yukimura_teruhiko", "miyake_akito",
        "hasebe", "ishizaki", "ibuki",
    })
    return mapping


def build_system_prompt(char_mapping: dict[str, str]) -> str:
    """Build the system prompt for event enrichment."""
    # Build compact role_id table
    role_table_lines = []
    for name, rid in sorted(char_mapping.items(), key=lambda x: x[0]):
        role_table_lines.append(f"  {rid} = {name}")
    role_table = "\n".join(role_table_lines[:60])  # limit to avoid token bloat

    return f"""你是一个游戏数据设计师。你的任务是为《实力至上主义教室》模拟器的549个事件补充游戏机制数据。

## 角色role_id对照表（常用角色）
{role_table}
注：player = 绫小路清隆（主角，也是默认玩家角色）
未列出的角色请从事件prompt中推断其role_id（英文小写+下划线格式）

## 输出格式
对于每组事件，输出一个JSON对象，key为event_id，value为补充数据：
```json
{{
  "event_id_1": {{
    "required_player_char": null,
    "required_location": "classroom_d",
    "options": [],
    "silent_effects": {{
      "status_tag_changes": {{}},
      "relation_changes": [],
      "class_point_changes": {{}}
    }}
  }}
}}
```

## 字段填写规则

### 1. required_player_char
- 如果事件以绫小路清隆（主角）为视角，只有扮演绫小路时才能触发 → 填 "player"
- 如果事件以某个特定角色为核心（如堀北的个人成长、龙园的统治），只有扮演该角色时才能触发 → 填对应role_id
- 如果事件是学校/班级层面的公共事件（考试、公告、全校活动）→ 填 null
- 如果事件是后台事件（不依赖玩家视角）→ 填 null

### 2. required_location
- 如果事件是后台事件，玩家不需要在场就能发生（如班级点数变化、角色间密谋、校内流言传播）→ 填 null
- 如果事件需要玩家在特定地点才能触发参与 → 保留原location_id或填入最合适的地点

### 3. options（仅对 type=ai_guided_choice 的事件填写，其余类型填 []）
每个选项格式：
```json
{{
  "id": "1",
  "text": "玩家可采取的行动，中文描述，10-20字",
  "target_event": null,
  "stat_changes": {{}}
}}
```
- 提供2-3个有区分度的选项
- 选项应该代表不同的策略或态度（如：积极介入/保持观望/暗中布局）
- 选项的text应该从玩家角色视角出发
- target_event保持null（暂时不链接）
- stat_changes保持空对象

### 4. silent_effects（所有事件必须填写）
记录事件发生后对世界状态的影响。三个子字段都必须存在（空则填空对象/空数组）：
- **status_tag_changes**: 角色状态变化，格式 {{"role_id": ["标签1", "标签2"]}}
  标签示例: "injured", "absent", "退学危机", "暴露", "被威胁", "觉醒", "点数归零"
- **relation_changes**: 人际关系变化，格式 [{{"from": "role_id", "to": "role_id", "type": "trust|hostile|subservient|rival|neutral", "reason": "中文原因"}}]
- **class_point_changes**: 班级点数变动，格式 {{"A": 50, "B": -30}} 或 {{}}

## 重要原则
1. 优先从事件的 active_prompt 和 ai_setup_prompt 文本推断角色、地点和后果
2. 无法确定时保持保守：required_player_char 优先填 null（公共事件比角色专属事件更安全）
3. silent_effects 要具体、可量化，不要泛泛而谈
4. options 要体现玩家选择的多样性，不能都是同一方向的微调
5. 所有字段必须完整，即使为空也要保留（[]、{{}}、null）"""


def build_batch_prompt(events_batch: dict) -> str:
    """Build the user prompt for a batch of events."""
    lines = ["请为以下事件补充游戏机制数据。输出格式：以event_id为key的JSON对象。\n"]
    lines.append("```json")
    for eid, edef in events_batch.items():
        # Extract minimal but sufficient info for the LLM
        summary = {
            "name": edef.get("name", ""),
            "type": edef.get("type", "fixed_story"),
            "trigger_conditions": edef.get("trigger_conditions", {}),
            "active_prompt": (edef.get("active_prompt", "") or "")[:600],
            "ai_setup_prompt": (edef.get("ai_setup_prompt", "") or "")[:400],
            "rules_appendix": edef.get("rules_appendix"),
        }
        lines.append(json.dumps({eid: summary}, ensure_ascii=False))
    lines.append("```")
    lines.append("\n请开始输出（仅输出JSON，不要其他说明）：")
    return "\n".join(lines)


def validate_enriched_batch(batch: dict, batch_idx: int) -> int:
    """Validate enriched data. Returns count of errors."""
    errors = 0
    for eid, enriched in batch.items():
        # Check required_player_char
        rpc = enriched.get("required_player_char", "__missing__")
        if rpc == "__missing__":
            print(f"  [VAL] {eid}: missing required_player_char")
            errors += 1

        # Check required_location
        rl = enriched.get("required_location", "__missing__")
        if rl == "__missing__":
            print(f"  [VAL] {eid}: missing required_location")
            errors += 1

        # Check options format
        options = enriched.get("options")
        if options is None:
            print(f"  [VAL] {eid}: options is null (should be [])")
            errors += 1
        elif not isinstance(options, list):
            print(f"  [VAL] {eid}: options is not a list")
            errors += 1

        # Check silent_effects format
        se = enriched.get("silent_effects", {})
        if not isinstance(se, dict):
            print(f"  [VAL] {eid}: silent_effects is not a dict")
            errors += 1
            continue
        for key in ("status_tag_changes", "relation_changes", "class_point_changes"):
            if key not in se:
                print(f"  [VAL] {eid}: silent_effects missing '{key}'")
                errors += 1

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--batch", type=int, default=None, help="Run only specific batch")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    # Load character role mapping
    char_mapping = load_character_role_ids()
    print(f"Loaded {len(char_mapping)} character role_id mappings")
    print(f"Total valid role_ids: {len(VALID_ROLE_IDS)}")

    # Load events
    with open(INPUT, "r", encoding="utf-8") as f:
        events_data = json.load(f)
    events = events_data["data"]
    print(f"Loaded {len(events)} events from {INPUT}")

    # Backup if not already backed up
    if not BACKUP.exists():
        import shutil
        shutil.copy2(INPUT, BACKUP)
        print(f"Backup created: {BACKUP}")

    # Split into batches
    event_items = list(events.items())
    batches = []
    for i in range(0, len(event_items), args.batch_size):
        batch = dict(event_items[i:i + args.batch_size])
        batches.append(batch)

    print(f"Split into {len(batches)} batches (batch size: {args.batch_size})")

    if args.dry_run:
        print("Dry run complete.")
        return

    # Create cache dir
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    system_prompt = build_system_prompt(char_mapping)
    all_enriched = {}

    # Determine which batches to process
    if args.batch is not None:
        batch_indices = [args.batch]
    else:
        batch_indices = list(range(len(batches)))

    for bi in batch_indices:
        if bi < 0 or bi >= len(batches):
            print(f"Batch {bi} out of range (0-{len(batches)-1})")
            continue

        cache_file = CACHE_DIR / f"batch_{bi:03d}.json"

        # Check cache
        if args.resume and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                all_enriched.update(cached)
                print(f"Batch {bi}/{len(batches)}: loaded from cache ({len(cached)} events)")
                continue
            except Exception:
                pass

        batch = batches[bi]
        batch_size = len(batch)
        print(f"\nBatch {bi}/{len(batches)} ({batch_size} events):")

        # Build prompt
        user_prompt = build_batch_prompt(batch)

        # Call LLM
        start = time.time()
        response = call_deepseek(system_prompt, user_prompt)
        elapsed = time.time() - start

        if response is None:
            print(f"  FAILED after {MAX_RETRIES} retries (took {elapsed:.1f}s)")
            # Save empty batch so we can still proceed
            cache_file.write_text("{}", encoding="utf-8")
            continue

        enriched = extract_json_from_response(response)

        if enriched is None:
            print(f"  FAILED to parse JSON (took {elapsed:.1f}s)")
            print(f"  Response preview: {response[:300]}")
            cache_file.write_text("{}", encoding="utf-8")
            continue

        # Validate
        errs = validate_enriched_batch(enriched, bi)
        if errs > 0:
            print(f"  Parsed with {errs} validation errors (took {elapsed:.1f}s)")
        else:
            print(f"  OK — {len(enriched)} events enriched ({elapsed:.1f}s)")

        # Cache this batch
        cache_file.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        all_enriched.update(enriched)

        # Rate limit
        if bi < batch_indices[-1]:
            time.sleep(RATE_LIMIT_SEC)

    # Merge enriched data into events
    print(f"\nMerging enriched data into {len(events)} events...")
    merge_count = 0
    for eid, enriched in all_enriched.items():
        if eid in events:
            event = events[eid]

            # Apply required_player_char to trigger_conditions
            tc = event.setdefault("trigger_conditions", {})
            tc["required_player_char"] = enriched.get("required_player_char")

            # Apply required_location override (enriched value replaces original)
            new_loc = enriched.get("required_location", "__keep__")
            if new_loc != "__keep__" and new_loc is not None:
                tc["required_location"] = new_loc
            elif new_loc is None:
                # Explicitly null means remove location requirement
                tc["required_location"] = None

            # Apply options
            options = enriched.get("options", [])
            if isinstance(options, list) and len(options) > 0:
                event["options"] = options

            # Apply silent_effects
            se = enriched.get("silent_effects")
            if isinstance(se, dict):
                event["silent_effects"] = se

            merge_count += 1

    print(f"Merged {merge_count} enriched events")

    # Update the data
    events_data["data"] = events

    # Save
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(events_data, f, ensure_ascii=False, indent=2)
    print(f"Saved enriched events to: {OUTPUT}")
    print(f"Total events: {len(events)}")
    print(f"Input: {INPUT}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
