"""
Assign dorm rooms to all 2024-enrolled students.

- Male students: floors 1-6 (dorm_room_101 ~ dorm_room_699)
- Female students: floors 7-12 (dorm_room_701 ~ dorm_room_1299)
- Only applies to enrollment_year == "2024"
- Excludes the player character (绫小路清隆)

Outputs:
  1. Updated characters_extracted.json (adds dorm_room_id to each 2024 char)
  2. Updated locations_extracted.json (adds dorm room location entries)
  3. Console output for DEFAULT_SCHEDULES and _LOCATION_ALIASES updates
"""
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = "scripts/output"

# ── Gender lookup for all 2024 students ────────────────────────────────────
# Based on Classroom of the Elite source material and Japanese name conventions
GENDER_MAP: dict[str, str] = {
    # D班
    "绫小路清隆": "male",
    "堀北铃音": "female",
    "栉田桔梗": "female",
    "须藤健": "male",
    "池宽治": "male",
    "山内春树": "male",
    "平田洋介": "male",
    "高圆寺六助": "male",
    "轻井泽惠": "female",
    "佐仓爱里": "female",
    "井之头心": "female",
    "本堂": "male",
    "小野寺": "female",
    "外村": "male",
    "筱原皋月": "female",
    "幸村辉彦": "male",
    "外村秀雄": "male",
    "佐藤麻耶": "female",
    "长谷部波琉加": "female",  # duplicate of 长谷部波瑠加
    "松下": "female",
    "三宅明人": "male",
    "姬野": "female",
    "松下千秋": "female",
    # B班
    "一之濑帆波": "female",
    "长谷部波瑠加": "female",
    "神崎隆二": "male",
    "滨口哲也": "male",
    "柴田飒": "male",
    "姬野雪": "female",
    # C班
    "龙园翔": "male",
    "石崎大地": "male",
    "山胁": "male",
    "伊吹澪": "female",
    "真锅志保": "female",
    "石崎": "male",
    "阿尔伯特": "male",
    "真锅": "female",
    "椎名日和": "female",
    "白波千寻": "female",
    "小桥梦": "female",
    "西野武子": "female",
    # A班
    "葛城康平": "male",
    "弥彦": "male",
    "町田浩二": "male",
    "坂柳有栖": "female",
    "神室真澄": "female",
    "桥本正义": "male",
    "竹本": "male",
    "鬼头隼": "male",
    "真田康生": "male",
    "山村美纪": "female",
}

# ── Load characters ─────────────────────────────────────────────────────────
with open(f"{BASE_DIR}/characters_extracted.json", "r", encoding="utf-8") as f:
    chars_data = json.load(f)

entries = chars_data["data"]
updated_count = 0
room_assignments: dict[str, str] = {}  # name -> dorm_room_id
gender_counts: dict[str, list[str]] = defaultdict(list)

for entry in entries:
    name = entry.get("name", "")
    ey = str(entry.get("enrollment_year", "2024"))

    if ey != "2024":
        continue
    if name == "绫小路清隆":
        continue  # skip player

    # Prefer gender field from character data, fall back to GENDER_MAP
    gender = entry.get("gender") or GENDER_MAP.get(name)
    if not gender:
        print(f"  WARNING: No gender mapping for {name} — skipping")
        continue

    gender_counts[gender].append(name)

print(f"Male 2024 students (excl. player): {len(gender_counts['male'])}")
print(f"Female 2024 students: {len(gender_counts['female'])}")
print(f"Total to assign: {len(gender_counts['male']) + len(gender_counts['female'])}")

# ── Assign room numbers ─────────────────────────────────────────────────────
# Distribute evenly across floors
males = gender_counts["male"]
females = gender_counts["female"]

