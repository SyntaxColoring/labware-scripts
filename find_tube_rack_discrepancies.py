from collections import defaultdict
import json
from pathlib import Path
import sys


def get_dimensions_key(definition):
    dimensions = definition["dimensions"]
    return dimensions["xDimension"], dimensions["yDimension"]


def get_wells_xy_key(definition):
    def get_well_xy(well_name):
        well = definition["wells"][well_name]
        return well["x"], well["y"]

    return tuple(
        get_well_xy(well_name)
        for column in definition["ordering"]
        for well_name in column
    )


if __name__ == "__main__":
    search_path = Path(sys.argv[1])
    print(search_path)
    definition_paths = list(search_path.rglob("*tube*/*.json"))
    print(definition_paths)

    dimensions_results = defaultdict(list)
    wells_results = defaultdict(list)

    for definition_path in definition_paths:
        definition = json.loads(definition_path.read_bytes())
        dimensions_results[get_dimensions_key(definition)].append(str(definition_path))
        wells_results[get_wells_xy_key(definition)].append(str(definition_path))

    print("DIMENSIONS:")
    for key in dimensions_results:
        print(f"  {key}")
        for value in dimensions_results[key]:
            print(f"    {value}")

    print()

    print("WELL XY:")
    for key in wells_results:
        print(f"  {key}")
        for value in wells_results[key]:
            print(f"    {value}")
