from typing import Iterator, List, Optional

import mpi4py
from httomo.runner.output_ref import OutputRef
from httomo.runner.pipeline import Pipeline
from httomo.utils import Colour, Pattern, log_once
from httomo.runner.method_wrapper import MethodWrapper


class PlatformSection:
    """Represents on section of a pipeline that can be executed on the same platform,
    and has the same dataset pattern."""

    def __init__(
        self,
        pattern: Pattern,
        max_slices: int,
        methods: List[MethodWrapper],
        is_last: bool = False,
    ):
        self.pattern = pattern
        self.max_slices = max_slices
        self.methods = methods
        self.is_last = is_last

    def __iter__(self) -> Iterator[MethodWrapper]:
        return iter(self.methods)

    def __len__(self) -> int:
        return len(self.methods)

    def __getitem__(self, idx: int) -> MethodWrapper:
        return self.methods[idx]


def sectionize(pipeline: Pipeline) -> List[PlatformSection]:
    sections: List[PlatformSection] = []

    # The functions below are internal to reduce duplication

    def is_pattern_compatible(a: Pattern, b: Pattern) -> bool:
        return a == Pattern.all or b == Pattern.all or a == b

    # loop carried variables, to build up the sections
    current_pattern: Pattern = pipeline.loader_pattern
    current_methods: List[MethodWrapper] = []

    def references_previous_method(method: MethodWrapper) -> bool:
        # find output references in the method's parameters
        refs = [v for v in method.config_params.values() if isinstance(v, OutputRef)]
        # see if any of them reference methods in the current method list
        for r in refs:
            if r.method in current_methods:
                return True
        return False

    def finish_section():
        sections.append(
            PlatformSection(
                current_pattern,
                0,
                current_methods,
            )
        )

    for method in pipeline:
        if not is_pattern_compatible(
            current_pattern, method.pattern
        ) or references_previous_method(method):
            finish_section()
            if method.pattern != Pattern.all:
                current_pattern = method.pattern
            current_methods = [method]
        else:
            current_methods.append(method)
            if current_pattern == Pattern.all:
                current_pattern = method.pattern

    finish_section()
    sections[-1].is_last = True

    _backpropagate_section_patterns(pipeline, sections)
    _finalize_patterns(pipeline, sections)
    _set_method_patterns(sections)

    return sections


def _backpropagate_section_patterns(
    pipeline: Pipeline, sections: List[PlatformSection]
):
    """Performs a backward sweep through the patterns of each section, propagating
    from the last section backwards in case the previous ones have Pattern.all.
    This makes sure the loader eventually gets the pattern that the section that follows
    has.

    Only special case: All methods have Pattern.all, which is handled separately
    """
    last_pattern = Pattern.all
    for s in reversed(sections):
        if s.pattern == Pattern.all:
            s.pattern = last_pattern
        last_pattern = s.pattern
    if pipeline.loader_pattern == Pattern.all:
        pipeline.loader_pattern = last_pattern
    elif pipeline.loader_pattern != last_pattern:
        pipeline.loader_reslice = True


def _finalize_patterns(
    pipeline: Pipeline,
    sections: List[PlatformSection],
    default_pattern=Pattern.projection,
):
    # final possible ambiguity: everything is Pattern.all -> pick projection by default
    if len(sections) > 0 and sections[0].pattern == Pattern.all:
        log_once(
            "All pipeline sections support all patterns: choosing projection",
            mpi4py.MPI.COMM_WORLD,
            Colour.YELLOW,
            level=2,
        )
        for s in sections:
            s.pattern = default_pattern
        pipeline.loader_pattern = default_pattern

    assert all(s.pattern != Pattern.all for s in sections)
    assert pipeline.loader_pattern != Pattern.all


def _set_method_patterns(sections: List[PlatformSection]):
    for s in sections:
        for m in s:
            m.pattern = s.pattern
