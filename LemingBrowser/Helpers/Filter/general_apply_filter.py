from __future__ import annotations

from typing import Any
from itertools import count
import os
import re
import sys
# Getting the name of the directory where this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory.
parent = os.path.dirname(current)
# Adding the parent directory to sys.path.
sys.path.append(parent)

from Exceptions.FilterError import FilterError
from CPP.load_filter_cpp_helper import load_cpp_vector_filter_helpers
from Provenance.provenance import register_provenance

_CUT_ID = count()

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"')


def global_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    cut_filter: str | list[str] | None,
) -> Any | list[Any]:
    """
    Apply scalar or element-wise cuts to one or more RDataFrames.
    If condition is not met it handled RVec and scalar variables and also deletes rows in case nothing left
    Supports:
        scalar numbers
        scalar bool
        scalar std::string

        RVec<int>
        RVec<float>
        RVec<double>
        RVec<bool>
        RVec<std::string>

        RVec<char> / RVec<Char_t>
            treated as one scalar string.

    Returns:
        one RDataFrame if one was supplied,
        otherwise a list of RDataFrames.

    Provenance is registered once for every filtered dataframe.
    """

    single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    dataframe_list = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

    filters = _normalize_filters(
        cut_filter
    )

    # ---------------------------------------------------------
    # No filtering requested
    # ---------------------------------------------------------

    if not filters:
        return (
            dataframe_list[0]
            if single_dataframe
            else dataframe_list
        )

    # ---------------------------------------------------------
    # Load C++ helpers
    # ---------------------------------------------------------

    load_cpp_vector_filter_helpers()

    # ---------------------------------------------------------
    # Apply filtering
    # ---------------------------------------------------------

    filtered_dataframes = []

    for index, dataframe in enumerate(
        dataframe_list,
        start=1,
    ):
        parent_dataframe = dataframe

        filtered_dataframe = _filter_dataframe(
            dataframe,
            filters,
            dataframe_index=index,
        )

        # -----------------------------------------------------
        # Register provenance
        # -----------------------------------------------------

        register_provenance(
            filtered_dataframe,
            kind="dataframe",
            operation="global filter",
            parameters={
                "cuts": list(filters),
                "combined_cut": " && ".join(
                    f"({expression})"
                    for expression in filters
                ),
            },
            parents=[
                parent_dataframe,
            ],
        )

        filtered_dataframes.append(
            filtered_dataframe
        )

    # ---------------------------------------------------------
    # Preserve input shape
    # ---------------------------------------------------------

    return (
        filtered_dataframes[0]
        if single_dataframe
        else filtered_dataframes
    )

