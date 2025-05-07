"""Consult --help for usage instructions."""

import argparse
import pathlib
import shutil
import sys
import typing
import json


def main() -> int:
    parser = argparse.ArgumentParser()

    action_group = parser.add_argument_group("actions").add_mutually_exclusive_group(
        required=True
    )
    action_group.add_argument(
        "--print-latest",
        action="store_true",
        help="Filter the given paths to just the latest version of each labware, and print those. Excludes draft.json files.",
    )
    action_group.add_argument(
        "--draft-from-latest",
        action="store_true",
        help="Filter the given paths to just the latest version of each labware, and copy those files to new draft.json files.",
    )
    action_group.add_argument(
        "--commit-draft",
        action="store_true",
        help="Move all given draft.json files to [number].json,"
        " where [number] is one greater than the existing highest version."
        " If the draft has identical contents to the existing highest version,"
        " it's removed.",
    )
    action_group.add_argument(
        "--versions-from-filenames",
        action="store_true",
        help="Set each labware's internal JSON version number to match its filename. Skips draft.json files.",
    )

    parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        type=pathlib.Path,
        help=(
            "The labware definitions you want to deal with."
            " Each arg can either be a directory, which will be searched recursively,"
            " or a single .json file, which will be individually added to the universe"
            " of known files. Typical usage is to pass a single directory like"
            " `/labware/definitions/2` or a a shell glob"
            " like `/labware/definitions/2/**.json`."
        ),
    )

    args = parser.parse_args()
    print_latest: bool = args.print_latest
    draft_from_latest: bool = args.draft_from_latest
    commit_draft: bool = args.commit_draft
    versions_from_filenames: bool = args.versions_from_filenames
    paths: list[pathlib.Path] = args.paths

    all_numbered_versions: list[tuple[str, pathlib.Path, int]] = []
    highest_numbered_versions: dict[str, tuple[pathlib.Path, int]] = {}
    drafts: list[tuple[str, pathlib.Path]] = []

    if not paths:
        print("Warning: No paths given.", file=sys.stderr)

    for path in resolve_paths(paths):
        parse_result = parse_path(path)
        if parse_result is None:
            print(f"Warning: Could not parse {path}", file=sys.stderr)
        else:
            name, version = parse_result
            if version == "draft":
                drafts.append((name, path))
            else:
                all_numbered_versions.append((name, path, version))
                try:
                    _, existing_highest_version = highest_numbered_versions[name]
                except KeyError:
                    existing_highest_version = None
                if (
                    existing_highest_version is None
                    or version > existing_highest_version
                ):
                    highest_numbered_versions[name] = (path, version)

    if print_latest:
        for path, _ in highest_numbered_versions.values():
            print(path)

    if draft_from_latest:
        for path, _ in highest_numbered_versions.values():
            new_path = path.with_name("draft.json")
            print(f"{path} -> {new_path}")
            shutil.copy(path, new_path)

    if commit_draft:
        for name, draft_path in drafts:
            try:
                existing_file, existing_highest_version = highest_numbered_versions[
                    name
                ]
            except KeyError:
                existing_file = None
                existing_highest_version = None

            if existing_file is None or json.loads(
                draft_path.read_bytes()
            ) != json.loads(existing_file.read_bytes()):
                new_version = (
                    existing_highest_version + 1
                    if existing_highest_version is not None
                    else 1
                )
                draft_path.replace(draft_path.with_name(f"{new_version}.json"))
            else:
                print(f"No changes in {draft_path}. Deleting it.", file=sys.stderr)
                draft_path.unlink()

    if versions_from_filenames:
        for _, path, version in all_numbered_versions:
            json_contents = json.loads(path.read_bytes())
            if json_contents["version"] != version:
                json_contents["version"] = version
                path.write_text(json.dumps(json_contents, indent=2, ensure_ascii=False))


def resolve_paths(
    roots: typing.Iterable[pathlib.Path],
) -> typing.Iterable[pathlib.Path]:
    for root in roots:
        if root.is_dir():
            yield from root.glob("**/*.json")
        else:
            yield root


def parse_path(path: pathlib.Path) -> tuple[str, int | typing.Literal["draft"]] | None:
    """Infer a labware definition's load name and version from its path."""
    if path.suffix != ".json":
        return None

    if path.stem == "draft":
        version = "draft"
    else:
        try:
            version = int(path.stem)
        except ValueError:
            return None

    name = path.resolve().parent.name
    return name, version


if __name__ == "__main__":
    sys.exit(main())
