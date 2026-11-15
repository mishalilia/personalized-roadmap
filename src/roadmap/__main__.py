"""Command line: `python -m roadmap fetch | plan <profile> | compare | checkpoints <module>...`, with
`--provider` to pick a model provider."""

import argparse
import itertools
import logging
import sys
from pathlib import Path

from .checkpoints import CheckpointGenerator, CheckpointStore, Status, verify_problem
from .curriculum import Module
from .events import EventLog
from .config import Settings
from .curriculum import Level
from .onboarding import LearnerProfile, load_profiles
from .path import Choice, LearningPath, path_difference
from .service import Roadmap
from .llm import LLMUnavailable, connect
from .source import CurriculumSource, checkout, load_curriculum


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
    parser.set_defaults(provider=None, verbose=False, curriculum=None)
    commands = parser.add_subparsers(required=True)

    model_options = argparse.ArgumentParser(add_help=False)
    model_options.add_argument(
        "--provider", help="a provider from config/llm.yaml, instead of LLM_PROVIDER"
    )
    model_options.add_argument(
        "--verbose", action="store_true", help="log each model call: time and tokens"
    )
    model_options.add_argument(
        "--curriculum",
        help="a curriculum version from config/curriculum.yaml, such as 2026-10-06; "
        "the newest by default",
    )

    fetch = commands.add_parser(
        "fetch", help="check out every curriculum version in config/curriculum.yaml"
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

    generate = commands.add_parser(
        "checkpoints",
        parents=[model_options],
        help="write draft checkpoint questions for modules, to be reviewed",
    )
    generate.add_argument("modules", nargs="*", help="module ids, as in a path")
    generate.add_argument(
        "--verify",
        action="store_true",
        help="run each reference solution against its tests instead of generating",
    )
    generate.add_argument("--all", action="store_true", help="every module")
    generate.add_argument(
        "--force", action="store_true", help="also replace reviewed checkpoints"
    )
    generate.set_defaults(command=_checkpoints)

    report = commands.add_parser(
        "report",
        help="where learners who share their progress stop, per module",
    )
    report.add_argument(
        "--curriculum", help="a curriculum version; the newest by default"
    )
    report.set_defaults(command=_report)
    return parser


def _fetch(args: argparse.Namespace, settings: Settings) -> None:
    source = CurriculumSource.from_file(settings.curriculum_file)
    for version in source.versions:
        docs_dir = checkout(source, version, settings.curricula_dir)
        print(
            f"Curriculum {version.name} ({version.ref[:7]}) is checked out in {docs_dir}"
        )


def _plan(args: argparse.Namespace, settings: Settings) -> None:
    roadmap = Roadmap.from_settings(settings, args.curriculum)
    path = _build_path(roadmap, _find_profile(settings, args.profile), args.level)
    _print_path(path)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(path.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nWritten to {args.out}")


def _compare(args: argparse.Namespace, settings: Settings) -> None:
    roadmap = Roadmap.from_settings(settings, args.curriculum)
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


def _checkpoints(args: argparse.Namespace, settings: Settings) -> None:
    source = CurriculumSource.from_file(settings.curriculum_file)
    version = source.version(args.curriculum)
    curriculum = load_curriculum(source, version, settings.curricula_dir)
    modules = {module.id: module for module in curriculum.modules}
    store = CheckpointStore(settings.checkpoints_dir / version.name)
    if args.verify:
        _verify(store, curriculum.modules)
        return
    wanted = list(modules) if args.all else args.modules
    if not wanted:
        sys.exit("Name modules to generate checkpoints for, or give --all.")
    if unknown := [module_id for module_id in wanted if module_id not in modules]:
        sys.exit(f"Unknown modules: {', '.join(unknown)}")
    llm = connect(settings)
    if llm is None:
        sys.exit("Generating checkpoints needs a model key in .env.")
    generator = CheckpointGenerator(llm, ", ".join(llm.models))
    for module_id in wanted:
        existing = store.load(module_id)
        if (
            existing is not None
            and existing.status is Status.REVIEWED
            and not args.force
        ):
            print(f"Kept {module_id}: it is reviewed (use --force to replace it)")
            continue
        try:
            checkpoint = generator.generate(modules[module_id], curriculum.version)
        except LLMUnavailable as error:
            print(f"No checkpoint for {module_id}: {error}")
            continue
        print(f"Draft for {module_id} written to {store.save(checkpoint)}: review it")


def _verify(store: CheckpointStore, modules: list[Module]) -> None:
    failed = False
    for module in modules:
        checkpoint = store.load(module.id)
        if checkpoint is None or checkpoint.problem is None:
            continue
        error = verify_problem(checkpoint.problem)
        failed = failed or error is not None
        print(
            f"{'ok  ' if error is None else 'FAIL'} {module.id}"
            + (f"\n{error}" if error else "")
        )
    if failed:
        sys.exit(1)


def _report(args: argparse.Namespace, settings: Settings) -> None:
    source = CurriculumSource.from_file(settings.curriculum_file)
    version = source.version(args.curriculum)
    curriculum = load_curriculum(source, version, settings.curricula_dir)
    file = settings.events_file
    if not file.exists():
        sys.exit(f"No events yet: {file} does not exist.")
    report = EventLog(file).report(
        curriculum.version, [m.id for m in curriculum.modules]
    )
    print(f"{report.paths} shared paths, curriculum {version.name}\n")
    print(f"{'module':60} {'included':>8} {'finished':>8} {'failed':>7} {'stopped':>7}")
    for row in report.modules:
        print(
            f"{row.module_id:60} {row.included:8} {row.finished:8} {row.failed_once:7} "
            f"{row.stopped_here:7}"
        )


if __name__ == "__main__":
    main()
