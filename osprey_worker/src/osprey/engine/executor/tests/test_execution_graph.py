"""Regression coverage for `_topologically_sort_dependency_chain_for`.

Before the fix, the recursion descended into `chain.dependent_on` *before* consulting the
`visited` set, so a chain reachable by N distinct paths from a source's statements was
walked N times. For a diamond-shaped feature graph (layered features that each reference a
lower feature more than once) N is exponential in the graph depth, so compilation could
take minutes or hang. The fix consults `visited` first, making the walk O(V + E): every
chain's `dependent_on` is iterated exactly once.
"""

from osprey.engine.conftest import RunValidationFunction
from osprey.engine.executor.dependency_chain import DependencyChain
from osprey.engine.executor.execution_graph import (
    _topologically_sort_dependency_chain_for,
    compile_execution_graph,
)


class _TraversalBudget:
    """Counts `dependent_on` iterations and trips fast once a sane ceiling is passed.

    Pre-fix, a depth-D doubling diamond drives the count to 2**D; this lets the test fail
    immediately instead of grinding through the full exponential blowup.
    """

    def __init__(self, limit: int) -> None:
        self.count = 0
        self.limit = limit

    def charge(self) -> None:
        self.count += 1
        if self.count > self.limit:
            raise AssertionError(
                f'topological sort iterated dependent_on {self.count} times (limit {self.limit}); '
                'the visited-set check is no longer short-circuiting re-traversal of shared sub-DAGs'
            )


class _CountingDeps(tuple):  # type: ignore[type-arg]
    """A `dependent_on` tuple that reports each iteration to a `_TraversalBudget`."""

    def __new__(cls, items: tuple, budget: _TraversalBudget) -> '_CountingDeps':
        self = super().__new__(cls, items)
        self._budget = budget
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        self._budget.charge()
        return super().__iter__()


class _FakeAstRoot:
    def __init__(self, statements: list[object]) -> None:
        self.statements = statements


class _FakeSource:
    def __init__(self, statements: list[object]) -> None:
        self.ast_root = _FakeAstRoot(statements)


class _FakeGraph:
    def __init__(self, chain_by_statement: dict[object, DependencyChain]) -> None:
        self._chain_by_statement = chain_by_statement

    def get_dependency_chain(self, statement: object) -> DependencyChain:
        return self._chain_by_statement[statement]


def _build_doubling_diamond(depth: int, budget: _TraversalBudget) -> tuple[DependencyChain, list[DependencyChain]]:
    """Build `depth` layers where every layer references the layer below it twice.

    The shared leaf is reachable by 2**depth distinct paths from the root, so pre-fix the
    recursion visits it 2**depth times; post-fix every chain is walked exactly once.
    Returns the root chain and every chain ordered leaf -> root (the expected topo order).
    """
    leaf = DependencyChain(executor=object(), dependent_on=_CountingDeps((), budget))  # type: ignore[arg-type]
    layers = [leaf]
    node = leaf
    for _ in range(depth):
        node = DependencyChain(
            executor=object(),  # type: ignore[arg-type]
            dependent_on=_CountingDeps((node, node), budget),
        )
        layers.append(node)
    return node, layers


def test_topological_sort_walks_each_chain_once_for_diamond_graph() -> None:
    depth = 30  # pre-fix: 2**30 dependent_on iterations; post-fix: depth + 1
    budget = _TraversalBudget(limit=10_000)
    root, layers = _build_doubling_diamond(depth, budget)

    statement = object()
    graph = _FakeGraph({statement: root})
    source = _FakeSource([statement])

    ordered = _topologically_sort_dependency_chain_for(graph, source)  # type: ignore[arg-type]

    # Linear work: one iteration of dependent_on per distinct chain.
    assert budget.count == depth + 1
    # Order is still a valid post-order: leaf first, root last, no repeats.
    assert list(ordered) == layers


def test_topological_sort_orders_shared_dependency_before_every_dependent() -> None:
    budget = _TraversalBudget(limit=1_000)
    shared = DependencyChain(executor=object(), dependent_on=_CountingDeps((), budget))  # type: ignore[arg-type]
    left = DependencyChain(executor=object(), dependent_on=_CountingDeps((shared,), budget))  # type: ignore[arg-type]
    right = DependencyChain(executor=object(), dependent_on=_CountingDeps((shared,), budget))  # type: ignore[arg-type]
    # `root` reaches `shared` three ways: directly, via `left`, and via `right`.
    root = DependencyChain(
        executor=object(),  # type: ignore[arg-type]
        dependent_on=_CountingDeps((left, shared, right), budget),
    )

    statement = object()
    ordered = _topologically_sort_dependency_chain_for(
        _FakeGraph({statement: root}),  # type: ignore[arg-type]
        _FakeSource([statement]),
    )

    positions = {chain: index for index, chain in enumerate(ordered)}
    assert positions[shared] < positions[left]
    assert positions[shared] < positions[right]
    assert positions[left] < positions[root]
    assert positions[right] < positions[root]
    assert len(ordered) == 4
    assert budget.count == 4


def test_compile_execution_graph_handles_diamond_feature_graph(
    run_validation: RunValidationFunction,
) -> None:
    """End-to-end: a diamond-shaped ruleset compiles to a valid, repeat-free schedule."""
    depth = 14
    lines = ['_L0 = 1 + 1']
    lines += [f'_L{i} = _L{i - 1} + _L{i - 1}' for i in range(1, depth + 1)]
    lines.append(f'Result = _L{depth}')
    validated = run_validation({'main.sml': '\n'.join(lines)})

    graph = compile_execution_graph(validated)

    ordered = graph.get_sorted_dependency_chain(graph.get_entry_point())
    seen: set[DependencyChain] = set()
    for chain in ordered:
        for predecessor in chain.dependent_on:
            assert predecessor in seen, 'a dependency was scheduled after its dependent'
        seen.add(chain)
    assert len(seen) == len(ordered), 'a chain appears more than once in the schedule'
