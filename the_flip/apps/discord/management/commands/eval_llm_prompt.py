"""Evaluate LLM prompt against test fixtures.

This command measures the accuracy of the Discord bot's LLM classifier by
running the prompt against test fixtures.

Usage:
    python manage.py eval_llm_prompt              # Run all fixtures
    python manage.py eval_llm_prompt --fixture multi_item_todo_list1
    python manage.py eval_llm_prompt --model claude-sonnet-4-20250514
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from constance import config
from django.core.management.base import BaseCommand, CommandError

from the_flip.apps.discord.llm import (
    ChildSuggestion,
    RecordSuggestion,
    _call_anthropic,
    _parse_tool_response,
    build_yaml_prompt,
)
from the_flip.apps.discord.llm_eval_fixtures import ALL_FIXTURES
from the_flip.apps.discord.llm_eval_types import (
    ExpectedChild,
    ExpectedSuggestion,
    LLMTestCase,
    get_all_test_machines,
)

# Max concurrent API calls - balances speed vs rate limits
# Each fixture uses ~2-3k tokens; Tier 1 limit is 30k tokens/min
# 5 concurrent = ~15k tokens burst, safe margin for rate limits
MAX_CONCURRENT_FIXTURES = 5

# Display formatting constants
SECTION_WIDTH = 60
DESCRIPTION_INDENT = " " * 14  # Aligns with "Actual:   " prefix


@dataclass
class SuggestionKey:
    """Hashable key for comparing suggestions."""

    record_type: str
    slug: str
    child_count: int = 0  # Number of expected children
    parent_record_id: int | None = None  # Expected link to existing Flipfix record
    author_id: str | None = None  # Discord user ID to attribute this record to
    source_message_ids: tuple[str, ...] | None = None  # Message IDs that contributed

    def __hash__(self):
        return hash(
            (
                self.record_type,
                self.slug,
                self.child_count,
                self.parent_record_id,
                self.author_id,
                self.source_message_ids,
            )
        )

    def __eq__(self, other):
        if not isinstance(other, SuggestionKey):
            return False
        return (
            self.record_type == other.record_type
            and self.slug == other.slug
            and self.child_count == other.child_count
            and self.parent_record_id == other.parent_record_id
            and self.author_id == other.author_id
            and self.source_message_ids == other.source_message_ids
        )


@dataclass
class PartialMatch:
    """A partial match where record_type and slug match but other fields differ."""

    expected: SuggestionKey
    actual: SuggestionKey
    actual_suggestion: RecordSuggestion  # Full suggestion for description access


@dataclass
class ComparisonResult:
    """Result of comparing expected vs actual suggestions."""

    correct: list[SuggestionKey]  # Fully matched
    missing: list[SuggestionKey]  # Expected but not found
    extra: list[RecordSuggestion]  # Found but not expected
    partial_matches: list[PartialMatch]  # Same type+slug, different attributes


@dataclass
class FixtureResult:
    """Result of evaluating a single fixture."""

    fixture_id: str
    category: str
    passed: bool
    expected: list[ExpectedSuggestion]
    actual: list[RecordSuggestion]
    comparison: ComparisonResult
    error: str | None = None


@dataclass
class EvalResults:
    """Aggregated evaluation results."""

    fixture_results: list[FixtureResult]

    @property
    def total(self) -> int:
        return len(self.fixture_results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.fixture_results if r.passed)


class Command(BaseCommand):
    help = "Evaluate LLM prompt against test fixtures"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            "-f",
            type=str,
            help="Run only a specific fixture by name",
        )
        parser.add_argument(
            "--model",
            "-m",
            type=str,
            help="Override model (e.g., claude-opus-4-20250514)",
        )

    def handle(self, *args, **options):
        asyncio.run(self._async_handle(options))

    async def _async_handle(self, options):
        # Check API key
        api_key = await self._get_api_key()
        if not api_key:
            raise CommandError(
                "ANTHROPIC_API_KEY not configured in Constance settings.\n"
                "Set it in Django admin: /admin/constance/config/"
            )

        # Check parts enabled
        parts_enabled = await self._get_parts_enabled()

        # Get fixtures
        fixtures = self._get_fixtures(parts_enabled, options.get("fixture"))
        if not fixtures:
            raise CommandError("No fixtures to run")

        # Get machines from test fixtures (self-contained, no database dependency)
        machines = get_all_test_machines()

        # Run evaluation
        model = options.get("model")
        self.stdout.write(f"\nRunning {len(fixtures)} fixtures...")
        results = await self._run_evaluation(
            fixtures=fixtures,
            machines=machines,
            api_key=api_key,
            model=model,
        )

        # Display results
        self._display_results(results)

    @sync_to_async
    def _get_api_key(self) -> str:
        return config.ANTHROPIC_API_KEY

    @sync_to_async
    def _get_parts_enabled(self) -> bool:
        return config.PARTS_ENABLED

    def _get_fixtures(
        self, parts_enabled: bool, fixture_name: str | None = None
    ) -> dict[str, LLMTestCase]:
        """Get fixtures to run, filtering by parts setting and optional name."""
        fixtures = ALL_FIXTURES.copy()

        # Filter to specific fixture if requested
        if fixture_name:
            if fixture_name not in fixtures:
                available = ", ".join(sorted(fixtures.keys()))
                raise CommandError(f"Fixture '{fixture_name}' not found.\nAvailable: {available}")
            fixtures = {fixture_name: fixtures[fixture_name]}

        # Filter out part_request fixtures if parts disabled
        if not parts_enabled:
            fixtures = {
                name: f
                for name, f in fixtures.items()
                if not any(e.record_type == "part_request" for e in f.expected)
            }

        return fixtures

    async def _run_evaluation(
        self,
        fixtures: dict[str, LLMTestCase],
        machines: list[dict],
        api_key: str,
        model: str | None = None,
    ) -> EvalResults:
        """Run all fixtures concurrently and collect results."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FIXTURES)
        results_dict: dict[str, FixtureResult] = {}
        completed_count = 0
        total = len(fixtures)

        async def run_with_semaphore(fixture_id: str, fixture: LLMTestCase) -> None:
            nonlocal completed_count
            async with semaphore:
                result = await self._evaluate_fixture(
                    fixture_id=fixture_id,
                    fixture=fixture,
                    machines=machines,
                    api_key=api_key,
                    model=model,
                )
                results_dict[fixture_id] = result
                completed_count += 1

                # Print progress as each completes
                status = (
                    self.style.ERROR("ERROR")
                    if result.error
                    else self.style.SUCCESS("PASS")
                    if result.passed
                    else self.style.ERROR("FAIL")
                )
                self.stdout.write(f"  [{completed_count}/{total}] {fixture_id}... {status}")

        # Run all fixtures concurrently (limited by semaphore)
        tasks = [run_with_semaphore(fid, fix) for fid, fix in fixtures.items()]
        await asyncio.gather(*tasks)

        # Return results in original fixture order
        fixture_results = [results_dict[fid] for fid in fixtures.keys()]
        return EvalResults(fixture_results=fixture_results)

    async def _evaluate_fixture(
        self,
        fixture_id: str,
        fixture: LLMTestCase,
        machines: list[dict],
        api_key: str,
        model: str | None = None,
    ) -> FixtureResult:
        """Evaluate a single fixture with retry on rate limit."""
        max_retries = 3
        base_delay = 5.0  # Start with 5 second delay

        for attempt in range(max_retries):
            try:
                # Build YAML prompt from GatheredContext
                user_message = build_yaml_prompt(fixture.to_context(), machines)

                # Call API (uses SYSTEM_PROMPT from llm.py by default)
                response = await _call_anthropic(api_key, user_message, None, model)

                # Parse response
                suggestions = _parse_tool_response(response)

                # Compare
                comparison = self._compare_suggestions(
                    expected=fixture.expected,
                    actual=suggestions,
                )

                passed = (
                    len(comparison.missing) == 0
                    and len(comparison.extra) == 0
                    and len(comparison.partial_matches) == 0
                )

                return FixtureResult(
                    fixture_id=fixture_id,
                    category=fixture.category,
                    passed=passed,
                    expected=fixture.expected,
                    actual=suggestions,
                    comparison=comparison,
                )

            except Exception as e:
                error_str = str(e)
                # Retry on rate limit errors
                if "429" in error_str and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                    continue

                return FixtureResult(
                    fixture_id=fixture_id,
                    category=fixture.category,
                    passed=False,
                    expected=fixture.expected,
                    actual=[],
                    comparison=ComparisonResult([], [], [], []),
                    error=error_str,
                )

        # Should never reach here, but satisfy type checker
        return FixtureResult(
            fixture_id=fixture_id,
            category=fixture.category,
            passed=False,
            expected=fixture.expected,
            actual=[],
            comparison=ComparisonResult([], [], [], []),
            error="Max retries exceeded",
        )

    def _compare_suggestions(
        self,
        expected: list[ExpectedSuggestion],
        actual: list[RecordSuggestion],
    ) -> ComparisonResult:
        """Compare expected vs actual using greedy matching.

        For optional fields (parent_record_id, author_id, source_message_ids),
        comparison only happens when the expected fixture specifies them.
        """
        correct: list[SuggestionKey] = []
        missing: list[SuggestionKey] = []
        partial_matches: list[PartialMatch] = []

        # Track which actual suggestions have been matched
        unmatched_actual = list(actual)

        # Try to match each expected suggestion
        for exp in expected:
            exp_key = self._expected_to_key(exp)
            matched = False

            # First pass: look for exact match
            for i, act in enumerate(unmatched_actual):
                if self._matches(exp, act):
                    correct.append(exp_key)
                    unmatched_actual.pop(i)
                    matched = True
                    break

            if not matched:
                # Second pass: look for partial match (same type+slug, different attrs)
                for i, act in enumerate(unmatched_actual):
                    if self._is_partial_match(exp, act):
                        partial_matches.append(
                            PartialMatch(
                                expected=exp_key,
                                actual=self._actual_to_key(act),
                                actual_suggestion=act,
                            )
                        )
                        unmatched_actual.pop(i)
                        matched = True
                        break

            if not matched:
                missing.append(exp_key)

        return ComparisonResult(
            correct=correct,
            missing=missing,
            extra=unmatched_actual,
            partial_matches=partial_matches,
        )

    def _is_partial_match(self, exp: ExpectedSuggestion, act: RecordSuggestion) -> bool:
        """Check if record_type and slug match, ignoring other attributes."""
        return exp.record_type == act.record_type and exp.slug == (act.slug or "")

    def _expected_to_key(self, exp: ExpectedSuggestion) -> SuggestionKey:
        """Convert ExpectedSuggestion to SuggestionKey for display."""
        return SuggestionKey(
            record_type=exp.record_type,
            slug=exp.slug,
            child_count=len(exp.children) if exp.children else 0,
            parent_record_id=exp.parent_record_id,
            author_id=exp.author_id,
            source_message_ids=tuple(exp.source_message_ids) if exp.source_message_ids else None,
        )

    def _actual_to_key(self, act: RecordSuggestion) -> SuggestionKey:
        """Convert RecordSuggestion to SuggestionKey for display."""
        return SuggestionKey(
            record_type=act.record_type,
            slug=act.slug or "",
            child_count=len(act.children) if act.children else 0,
            parent_record_id=act.parent_record_id,
            author_id=act.author_id,
            source_message_ids=tuple(act.source_message_ids) if act.source_message_ids else None,
        )

    def _matches(self, exp: ExpectedSuggestion, act: RecordSuggestion) -> bool:
        """Check if an actual suggestion matches an expected one.

        Required fields (record_type, slug) must match exactly.
        Optional fields are only checked when specified in the expected fixture.
        Children are optional - when exp.children is None, child count isn't checked.
        """
        # Required: record_type and slug must match
        if exp.record_type != act.record_type:
            return False
        if exp.slug != (act.slug or ""):
            return False

        # Optional: parent_record_id (only check if expected specifies it)
        if exp.parent_record_id is not None:
            if act.parent_record_id != exp.parent_record_id:
                return False

        # Optional: author_id (only check if expected specifies it)
        if exp.author_id is not None:
            if act.author_id != exp.author_id:
                return False

        # Optional: source_message_ids (only check if expected specifies it)
        if exp.source_message_ids is not None:
            if act.source_message_ids is None:
                return False
            if sorted(exp.source_message_ids) != sorted(act.source_message_ids):
                return False

        # Optional: children (only check if expected specifies them)
        # When exp.children is None, we don't check child count at all
        # When exp.children is an empty list, we expect exactly 0 children
        # When exp.children has items, we check count and optionally attribution
        if exp.children is not None:
            exp_child_count = len(exp.children)
            act_child_count = len(act.children) if act.children else 0
            if exp_child_count != act_child_count:
                return False
            # Check children attribution if both have children
            if exp.children and act.children:
                if not self._children_match(exp.children, act.children):
                    return False

        return True

    def _children_match(
        self, exp_children: list[ExpectedChild], act_children: list[ChildSuggestion]
    ) -> bool:
        """Check if child records match.

        Uses greedy matching. For each expected child, tries to find a matching
        actual child. Only checks fields specified in the expected child.
        """
        unmatched_actual = list(act_children)

        for exp_child in exp_children:
            matched = False
            for i, act_child in enumerate(unmatched_actual):
                if self._child_matches(exp_child, act_child):
                    unmatched_actual.pop(i)
                    matched = True
                    break
            if not matched:
                return False

        return True

    def _child_matches(self, exp: ExpectedChild, act: ChildSuggestion) -> bool:
        """Check if an actual child matches an expected one."""
        # Optional: author_id (only check if expected specifies it)
        if exp.author_id is not None:
            if act.author_id != exp.author_id:
                return False

        # Optional: source_message_ids (only check if expected specifies it)
        if exp.source_message_ids is not None:
            if act.source_message_ids is None:
                return False
            if sorted(exp.source_message_ids) != sorted(act.source_message_ids):
                return False

        return True

    def _display_results(self, results: EvalResults):
        """Display evaluation results grouped by category."""
        self.stdout.write("\n" + "=" * SECTION_WIDTH)

        # Overall result - simple pass/fail
        failed = results.total - results.passed
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"Overall: {failed} of {results.total} incorrect"))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Overall: {results.total} of {results.total} correct")
            )

        # Display failures
        failures = [r for r in results.fixture_results if not r.passed]
        if failures:
            self.stdout.write("\n" + "-" * SECTION_WIDTH)
            self.stdout.write("Failures")
            self.stdout.write("-" * SECTION_WIDTH)

            for result in failures:
                self._display_failure(result)

    def _display_failure(self, result: FixtureResult):
        """Display a single failure with Expected/Actual format."""
        self.stdout.write(self.style.ERROR(f"\n[FAIL] {result.fixture_id}"))

        if result.error:
            self.stdout.write(f"  Error: {result.error}")
            return

        comparison = result.comparison

        # Partial matches: same type+slug but different attributes
        if comparison.partial_matches:
            self.stdout.write("  Partial match:")
            for match in comparison.partial_matches:
                self.stdout.write(f"    Expected: {self._format_key(match.expected)}")
                self.stdout.write(f"    Actual:   {self._format_key(match.actual)}")
                self._write_description(match.actual_suggestion.description)

        # Missing: expected but no match at all
        if comparison.missing:
            self.stdout.write("  Missing:")
            for key in comparison.missing:
                self.stdout.write(f"    - {self._format_key(key)}")

        # Extra: in actual but not expected
        if comparison.extra:
            self.stdout.write("  Extra:")
            for suggestion in comparison.extra:
                self.stdout.write(f"    + {self._format_key(self._actual_to_key(suggestion))}")
                self._write_description(suggestion.description)

    def _write_description(self, description: str | None) -> None:
        """Write a description with proper indentation if present."""
        if description:
            self.stdout.write(f'{DESCRIPTION_INDENT}"{description}"')

    def _format_key(self, key: SuggestionKey) -> str:
        """Format a SuggestionKey for display."""
        parts = [f"{key.record_type} for {key.slug}"]

        if key.child_count:
            parts.append(f"(with {key.child_count} children)")

        if key.parent_record_id is not None:
            parts.append(f"parent_record_id={key.parent_record_id}")

        if key.author_id is not None:
            parts.append(f"author_id={key.author_id}")

        if key.source_message_ids is not None:
            parts.append(f"source_message_ids={list(key.source_message_ids)}")

        return " ".join(parts)
