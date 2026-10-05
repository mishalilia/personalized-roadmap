"""Command line: `python -m roadmap fetch | plan <profile> | compare`, with `--provider` to pick a model provider."""

import argparse
import itertools
import logging
import sys
from pathlib import Path

from .config import Settings
from .curriculum import Level
from .onboarding import LearnerProfile, load_profiles
from .path import Choice, LearningPath, path_difference
from .service import Roadmap
from .source import CurriculumSource, checkout


def main(argv: list[str] | None = None) -> None:
    # Module titles contain characters such as "›" that the Windows console encoding cannot print.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    if args.provider:
        settings = settings.model_copy(update={"llm_provider": args.provider})
    args.command(args, settings)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roadmap", description="Personal paths through the HumbleBeeAI curriculum."
    )
    parser.set_defaults(provider=None, verbose=False)
    commands = parser.add_subparsers(required=True)

    model_options = argparse.ArgumentParser(add_help=False)
    model_options.add_argument(
        "--provider", help="a provider from config/llm.yaml, instead of LLM_PROVIDER"
    )
    model_options.add_argument(
        "--verbose", action="store_true", help="log each model call: time and tokens"
    )

    fetch = commands.add_parser(
        "fetch", help="check out the curriculum at the pinned version"
    )
    fetch.set_defaults(command=_fetch)

    plan = commands.add_parser(
        "plan", parents=[model_options], help="build the path for an example profile"
    )
    plan.add_argument("profile", help="profile id from config/profiles.yaml, e.g. p1")
    plan.add_argument(
        "--level",
        type=Level,
        choices=list(Level),
        help="skip level inference and plan for this level",
    )
    plan.add_argument(
        "--out", type=Path, help="also write the path as JSON to this file"
    )
    plan.set_defaults(command=_plan)

    compare = commands.add_parser(
        "compare",
        parents=[model_options],
        help="build the paths of all example profiles and compare them",
    )
    compare.set_defaults(command=_compare)
    return parser


def _fetch(args: argparse.Namespace, settings: Settings) -> None:
    source = CurriculumSource.from_file(settings.curriculum_file)
    docs_dir = checkout(source, settings.curriculum_checkout)
    print(f"Curriculum {source.version[:7]} is checked out in {docs_dir}")


def _plan(args: argparse.Namespace, settings: Settings) -> None:
    roadmap = Roadmap.from_settings(settings)
    path = _build_path(roadmap, _find_profile(settings, args.profile), args.level)
    _print_path(path)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(path.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nWritten to {args.out}")


def _compare(args: argparse.Namespace, settings: Settings) -> None:
    roadmap = Roadmap.from_settings(settings)
    paths = {
        profile.id: _build_path(roadmap, profile)
        for profile in load_profiles(settings.profiles_file)
    }
    for profile_id, path in paths.items():
        print(f"{profile_id}, planned for {path.level or 'no level'}: {_summary(path)}")
    pairs = itertools.combinations(paths.items(), 2)
    for (first_id, first), (second_id, second) in pairs:
        difference = path_difference(first, second)
        print(f"{first_id} vs {second_id}: {difference:.0%} of the modules differ")


def _build_path(
    roadmap: Roadmap, profile: LearnerProfile, level: Level | None = None
) -> LearningPath:
    """Plan for the given level, or for the suggested one when none is given."""
    assessment = None if level else roadmap.assess_level(profile.answers)
    if assessment is not None:
        level = assessment.level
    return roadmap.build_path(profile.answers, level, assessment)


def _find_profile(settings: Settings, profile_id: str) -> LearnerProfile:
    profiles = {
        profile.id: profile for profile in load_profiles(settings.profiles_file)
    }
    if profile_id not in profiles:
        sys.exit(f"Unknown profile '{profile_id}'. Available: {', '.join(profiles)}")
    return profiles[profile_id]


def _print_path(path: LearningPath) -> None:
    if path.assessment is not None:
        print(
            f"Suggested level: {path.assessment.level} ({path.assessment.confidence} confidence)"
        )
        for point in path.assessment.evidence:
            print(f"  - {point}")
    if path.personalization_unavailable:
        print("Personalization is unavailable: the path follows the course as written.")
    print(f"Planned for: {path.level or 'no level'}\n")
    for item in path.items:
        print(
            f"{item.choice.upper():5}  {item.module.full_title}\n       {item.reason}"
        )
    print(f"\n{_summary(path)}.")
    attribution = path.attribution
    print(
        f"Content: {attribution.title} by {attribution.author} ({attribution.url}), version "
        f"{path.curriculum_version[:7]}, {attribution.licence} ({attribution.licence_url}). {path.changes}"
    )


def _summary(path: LearningPath) -> str:
    return (
        f"{path.count(Choice.STUDY)} to study, {path.count(Choice.PROVE)} to prove, "
        f"{path.count(Choice.SKIP)} skipped"
    )


if __name__ == "__main__":
    main()