def _filter_dataframe(
    dataframe: Any,
    filters: list[str],
    dataframe_index: int,
) -> Any:
    """Apply all cuts to one dataframe.

    Scalar-only cuts:
        use normal RDataFrame.Filter().

    Cuts involving genuine RVec columns:
        1. combine all filters,
        2. create one mask,
        3. reject rows where no element passes,
        4. apply that mask once to all aligned RVec columns.

    RVec<char>/RVec<Char_t> is treated as one scalar string.
    """

    column_names = tuple(
        str(name)
        for name in dataframe.GetColumnNames()
    )

    available_columns = set(column_names)

    column_types = {
        name: str(dataframe.GetColumnType(name))
        for name in column_names
    }

    vector_columns = tuple(
        name
        for name in column_names
        if _is_maskable_rvec_type(
            column_types[name]
        )
    )

    referenced_columns: set[str] = set()

    for filter_index, expression in enumerate(
        filters,
        start=1,
    ):
        referenced = _referenced_columns(
            expression,
            available_columns,
        )

        if not referenced:
            raise FilterError(
                "The cut does not reference any dataframe column.\n"
                f"Dataset: {dataframe_index}\n"
                f"Cut: {filter_index}\n"
                f"Expression: {expression}"
            )

        referenced_columns.update(referenced)

    combined_expression = " && ".join(
        f"({expression})"
        for expression in filters
    )

    combined_expression = _rewrite_string_comparisons(
        combined_expression,
        column_types,
    )

    combined_expression = _rewrite_bool_vector_negations(
        combined_expression,
        column_types,
    )

    combined_expression = (
        _rewrite_vector_logical_operations(
            combined_expression,
            column_types,
        )
    )

    uses_vector = any(
        _is_maskable_rvec_type(
            column_types[name]
        )
        for name in referenced_columns
    )

    label = f"Dataset {dataframe_index}, user cut"

    try:
        # Scalar-only path.
        if not uses_vector:
            return dataframe.Filter(
                combined_expression,
                label,
            )

        cut_id = next(_CUT_ID)
        mask_column = f"__smartcut_mask_{cut_id}"

        # ROOT can behave unexpectedly for compound logical
        # expressions involving multiple RVec<bool> columns.
        #
        # Convert referenced bool vectors to temporary RVec<int>
        # columns before evaluating the expression.
        bool_vector_index = 0

        for column_name in sorted(referenced_columns):
            compact_type = _compact_cpp_type(
                column_types[column_name]
            )

            if compact_type not in (
                "ROOT::VecOps::RVec<bool>",
                "RVec<bool>",
            ):
                continue

            temporary_column = (
                f"__smartcut_boolvec_"
                f"{cut_id}_{bool_vector_index}"
            )

            bool_vector_index += 1

            dataframe = dataframe.Define(
                temporary_column,
                (
                    "SmartRDFCut::BoolVectorToInt("
                    f"{column_name}"
                    ")"
                ),
            )

            combined_expression = (
                _replace_identifier_outside_strings(
                    combined_expression,
                    column_name,
                    temporary_column,
                )
            )

        dataframe = dataframe.Define(
            mask_column,
            combined_expression,
        )

        dataframe = dataframe.Filter(
            f"ROOT::VecOps::Any({mask_column})",
            label,
        )

        for column_name in vector_columns:
            dataframe = dataframe.Redefine(
                column_name,
                (
                    "SmartRDFCut::ApplyMask("
                    f"{column_name}, "
                    f"{mask_column}, "
                    f'"{_escape_cpp_string(column_name)}"'
                    ")"
                ),
            )

        return dataframe

    except FilterError:
        raise

    except Exception as error:
        raise FilterError(
            "Could not compile or apply the dataframe cut.\n"
            f"Dataset: {dataframe_index}\n"
            f"Expression: {combined_expression}\n"
            f"ROOT error: {error}"
        ) from error


def _normalize_filters(
    cut_filter: str | list[str] | None,
) -> list[str]:
    if cut_filter is None:
        return []

    if isinstance(cut_filter, str):
        filters = [cut_filter]
    else:
        filters = list(cut_filter)

    result: list[str] = []

    for index, expression in enumerate(
        filters,
        start=1,
    ):
        if not isinstance(expression, str):
            raise FilterError(
                f"Cut filter {index} must be a string."
            )

        expression = expression.strip()

        if expression:
            result.append(expression)

    return result


def _referenced_columns(
    expression: str,
    available_columns: set[str],
) -> set[str]:
    """Find dataframe columns referenced in the expression.

    String contents are removed first so that text such as
    "Muon_Entrance" is never mistaken for a column name.
    """

    expression_without_strings = _STRING_LITERAL_RE.sub(
        "",
        expression,
    )

    identifiers = set(
        _IDENTIFIER_RE.findall(
            expression_without_strings
        )
    )

    return identifiers & available_columns


def _compact_cpp_type(
    column_type: str,
) -> str:
    return column_type.replace(" ", "")


def _is_rvec_type(
    column_type: str,
) -> bool:
    compact = _compact_cpp_type(column_type)

    return (
        "ROOT::VecOps::RVec<" in compact
        or compact.startswith("RVec<")
    )


def _is_char_array_type(
    column_type: str,
) -> bool:
    """Detect a character buffer representing ONE string.

    Examples:
        RVec<Char_t>
        RVec<char>
    """

    compact = _compact_cpp_type(column_type)

    return (
        "RVec<Char_t>" in compact
        or "RVec<char>" in compact
        or "RVec<signedchar>" in compact
        or "RVec<unsignedchar>" in compact
    )


def _is_string_vector_type(
    column_type: str,
) -> bool:
    """Detect a genuine list/vector of strings."""

    compact = _compact_cpp_type(column_type)

    return (
        "RVec<std::string>" in compact
        or "RVec<string>" in compact
    )


def _is_maskable_rvec_type(
    column_type: str,
) -> bool:
    """Genuine element-wise vectors are maskable.

    Included:
        RVec<int>
        RVec<double>
        RVec<float>
        RVec<bool>
        RVec<std::string>

    Excluded:
        RVec<char>
        RVec<Char_t>

    because those are treated as one string.
    """

    return (
        _is_rvec_type(column_type)
        and not _is_char_array_type(column_type)
    )


