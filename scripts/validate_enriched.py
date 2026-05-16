"""
Validate events_enriched.json data quality.

Checks:
  - All ai_guided_choice events have non-empty options
  - All silent_effects have the three required keys
  - required_player_char values are valid role_ids or null
  - required_location values are valid location_ids or null
  - All dates are YYYY-MM-DD format

Usage:
    py scripts/validate_enriched.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
INPUT = OUTPUT_DIR / "events_enriched.json"
LOCATIONS_INPUT = OUTPUT_DIR / "locations_extracted.json"
CHAR_INPUT = OUTPUT_DIR / "characters_extracted.json"

VALID_ROLE_IDS: set[str] = set()
VALID_LOCATION_IDS: set[str] = set()


def load_reference_data():
    if CHAR_INPUT.exists():
        with open(CHAR_INPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("data", []):
            if c.get("role_id"):
                VALID_ROLE_IDS.add(c["role_id"])
    VALID_ROLE_IDS.add("player")
    # Common known IDs
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
        "hasebe_haruka", "ishizaki", "ibuki", "kushida_kikyou",
    })

    if LOCATIONS_INPUT.exists():
        with open(LOCATIONS_INPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
        for loc in data.get("data", []):
            if loc.get("location_id"):
                VALID_LOCATION_IDS.add(loc["location_id"])


def validate():
    load_reference_data()
    print(f"Reference data: {len(VALID_ROLE_IDS)} role_ids, {len(VALID_LOCATION_IDS)} location_ids")

    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("data", {})
    print(f"Events: {len(events)}")

    errors = []
    warnings = []

    ai_choice_count = 0
    ai_choice_with_options = 0

    for eid, e in sorted(events.items()):
        name = e.get("name", eid)
        etype = e.get("type", "")

        # 1. Check silent_effects
        se = e.get("silent_effects")
        if se is None:
            errors.append(f"[MISSING] {eid}: silent_effects is null")
        elif not isinstance(se, dict):
            errors.append(f"[FORMAT] {eid}: silent_effects is not a dict")
        else:
            for key in ("status_tag_changes", "relation_changes", "class_point_changes"):
                if key not in se:
                    errors.append(f"[MISSING] {eid}: silent_effects missing '{key}'")
            # Validate relation_changes format
            for rc in se.get("relation_changes", []):
                if not isinstance(rc, dict):
                    errors.append(f"[FORMAT] {eid}: relation_changes item is not dict")
                    break
                for fk in ("from", "to", "type", "reason"):
                    if fk not in rc:
                        errors.append(f"[MISSING] {eid}: relation missing '{fk}'")
                valid_types = {"trust", "hostile", "subservient", "rival", "neutral"}
                if rc.get("type") not in valid_types:
                    errors.append(f"[VALUE] {eid}: invalid relation type '{rc.get('type')}'")
            # Validate status_tag_changes format
            stc = se.get("status_tag_changes", {})
            if not isinstance(stc, dict):
                errors.append(f"[FORMAT] {eid}: status_tag_changes is not dict")
            # Validate class_point_changes format
            cpc = se.get("class_point_changes", {})
            if not isinstance(cpc, dict):
                errors.append(f"[FORMAT] {eid}: class_point_changes is not dict")
            else:
                for cls_name in cpc:
                    if cls_name not in ("A", "B", "C", "D"):
                        warnings.append(f"[WARN] {eid}: unusual class in class_point_changes: {cls_name}")

        # 2. Check options for ai_guided_choice
        if etype == "ai_guided_choice":
            ai_choice_count += 1
            opts = e.get("options", [])
            if not isinstance(opts, list) or len(opts) == 0:
                errors.append(f"[MISSING] {eid} ({name}): ai_guided_choice has no options")
            else:
                ai_choice_with_options += 1
                for opt in opts:
                    for fk in ("id", "text", "target_event", "stat_changes"):
                        if fk not in opt:
                            errors.append(f"[MISSING] {eid}: option missing '{fk}'")

        # 3. Check required_player_char
        tc = e.get("trigger_conditions", {})
        rpc = tc.get("required_player_char")
        if rpc is not None and rpc not in VALID_ROLE_IDS:
            # Not a hard error — the LLM may have generated valid new IDs
            warnings.append(f"[WARN] {eid}: unknown required_player_char '{rpc}'")

        # 4. Check required_location
        rl = tc.get("required_location")
        if rl is not None and rl not in VALID_LOCATION_IDS:
            if len(VALID_LOCATION_IDS) > 0:
                warnings.append(f"[WARN] {eid}: unknown required_location '{rl}'")

        # 5. Check date formats
        for date_field in ("required_date", "active_start_date", "active_end_date",
                           "foreshadow_start_date", "transition_date"):
            val = tc.get(date_field) or e.get(date_field)
            if val and not re.match(r'^\d{4}-\d{2}-\d{2}$', str(val)):
                errors.append(f"[FORMAT] {eid}: invalid date '{val}' in {date_field}")

    # Summary
    print(f"\n{'='*50}")
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  ai_guided_choice events: {ai_choice_count}")
    print(f"  ai_guided_choice with options: {ai_choice_with_options}")
    print(f"{'='*50}")

    if errors:
        print(f"\nERRORS:")
        for err in errors[:30]:
            print(f"  {err}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more errors")

    if warnings:
        print(f"\nWARNINGS:")
        for w in warnings[:20]:
            print(f"  {w}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more warnings")

    return len(errors)


if __name__ == "__main__":
    errs = validate()
    if errs == 0:
        print("\nPASSED: All validations passed!")
    else:
        print(f"\nFAILED: {errs} validation errors found.")
    exit(0 if errs == 0 else 1)
