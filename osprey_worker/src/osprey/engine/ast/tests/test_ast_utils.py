from osprey.engine.ast.ast_utils import filter_nodes, iter_nodes, replace_from_root
from osprey.engine.ast.grammar import Assign, Call, Keyword, Load, Name, Number, Root, Source, Span, Store
from osprey.engine.ast.py_ast import fixup_parents


def _make_span(source: Source) -> Span:
    return Span(source, start_line=1, start_pos=0)


def test_iter_nodes_traverses_a_parsed_source() -> None:
    source = Source(path='test.sml', contents='Result = Function(a=1)\n')

    node_types = [type(node).__name__ for node in iter_nodes(source.ast_root)]

    assert node_types == ['Root', 'Assign', 'Name', 'Call', 'Name', 'Keyword', 'Number']


def test_iter_nodes_traverses_root_statements_provided_as_a_tuple() -> None:
    # `Root.statements` (like most multi-child AST fields) is typed as `Sequence[Statement]`, not `list` - the
    # real parser always hands it a list, but anything else honoring that type hint, e.g. a tuple built by hand
    # in a test, must be walked too.
    source = Source(path='test.sml', contents='')
    span = _make_span(source)
    assign = Assign(
        target=Name(identifier='X', context=Store(), span=span), value=Number(value=1, span=span), span=span
    )

    root = Root(statements=(assign,), span=span)

    assert [type(node).__name__ for node in iter_nodes(root)] == ['Root', 'Assign', 'Name', 'Number']


def test_iter_nodes_traverses_other_sequence_fields_provided_as_tuples() -> None:
    # Same issue, but on a non-Root node (`Call.arguments`), to confirm the fix isn't Root-specific.
    source = Source(path='test.sml', contents='')
    span = _make_span(source)
    keyword = Keyword(name='a', value=Number(value=1, span=span), span=span)

    call = Call(func=Name(identifier='Function', context=Store(), span=span), arguments=(keyword,), span=span)

    assert [type(node).__name__ for node in iter_nodes(call)] == ['Call', 'Name', 'Keyword', 'Number']


def test_filter_nodes_finds_nodes_nested_under_a_tuple_sequence_field() -> None:
    source = Source(path='test.sml', contents='')
    span = _make_span(source)
    assign = Assign(
        target=Name(identifier='X', context=Store(), span=span), value=Number(value=1, span=span), span=span
    )

    root = Root(statements=(assign,), span=span)

    assert list(filter_nodes(root, Assign)) == [assign]


def test_fixup_parents_sets_parent_through_a_tuple_sequence_field() -> None:
    source = Source(path='test.sml', contents='')
    span = _make_span(source)
    number = Number(value=1, span=span)
    keyword = Keyword(name='a', value=number, span=span)
    call = Call(func=Name(identifier='Function', context=Load(), span=span), arguments=(keyword,), span=span)
    root = Root(statements=(call,), span=span)

    fixup_parents(root)

    assert number.parent is keyword
    assert keyword.parent is call
    assert call.parent is root


def test_replace_from_root_replaces_a_node_nested_under_a_tuple_sequence_field() -> None:
    # `Call.arguments` here is a tuple rather than a list, which used to make `replace_from_root` blind to
    # `number` (skipped during the walk) and, even once found, unable to swap it in place (tuples don't
    # support item assignment).
    source = Source(path='test.sml', contents='')
    span = _make_span(source)
    number = Number(value=1, span=span)
    keyword = Keyword(name='a', value=number, span=span)
    call = Call(func=Name(identifier='Function', context=Load(), span=span), arguments=(keyword,), span=span)
    assign = Assign(target=Name(identifier='X', context=Store(), span=span), value=call, span=span)
    root = Root(statements=(assign,), span=span)
    fixup_parents(root)

    replacement = Number(value=2, span=span)
    new_statement = replace_from_root(number, replacement)

    assert isinstance(new_statement, Assign)
    assert isinstance(new_statement.value, Call)
    # The rebuilt sequence still contains the replacement, and is still a tuple.
    assert new_statement.value.arguments == (Keyword(name='a', value=replacement, span=span),)
    assert isinstance(new_statement.value.arguments, tuple)
