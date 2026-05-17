"""
Enrich characters_extracted.json with private_points and spending_habit fields.
Spending habit is derived from traits using the same logic as _derive_spending_habit().
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "output", "characters_extracted.json")


def derive_spending_habit(traits: list[str]) -> str:
    traits_text = " ".join(traits)
    if any(t in traits_text for t in ["孤高", "节俭", "朴素", "省钱", "节约", "体弱", "身体虚弱", "病弱"]):
        return "frugal"
    if any(t in traits_text for t in ["社交", "外向", "开朗", "人脉", "辣妹", "天然"]):
        return "socialite"
    if any(t in traits_text for t in ["游戏", "漫画", "动漫", "二次元", "宅", "otaku"]):
        return "gamer/otaku"
    return "normal"


def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        original = f.read()

    # Backup
    backup_path = INPUT_PATH.replace(".json", "_backup.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original)
    print(f"Backup saved to {backup_path}")

    data = json.loads(original)
    characters = data.get("data", [])
    stats = {"frugal": 0, "socialite": 0, "gamer/otaku": 0, "normal": 0}

    for entry in characters:
        name = entry.get("name", "?")
        traits = entry.get("traits", [])

        if "private_points" not in entry:
            entry["private_points"] = 100000

        habit = entry.get("spending_habit") or derive_spending_habit(traits)
        entry["spending_habit"] = habit
        stats[habit] = stats.get(habit, 0) + 1

    with open(INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Enriched {len(characters)} characters")
    print(f"  Spending habits: {stats}")


if __name__ == "__main__":
    main()
