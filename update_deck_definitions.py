#!/usr/bin/env python3
"""
Script to add extents and features to deck definitions.

Usage:
cd shared-data/python
pipenv run python update_deck_defs.py ../deck/definitions/5/**/*.json
make -C .. format-js
"""

import json
from pathlib import Path
import sys
import decimal


class DecimalEncoder(json.JSONEncoder):
    """A JSON encoder that can encode decimal.Decimal objects."""

    def default(self, o: object) -> object:
        if isinstance(o, decimal.Decimal):
            return float(o)
        else:
            return super().default(o)


def migrate_addressable_area(area: dict) -> dict:
    """Migrate a single addressable area to add extents and features."""
    bounding_box = area["boundingBox"]

    x_dimension = bounding_box["xDimension"]
    y_dimension = bounding_box["yDimension"]
    z_dimension = bounding_box["zDimension"]
    y_inverse = -y_dimension

    extents = {
        "total": {
            "backLeftBottom": {"x": 0, "y": 0, "z": 0},
            "frontRightTop": {"x": x_dimension, "y": y_inverse, "z": z_dimension},
        }
    }

    new_area = {}
    for key, value in area.items():
        new_area[key] = value

        if key == "boundingBox":
            new_area["extents"] = extents
        elif key == "extents" or (key == "boundingBox" and "extents" not in area):
            if "features" not in area:
                new_area["features"] = {}

    if "features" not in new_area:
        new_area["features"] = {}

    return new_area


def migrate(context: str, definition: dict) -> dict:
    """Migrate a deck definition to add extents and features to addressable areas."""
    if "locations" not in definition or "addressableAreas" not in definition["locations"]:
        print(f"{context}: not a deck definition with addressable areas, skipping")
        return definition

    new_definition = {}
    for key, value in definition.items():
        if key == "locations":
            new_locations = {}
            for loc_key, loc_value in value.items():
                if loc_key == "addressableAreas":
                    new_locations[loc_key] = [
                        migrate_addressable_area(area) for area in loc_value
                    ]
                else:
                    new_locations[loc_key] = loc_value
            new_definition[key] = new_locations
        else:
            new_definition[key] = value


    addressable_areas = definition["locations"]["addressableAreas"]
    print(f"{context}: migrated {len(addressable_areas)} addressable areas")
    return new_definition


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_deck_defs.py <deck_file_1> [deck_file_2] ...")
        sys.exit(1)

    paths = [Path(arg) for arg in sys.argv[1:]]

    for path in paths:
        try:
            definition = json.loads(
                path.read_text(encoding="utf-8"),
                parse_float=decimal.Decimal,
            )
            migrated_definition = migrate(str(path), definition)
            path.write_text(
                json.dumps(
                    migrated_definition,
                    indent=2,
                    ensure_ascii=False,
                    cls=DecimalEncoder,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"Error processing {path}: {e}")

    print(f"Processed {len(paths)} files.")