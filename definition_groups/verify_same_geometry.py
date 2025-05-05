import json
from pathlib import Path
import sys
from typing import Any


def get_definition_path(root: Path, load_name: str) -> Path | None:
    matches = list((root / load_name).glob("*.json"))
    if len(matches) > 1:
        raise ValueError(f"Expected exactly 1 match: {matches}")
    return matches[0] if matches else None


def geometries_equal(geometry_a: dict[str, Any], geometry_b: dict[str, Any]) -> bool:
    if len(geometry_a) == 1 and len(geometry_b) == 1:
        return next(iter(geometry_a.values())) == next(iter(geometry_b.values()))
    else:
        return False  # Not implemented.


if __name__ == "__main__":
    groups_file = Path(sys.argv[1])
    definitions_path = Path(sys.argv[2])

    groups_dict = json.loads(groups_file.read_bytes())
    for group_name, group_members in groups_dict.items():
        definition_paths = [
            get_definition_path(definitions_path, load_name)
            for load_name in group_members
        ]
        geometries: list[dict[str, Any]] = [
            json.loads(path.read_bytes()).get("innerLabwareGeometry", {})
            for path in definition_paths
            if path
        ]
        all_geometries_equal = all(
            geometries_equal(g, geometries[0]) for g in geometries
        )
        mark = "✅" if all_geometries_equal else "❌"
        print(f'{mark} group "{group_name}"')
        for member, path in zip(group_members, definition_paths):
            print(f"  {member} {path if path else '⚠️ no path found'}")
