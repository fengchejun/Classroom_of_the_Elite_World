"""
Add portrait_image field to all characters and scene_image field to all locations.
Run once to initialize the image fields in the JSON data files.
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

# ── Core scene image mapping ──
# These are the most frequently visited locations
CORE_SCENES = {
    "classroom_1d": "classroom_1d.png",
    "classroom_1a": "classroom_1a.png",
    "classroom_1b": "classroom_1b.png",
    "classroom_1c": "classroom_1c.png",
    "dorm_lobby": "dorm_lobby.png",
    "dorm_male_floor": "dorm_male_floor.png",
    "dorm_female_floor": "dorm_female_floor.png",
    "dorm_courtyard": "dorm_courtyard.png",
    "hallway_1f": "hallway_1f.png",
    "hallway_2f": "hallway_2f.png",
    "hallway_3f": "hallway_3f.png",
    "library": "library.png",
    "teachers_office": "teachers_office.png",
    "campus_gate": "campus_gate.png",
    "sports_field": "sports_field.png",
    "mall_entrance": "mall_entrance.png",
    "mall_cafeteria": "mall_cafeteria.png",
    "mall_cafe": "mall_cafe.png",
    "mall_shop": "mall_shop.png",
    "special_building_1f": "special_building_1f.png",
}

# ── 1. Add portrait_image to characters ──
with open('scripts/output/characters_extracted.json', 'r', encoding='utf-8') as f:
    chars = json.load(f)

for entry in chars['data']:
    if 'portrait_image' not in entry:
        entry['portrait_image'] = ""

with open('scripts/output/characters_extracted.json', 'w', encoding='utf-8') as f:
    json.dump(chars, f, ensure_ascii=False, indent=2)
print(f"Added portrait_image field to {len(chars['data'])} characters")

# ── 2. Add scene_image to locations ──
with open('scripts/output/locations_extracted.json', 'r', encoding='utf-8') as f:
    locs = json.load(f)

scene_count = 0
for entry in locs['data']:
    lid = entry.get('location_id', '')
    if lid in CORE_SCENES:
        entry['scene_image'] = CORE_SCENES[lid]
        scene_count += 1
    elif 'scene_image' not in entry:
        entry['scene_image'] = ""

with open('scripts/output/locations_extracted.json', 'w', encoding='utf-8') as f:
    json.dump(locs, f, ensure_ascii=False, indent=2)
print(f"Added scene_image field to {len(locs['data'])} locations ({scene_count} with initial image assignments)")

print("\nDone! Image fields initialized.")