def assign_rooms(names: list[str], start_floor: int, num_floors: int) -> dict[str, str]:
    """Assign room numbers, spreading names across floors.

    Room ID format: dorm_room_FFRR (4 digits: FF=floor 01-12, RR=room 01-99).
    E.g. dorm_room_0101 = floor 1 room 1, dorm_room_1205 = floor 12 room 5.
    """
    per_floor = (len(names) + num_floors - 1) // num_floors  # ceiling division
    assignments = {}
    for i, name in enumerate(names):
        floor = start_floor + (i // per_floor)
        if floor >= start_floor + num_floors:
            floor = start_floor + num_floors - 1  # clamp to max floor
        room_num = (i % per_floor) + 1
        room_id = f"dorm_room_{floor:02d}{room_num:02d}"
        assignments[name] = room_id
    return assignments

male_rooms = assign_rooms(males, 1, 6)
female_rooms = assign_rooms(females, 7, 6)

all_rooms = {**male_rooms, **female_rooms}

# ── Update characters_extracted.json ────────────────────────────────────────
for entry in entries:
    name = entry.get("name", "")
    if name in all_rooms:
        entry["dorm_room_id"] = all_rooms[name]
        updated_count += 1

# Write back
with open(f"{BASE_DIR}/characters_extracted.json", "w", encoding="utf-8") as f:
    json.dump(chars_data, f, ensure_ascii=False, indent=2)
print(f"\nUpdated {updated_count} characters with dorm_room_id")

# ── Print room assignments ──────────────────────────────────────────────────
print("\n--- Male Room Assignments ---")
for name, room in sorted(male_rooms.items(), key=lambda x: x[1]):
    print(f"  {name} → {room}")

print("\n--- Female Room Assignments ---")
for name, room in sorted(female_rooms.items(), key=lambda x: x[1]):
    print(f"  {name} → {room}")

# ── Generate dorm room locations for locations_extracted.json ───────────────
all_room_ids = sorted(set(all_rooms.values()))
print(f"\nGenerating {len(all_room_ids)} dorm room locations...")

# Load existing locations
with open(f"{BASE_DIR}/locations_extracted.json", "r", encoding="utf-8") as f:
    locs_data = json.load(f)

existing_ids = {loc["location_id"] for loc in locs_data["data"]}
new_rooms_added = 0

for room_id in all_room_ids:
    if room_id in existing_ids:
        continue
    # Extract floor from room_id: dorm_room_0101 → floor 1, dorm_room_1205 → floor 12
    room_suffix = room_id.split("_")[-1]  # e.g. "0101", "1205"
    floor_num = int(room_suffix[:2])  # first 2 digits = floor
    is_male = floor_num <= 6
    gender_str = "男生" if is_male else "女生"
    floor_str = f"{floor_num}F"

    locs_data["data"].append({
        "location_id": room_id,
        "name": f"宿舍房间 {room_id.split('_')[-1]}",
        "description": f"宿舍{floor_num}楼的一间{gender_str}单人房间，约四坪大小，配备基本家具和空调。",
        "tags": ["indoor", "private", "residential"],
        "connected_to": [f"dorm_male_floor" if is_male else f"dorm_female_floor"],
        "parent_zone": "dormitory",
        "zone_name": "宿舍区",
        "floor": floor_str,
    })
    new_rooms_added += 1

# Write back
with open(f"{BASE_DIR}/locations_extracted.json", "w", encoding="utf-8") as f:
    json.dump(locs_data, f, ensure_ascii=False, indent=2)
print(f"Added {new_rooms_added} new dorm room locations")

# ── Print summary for manual code updates ───────────────────────────────────
print("\n" + "=" * 60)
print("MANUAL UPDATE REQUIRED: npc_funnel.py DEFAULT_SCHEDULES")
print("=" * 60)
print("""
Update evening and late_night DEFAULT_SCHEDULES to distribute NPCs
to their dorm_room_id instead of all crowding dorm_lobby.

For characters with dorm_room_id, they should use their own room
in the evening/night instead of the lobby.
""")

# Print stats for schedule design
print("\nRoom distribution by class and gender:")
class_room_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
for entry in entries:
    name = entry.get("name", "")
    if name not in all_rooms:
        continue
    cls = entry.get("class_name", "?")
    room = all_rooms[name]
    room_suffix = room.split("_")[-1]
    floor = int(room_suffix[:2])
    gender = "male" if floor <= 6 else "female"
    class_room_count[cls][gender] += 1

for cls in ["D", "C", "B", "A"]:
    counts = class_room_count[cls]
    print(f"  {cls}班: male={counts.get('male', 0)}, female={counts.get('female', 0)}")

print("\nDone!")
