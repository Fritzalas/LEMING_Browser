from __future__ import annotations
from typing import Any
from itertools import count
import os
import re
import sys

current = os.path.dirname(
    os.path.realpath(__file__)
)
parent = os.path.dirname(
    current
)
if parent not in sys.path:
    sys.path.append(
        parent
    )

from Exceptions.FilterError import FilterError
from CPP.load_filter_cpp_helper import (
    load_cpp_vector_filter_helpers
)
from Provenance.provenance import (
    register_provenance
)

# -----------------------------------------------------------------
# This function is just a helper function if in the future someone
# Decides that he wants to filter only a specific column
# Ranging can do the same job in histograms :)
# -----------------------------------------------------------------

# -------------------------------------------------------------
# Internal state / regex
# -------------------------------------------------------------

_CUT_ID = count()

_IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*"
)

_STRING_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\])*"'
)


def column_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    cut_filter: str | list[str] | None,
) -> Any | list[Any]:
    """
    Apply element-wise cuts only to RVec columns referenced by the cut.

    Unlike global_filter_cut_rdataframe:

        - dataframe rows are NOT removed
        - unrelated columns are NOT modified
        - only referenced maskable RVec columns are Redefined

    Examples
    --------

    One cut:

        cut_filter = "Muon_PT > 500"

    If Muon_PT is an RVec, only the elements of Muon_PT passing
    the cut are retained.

    Multiple cuts:

        cut_filter = [
            "Muon_PT > 500",
            "Muon_E > 1000",
        ]

    A common mask is constructed from the cuts and is applied only
    to the referenced maskable RVec columns.

    Provenance
    ----------
    A provenance node is registered for every dataframe whenever a
    non-empty column-filter request is supplied.

    The provenance node records whether an element-wise mask was
    actually applied.
    """

    # ---------------------------------------------------------
    # Normalize dataframe input
    # ---------------------------------------------------------

    single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    dataframe_list = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

    if not dataframe_list:
        raise FilterError(
            "At least one dataframe must be supplied."
        )

    # ---------------------------------------------------------
    # Normalize cut input
    # ---------------------------------------------------------

    filters = _normalize_filters(
        cut_filter
    )

    # No cut means no operation and therefore no provenance node.
    if not filters:
        return (
            dataframe_list[0]
            if single_dataframe
            else dataframe_list
        )

    # ---------------------------------------------------------
    # Load C++ filtering helpers
    # ---------------------------------------------------------

    load_cpp_vector_filter_helpers()

    filtered_dataframes: list[Any] = []

    # ---------------------------------------------------------
    # Process every dataframe independently
    # ---------------------------------------------------------

    for dataframe_index, dataframe in enumerate(
        dataframe_list,
        start=1,
    ):
        # Keep the original dataframe before any Define/Redefine.
        # Provenance will point back to this state.
        parent_dataframe = dataframe

        # -----------------------------------------------------
        # Inspect dataframe columns
        # -----------------------------------------------------

        column_names = tuple(
            str(name)
            for name in dataframe.GetColumnNames()
        )

        available_columns = set(
            column_names
        )

        column_types = {
            name: str(
                dataframe.GetColumnType(name)
            )
            for name in column_names
        }

        # -----------------------------------------------------
        # Determine which columns each cut references
        # -----------------------------------------------------

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
                    "The column cut does not reference any "
                    "dataframe column.\n"
                    f"Dataset: {dataframe_index}\n"
                    f"Cut: {filter_index}\n"
                    f"Expression: {expression}"
                )

            referenced_columns.update(
                referenced
            )

        # -----------------------------------------------------
        # Find referenced columns that can actually be masked
        # -----------------------------------------------------

        vector_columns_to_filter = [
            column_name
            for column_name in sorted(
                referenced_columns
            )
            if _is_maskable_rvec_type(
                column_types[column_name]
            )
        ]

        scalar_or_nonmaskable_columns = [
            column_name
            for column_name in sorted(
                referenced_columns
            )
            if column_name
            not in vector_columns_to_filter
        ]

        # -----------------------------------------------------
        # No maskable RVec column
        #
        # Nothing in the dataframe changes, but the requested
        # column-filter operation is still recorded.
        # -----------------------------------------------------

        if not vector_columns_to_filter:
            register_provenance(
                dataframe,
                kind="dataframe",
                operation="column filter",
                parameters={
                    "cuts": list(
                        filters
                    ),
                    "referenced_columns": sorted(
                        referenced_columns
                    ),
                    "filtered_columns": [],
                    "nonmaskable_columns": (
                        scalar_or_nonmaskable_columns
                    ),
                    "filters_rows": False,
                    "modifies_unrelated_columns": False,
                    "applied": False,
                    "reason": (
                        "No referenced column is a "
                        "maskable RVec."
                    ),
                },
                parents=[
                    parent_dataframe,
                ],
            )

            filtered_dataframes.append(
                dataframe
            )

            continue

        # -----------------------------------------------------
        # Build the combined expression
        # -----------------------------------------------------

        combined_expression = " && ".join(
            f"({expression})"
            for expression in filters
        )

        # ROOT needs help for some string-column representations.
        combined_expression = (
            _rewrite_string_comparisons(
                combined_expression,
                column_types,
            )
        )

        # ROOT RVec<bool> unary ! handling needs rewriting.
        combined_expression = (
            _rewrite_bool_vector_negations(
                combined_expression,
                column_types,
            )
        )

        # -----------------------------------------------------
        # Unique temporary mask name
        # -----------------------------------------------------

        cut_id = next(
            _CUT_ID
        )

        mask_column = (
            f"__columncut_mask_{cut_id}"
        )

        # -----------------------------------------------------
        # Convert referenced RVec<bool> columns to temporary
        # RVec<int> columns before evaluating the expression.
        # -----------------------------------------------------

        bool_vector_index = 0

        for column_name in sorted(
            referenced_columns
        ):
            compact_type = _compact_cpp_type(
                column_types[column_name]
            )

            if compact_type not in (
                "ROOT::VecOps::RVec<bool>",
                "RVec<bool>",
            ):
                continue

            temporary_column = (
                f"__columncut_boolvec_"
                f"{cut_id}_"
                f"{bool_vector_index}"
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

        # -----------------------------------------------------
        # Compute the element-wise mask once
        # -----------------------------------------------------

        try:
            dataframe = dataframe.Define(
                mask_column,
                combined_expression,
            )

            # -------------------------------------------------
            # Apply the mask ONLY to referenced RVec columns
            # -------------------------------------------------

            for column_name in vector_columns_to_filter:
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

        except FilterError:
            raise

        except Exception as error:
            raise FilterError(
                "Could not compile or apply the column cut.\n"
                f"Dataset: {dataframe_index}\n"
                f"Expression: {combined_expression}\n"
                f"ROOT error: {error}"
            ) from error

        # -----------------------------------------------------
        # Register provenance
        # -----------------------------------------------------

        register_provenance(
            dataframe,
            kind="dataframe",
            operation="column filter",
            parameters={
                "cuts": list(
                    filters
                ),
                "referenced_columns": sorted(
                    referenced_columns
                ),
                "filtered_columns": sorted(
                    vector_columns_to_filter
                ),
                "nonmaskable_columns": (
                    scalar_or_nonmaskable_columns
                ),
                "filters_rows": False,
                "modifies_unrelated_columns": False,
                "applied": True,
            },
            parents=[
                parent_dataframe,
            ],
        )

        filtered_dataframes.append(
            dataframe
        )

    # ---------------------------------------------------------
    # Preserve input shape
    # ---------------------------------------------------------

    return (
        filtered_dataframes[0]
        if single_dataframe
        else filtered_dataframes
    )


def _normalize_filters(
    cut_filter: str | list[str] | None,
) -> list[str]:
    """
    Normalize one cut or a collection of cuts to a clean list.
    """

    if cut_filter is None:
        return []

    if isinstance(
        cut_filter,
        str,
    ):
        filters = [
            cut_filter
        ]

    elif isinstance(
        cut_filter,
        (list, tuple),
    ):
        filters = list(
            cut_filter
        )

    else:
        raise FilterError(
            "cut_filter must be a string, "
            "a list/tuple of strings, or None."
        )

    result: list[str] = []

    for index, expression in enumerate(
        filters,
        start=1,
    ):
        if not isinstance(
            expression,
            str,
        ):
            raise FilterError(
                f"Cut filter {index} must be a string."
            )

        expression = expression.strip()

        if expression:
            result.append(
                expression
            )

    return result


def _referenced_columns(
    expression: str,
    available_columns: set[str],
) -> set[str]:
    """
    Find dataframe columns referenced in an expression.

    String literals are removed first so strings such as:

        "Muon_Entrance"

    are never incorrectly interpreted as dataframe columns.
    """

    expression_without_strings = (
        _STRING_LITERAL_RE.sub(
            "",
            expression,
        )
    )

    identifiers = set(
        _IDENTIFIER_RE.findall(
            expression_without_strings
        )
    )

    return (
        identifiers
        & available_columns
    )


def _compact_cpp_type(
    column_type: str,
) -> str:
    """
    Remove whitespace from a ROOT/C++ type string.
    """

    return column_type.replace(
        " ",
        "",
    )


def _is_rvec_type(
    column_type: str,
) -> bool:
    """
    Return True if the ROOT column type is an RVec.
    """

    compact = _compact_cpp_type(
        column_type
    )

    return (
        "ROOT::VecOps::RVec<" in compact
        or compact.startswith(
            "RVec<"
        )
    )


def _is_char_array_type(
    column_type: str,
) -> bool:
    """
    Detect a character RVec representing one string.

    Examples:
        RVec<Char_t>
        RVec<char>

    These are intentionally NOT treated as element-wise
    filterable RVec columns.
    """

    compact = _compact_cpp_type(
        column_type
    )

    return (
        "RVec<Char_t>" in compact
        or "RVec<char>" in compact
        or "RVec<signedchar>" in compact
        or "RVec<unsignedchar>" in compact
    )


def _is_string_vector_type(
    column_type: str,
) -> bool:
    """
    Detect a genuine element-wise vector of strings.
    """

    compact = _compact_cpp_type(
        column_type
    )

    return (
        "RVec<std::string>" in compact
        or "RVec<string>" in compact
    )


def _is_maskable_rvec_type(
    column_type: str,
) -> bool:
    """
    Determine whether a column can be masked element-by-element.

    Included:
        RVec<int>
        RVec<float>
        RVec<double>
        RVec<bool>
        RVec<std::string>
        other genuine RVec types

    Excluded:
        RVec<char>
        RVec<Char_t>
        RVec<signed char>
        RVec<unsigned char>

    Character vectors are treated as scalar strings.
    """

    return (
        _is_rvec_type(
            column_type
        )
        and not _is_char_array_type(
            column_type
        )
    )


def _rewrite_string_comparisons(
    expression: str,
    column_types: dict[str, str],
) -> str:
    """
    Rewrite string comparisons where ROOT requires explicit helpers.

    RVec<char>/RVec<Char_t>:
        treated as one scalar string.

    RVec<std::string>:
        treated as an element-wise string vector.
    """

    rewritten = expression

    string_literal = (
        r'"(?:\\.|[^"\\])*"'
    )

    for column_name in sorted(
        column_types,
        key=len,
        reverse=True,
    ):
        column_type = (
            column_types[column_name]
        )

        column_pattern = (
            r"(?<![A-Za-z0-9_])"
            + re.escape(
                column_name
            )
            + r"(?![A-Za-z0-9_])"
        )

        # -----------------------------------------------------
        # Character array treated as one scalar string
        # -----------------------------------------------------

        if _is_char_array_type(
            column_type
        ):
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

        # -----------------------------------------------------
        # Genuine vector of strings
        # -----------------------------------------------------

        elif _is_string_vector_type(
            column_type
        ):
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
    """
    Escape text for insertion into a C++ string literal.
    """

    return (
        value
        .replace(
            "\\",
            "\\\\",
        )
        .replace(
            '"',
            '\\"',
        )
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

    This avoids problematic unary-negation behaviour for
    RVec<bool> in ROOT expressions.
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
            "ROOT::VecOps::RVec<bool>"
            in compact_type
            or compact_type
            == "RVec<bool>"
        )

        if not is_bool_vector:
            continue

        column_pattern = (
            r"(?<![A-Za-z0-9_])"
            + re.escape(
                column_name
            )
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
    """
    Replace an identifier while leaving string literals untouched.
    """

    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(
            identifier
        )
        + r"(?![A-Za-z0-9_])"
    )

    pieces = []
    last_end = 0

    for match in _STRING_LITERAL_RE.finditer(
        expression
    ):
        pieces.append(
            pattern.sub(
                replacement,
                expression[
                    last_end:match.start()
                ],
            )
        )

        # Keep the string literal untouched.
        pieces.append(
            match.group(0)
        )

        last_end = (
            match.end()
        )

    pieces.append(
        pattern.sub(
            replacement,
            expression[last_end:],
        )
    )

    return "".join(
        pieces
    )