def _rewrite_string_comparisons(
    expression: str,
    column_types: dict[str, str],
) -> str:
    """Rewrite string comparisons when ROOT needs explicit help.

    RVec<char>/RVec<Char_t>:
        treated as one scalar string.

    RVec<std::string>:
        treated as an element-wise vector of strings.
    """

    rewritten = expression

    string_literal = r'"(?:\\.|[^"\\])*"'

    for column_name in sorted(
        column_types,
        key=len,
        reverse=True,
    ):
        column_type = column_types[column_name]

        column_pattern = (
            r"(?<![A-Za-z0-9_])"
            + re.escape(column_name)
            + r"(?![A-Za-z0-9_])"
        )

        if _is_char_array_type(column_type):
            rewritten = re.sub(
                rf"({column_pattern})"
                rf"\s*==\s*"
                rf"({string_literal})",
                (
                    r"SmartRDFCut::CharArrayEquals("
                    r"\1, \2)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({column_pattern})"
                rf"\s*!=\s*"
                rf"({string_literal})",
                (
                    r"!SmartRDFCut::CharArrayEquals("
                    r"\1, \2)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({string_literal})"
                rf"\s*==\s*"
                rf"({column_pattern})",
                (
                    r"SmartRDFCut::CharArrayEquals("
                    r"\2, \1)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({string_literal})"
                rf"\s*!=\s*"
                rf"({column_pattern})",
                (
                    r"!SmartRDFCut::CharArrayEquals("
                    r"\2, \1)"
                ),
                rewritten,
            )

        elif _is_string_vector_type(column_type):
            rewritten = re.sub(
                rf"({column_pattern})"
                rf"\s*==\s*"
                rf"({string_literal})",
                (
                    r"SmartRDFCut::StringVectorEquals("
                    r"\1, \2)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({column_pattern})"
                rf"\s*!=\s*"
                rf"({string_literal})",
                (
                    r"SmartRDFCut::StringVectorNotEquals("
                    r"\1, \2)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({string_literal})"
                rf"\s*==\s*"
                rf"({column_pattern})",
                (
                    r"SmartRDFCut::StringVectorEquals("
                    r"\2, \1)"
                ),
                rewritten,
            )

            rewritten = re.sub(
                rf"({string_literal})"
                rf"\s*!=\s*"
                rf"({column_pattern})",
                (
                    r"SmartRDFCut::StringVectorNotEquals("
                    r"\2, \1)"
                ),
                rewritten,
            )

    return rewritten


def _escape_cpp_string(
    value: str,
) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )

def _rewrite_bool_vector_negations(
    expression: str,
    column_types: dict[str, str],
) -> str:
    """
    Rewrite unary ! on RVec<bool> columns.

    Example:
        !A

    becomes:
        (A == false)

    This avoids problematic unary negation behaviour
    for RVec<bool> in ROOT expressions.
    """

    rewritten = expression

    for column_name in sorted(
        column_types,
        key=len,
        reverse=True,
    ):
        compact_type = _compact_cpp_type(
            column_types[column_name]
        )

        is_bool_vector = (
            "ROOT::VecOps::RVec<bool>" in compact_type
            or compact_type == "RVec<bool>"
        )

        if not is_bool_vector:
            continue

        column_pattern = (
            r"(?<![A-Za-z0-9_])"
            + re.escape(column_name)
            + r"(?![A-Za-z0-9_])"
        )

        rewritten = re.sub(
            rf"!\s*({column_pattern})",
            rf"(\1 == false)",
            rewritten,
        )

    return rewritten

def _replace_identifier_outside_strings(
    expression: str,
    identifier: str,
    replacement: str,
) -> str:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(identifier)
        + r"(?![A-Za-z0-9_])"
    )

    pieces = []
    last_end = 0

    for match in _STRING_LITERAL_RE.finditer(expression):
        pieces.append(
            pattern.sub(
                replacement,
                expression[last_end:match.start()],
            )
        )

        # Keep string literals completely untouched.
        pieces.append(match.group(0))
        last_end = match.end()

    pieces.append(
        pattern.sub(
            replacement,
            expression[last_end:],
        )
    )

    return "".join(pieces)

def _outer_parentheses_wrap_all(
    expression: str,
) -> bool:
    """
    Return True if the first '(' and last ')' wrap
    the complete expression.
    """

    if not (
        expression.startswith("(")
        and expression.endswith(")")
    ):
        return False

    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(expression):
        if in_string:
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True
            continue

        if char == "(":
            depth += 1

        elif char == ")":
            depth -= 1

            if (
                depth == 0
                and index != len(expression) - 1
            ):
                return False

    return depth == 0


def _split_top_level_logic(
    expression: str,
    operator: str,
) -> tuple[str, str] | None:
    """
    Find the right-most top-level && or ||.

    Right-most preserves normal C++ left associativity:

        A && B && C

    means:

        (A && B) && C
    """

    depth = 0
    in_string = False
    escaped = False
    positions: list[int] = []

    index = 0

    while index < len(expression):
        char = expression[index]

        if in_string:
            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            index += 1
            continue

        if char == '"':
            in_string = True
            index += 1
            continue

        if char == "(":
            depth += 1
            index += 1
            continue

        if char == ")":
            depth -= 1
            index += 1
            continue

        if (
            depth == 0
            and expression.startswith(
                operator,
                index,
            )
        ):
            positions.append(index)
            index += len(operator)
            continue

        index += 1

    if not positions:
        return None

    position = positions[-1]

    return (
        expression[:position].strip(),
        expression[
            position + len(operator):
        ].strip(),
    )


def _expression_is_vector(
    expression: str,
    column_types: dict[str, str],
) -> bool:
    """
    Determine whether an expression participates in
    element-wise RVec logic.
    """

    expression = expression.strip()

    # Explicit reductions return scalars.
    if re.match(
        r"^(?:ROOT::VecOps::)?"
        r"(?:Any|All|Sum|Mean|Min|Max)\s*\(",
        expression,
    ):
        return False

    referenced = _referenced_columns(
        expression,
        set(column_types),
    )

    return any(
        _is_maskable_rvec_type(
            column_types[column_name]
        )
        for column_name in referenced
    )


def _rewrite_vector_logical_operations(
    expression: str,
    column_types: dict[str, str],
) -> str:
    """
    Route vector-to-vector && / || through SmartRDFCut.

    Normal scalar C++ logic is left untouched.

    C++ precedence is preserved:
        && before ||
    """

    expression = expression.strip()

    # Remove one complete outer (...) while parsing.
    # Add it back afterward.
    if _outer_parentheses_wrap_all(
        expression
    ):
        inner = expression[1:-1].strip()

        return (
            "("
            + _rewrite_vector_logical_operations(
                inner,
                column_types,
            )
            + ")"
        )

    # ---------------------------------------------------------
    # || has LOWER precedence than &&
    # so split on || first.
    # ---------------------------------------------------------

    split = _split_top_level_logic(
        expression,
        "||",
    )

    if split is not None:
        left, right = split

        rewritten_left = (
            _rewrite_vector_logical_operations(
                left,
                column_types,
            )
        )

        rewritten_right = (
            _rewrite_vector_logical_operations(
                right,
                column_types,
            )
        )

        if (
            _expression_is_vector(
                left,
                column_types,
            )
            and
            _expression_is_vector(
                right,
                column_types,
            )
        ):
            return (
                "SmartRDFCut::LogicalOr("
                f"{rewritten_left}, "
                f"{rewritten_right}"
                ")"
            )

        return (
            f"({rewritten_left})"
            " || "
            f"({rewritten_right})"
        )

    # ---------------------------------------------------------
    # &&
    # ---------------------------------------------------------

    split = _split_top_level_logic(
        expression,
        "&&",
    )

    if split is not None:
        left, right = split

        rewritten_left = (
            _rewrite_vector_logical_operations(
                left,
                column_types,
            )
        )

        rewritten_right = (
            _rewrite_vector_logical_operations(
                right,
                column_types,
            )
        )

        if (
            _expression_is_vector(
                left,
                column_types,
            )
            and
            _expression_is_vector(
                right,
                column_types,
            )
        ):
            return (
                "SmartRDFCut::LogicalAnd("
                f"{rewritten_left}, "
                f"{rewritten_right}"
                ")"
            )

        return (
            f"({rewritten_left})"
            " && "
            f"({rewritten_right})"
        )

    return expression