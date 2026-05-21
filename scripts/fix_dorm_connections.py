"""
Fix: dorm_male_floor and dorm_female_floor must connect to all rooms on their floors.
Without this, individual dorm rooms are isolated and unreachable.
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scripts/output/locations_extracted.json', 'r', encoding='utf-8') as f:
    locs = json.load(f)

# Collect all dorm room IDs by floor
male_rooms = []
female_rooms = []
for loc in locs['data']:
    lid = loc['location_id']
    if lid.startswith('dorm_room_'):
        room_suffix = lid.split('_')[-1]  # e.g. "0101"
        floor = int(room_suffix[:2])
        if floor <= 6:
            male_rooms.append(lid)
        else:
            female_rooms.append(lid)

male_rooms.sort()
female_rooms.sort()
print(f'Male rooms ({len(male_rooms)}): {male_rooms[:5]}...{male_rooms[-3:]}')
print(f'Female rooms ({len(female_rooms)}): {female_rooms[:5]}...{female_rooms[-3:]}')

# Fix dorm_male_floor's connected_to
for loc in locs['data']:
    if loc['location_id'] == 'dorm_male_floor':
        old = loc['connected_to']
        loc['connected_to'] = ['dorm_lobby'] + male_rooms
        print(f'\nFixed dorm_male_floor: {len(old)} → {len(loc["connected_to"])} connections')
    elif loc['location_id'] == 'dorm_female_floor':
        old = loc['connected_to']
        loc['connected_to'] = ['dorm_lobby'] + female_rooms
        print(f'Fixed dorm_female_floor: {len(old)} → {len(loc["connected_to"])} connections')

with open('scripts/output/locations_extracted.json', 'w', encoding='utf-8') as f:
    json.dump(locs, f, ensure_ascii=False, indent=2)
print('\nDone! Restart server to apply.')
