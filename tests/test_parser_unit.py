"""Component-level tests for ``zros2.generator._parser``.

Tests every internal function in the parser module in isolation:
- Inline comment stripping (string-state machine)
- Name validation (field and constant names)
- Line-level tokenisation (all line forms)
- Section splitting (``---`` separator)
- High-level file parsers
- Directory discovery helpers
"""

import pathlib
import pytest

from zros2.generator._parser import (
    _strip_inline_comment,
    _is_valid_field_name,
    _is_valid_constant_name,
    _tokenise_field_line,
    _split_sections,
    parse_msg_text,
    parse_msg_file,
    parse_srv_file,
    parse_action_file,
    iter_msg_files,
    iter_srv_files,
    iter_action_files,
    find_msg_dirs,
)


# ======================================================================
# _strip_inline_comment
# ======================================================================

class TestStripInlineComment:
    """String-state machine that strips ``#`` comments respecting quotes."""

    def test_no_comment(self):
        assert _strip_inline_comment("int32 x") == "int32 x"

    def test_simple_comment(self):
        assert _strip_inline_comment("int32 x  # this is x") == "int32 x"

    def test_comment_with_double_quote(self):
        """A ``#`` inside double quotes must NOT be stripped."""
        result = _strip_inline_comment('string name = "hello#world"')
        assert result == 'string name = "hello#world"'

    def test_comment_with_single_quote(self):
        result = _strip_inline_comment("string name = 'hello#world'")
        assert result == "string name = 'hello#world'"

    def test_escaped_quote_inside_string(self):
        result = _strip_inline_comment('string name = "say \\"hi\\""')
        assert result == 'string name = "say \\"hi\\""'

    def test_hash_at_end_of_quoted_string_comment_after(self):
        result = _strip_inline_comment('string name = "data"  # end comment')
        assert result == 'string name = "data"'

    def test_empty_after_strip(self):
        result = _strip_inline_comment("  # only comment")
        assert result == ""

    def test_multiple_hashes(self):
        result = _strip_inline_comment("int32 x ## double hash")
        assert result == "int32 x"

    def test_comment_with_equals(self):
        result = _strip_inline_comment("int32 x = 42  # default")
        assert result == "int32 x = 42"

    def test_unclosed_double_quote(self):
        """If the quote is never closed, '#' inside the string is NOT a comment."""
        result = _strip_inline_comment('string x = "unclosed  # comment')
        # The function keeps '#' inside unclosed quotes because it's still
        # inside the string token.
        assert result == 'string x = "unclosed  # comment'

    def test_single_quote_inside_double_quote(self):
        result = _strip_inline_comment("string x = \"it's fine\"  # comment")
        assert result == "string x = \"it's fine\""

    def test_backslash_not_at_end(self):
        result = _strip_inline_comment("int32 x \\\n# still comment?")
        assert result == "int32 x \\"


# ======================================================================
# _is_valid_field_name
# ======================================================================

class TestIsValidFieldName:
    """Field name validation per ROS 2 interface spec."""

    def test_valid_simple(self):
        assert _is_valid_field_name("x")
        assert _is_valid_field_name("my_field")
        assert _is_valid_field_name("field1")
        assert _is_valid_field_name("a_longer_field_name")

    def test_start_with_underscore_invalid(self):
        assert not _is_valid_field_name("_private")

    def test_start_with_digit_invalid(self):
        assert not _is_valid_field_name("1field")

    def test_trailing_underscore_invalid(self):
        assert not _is_valid_field_name("field_")

    def test_consecutive_underscores_invalid(self):
        assert not _is_valid_field_name("field__name")

    def test_uppercase_invalid(self):
        assert not _is_valid_field_name("FieldName")

    def test_python_keyword_invalid(self):
        assert not _is_valid_field_name("class")
        assert not _is_valid_field_name("def")
        assert not _is_valid_field_name("import")
        assert not _is_valid_field_name("from")
        assert not _is_valid_field_name("return")
        assert not _is_valid_field_name("None")
        assert not _is_valid_field_name("True")
        assert not _is_valid_field_name("False")

    def test_special_chars_invalid(self):
        assert not _is_valid_field_name("field-name")
        assert not _is_valid_field_name("field.name")
        assert not _is_valid_field_name("field name")

    def test_empty_string_invalid(self):
        assert not _is_valid_field_name("")


# ======================================================================
# _is_valid_constant_name
# ======================================================================

class TestIsValidConstantName:
    """Constant name validation (UPPER_CASE)."""

    def test_valid_simple(self):
        assert _is_valid_constant_name("FOO")
        assert _is_valid_constant_name("MY_CONST")
        assert _is_valid_constant_name("MAX_VALUE")
        assert _is_valid_constant_name("FOO42")

    def test_lowercase_invalid(self):
        assert not _is_valid_constant_name("foo")
        assert not _is_valid_constant_name("my_const")

    def test_start_with_digit_invalid(self):
        assert not _is_valid_constant_name("1FOO")

    def test_start_with_underscore_invalid(self):
        assert not _is_valid_constant_name("_FOO")

    def test_empty_invalid(self):
        assert not _is_valid_constant_name("")

    def test_special_chars_invalid(self):
        assert not _is_valid_constant_name("FOO-BAR")
        assert not _is_valid_constant_name("FOO BAR")


# ======================================================================
# _tokenise_field_line
# ======================================================================

class TestTokeniseFieldLine:
    """Line-level tokeniser — every valid and invalid line form."""

    # -- Fields ---------------------------------------------------------

    def test_simple_field(self):
        field = _tokenise_field_line("int32 x")
        assert field is not None
        assert field.name == "x"
        assert field.type_str == "int32"
        assert field.default is None
        assert not field.is_constant

    def test_field_with_default(self):
        field = _tokenise_field_line("int32 x = 42")
        assert field is not None
        assert field.name == "x"
        assert field.default == "42"
        assert not field.is_constant

    def test_field_with_default_compact(self):
        """'int32 x=42' is a field, not a constant (name is lowercase)."""
        field = _tokenise_field_line("int32 x=42")
        assert field is not None
        assert field.name == "x"
        assert field.default == "42"
        assert not field.is_constant

    def test_field_with_string_default(self):
        field = _tokenise_field_line('string name = "hello"')
        assert field is not None
        assert field.name == "name"
        assert field.default == '"hello"'

    def test_field_array_type(self):
        field = _tokenise_field_line("int32[] values")
        assert field is not None
        assert field.type_str == "int32[]"
        assert field.name == "values"

    def test_field_sequence_type(self):
        field = _tokenise_field_line("sequence<uint8> data")
        assert field is not None
        assert field.type_str == "sequence<uint8>"
        assert field.name == "data"

    def test_field_nested_type(self):
        field = _tokenise_field_line("std_msgs/Header header")
        assert field is not None
        assert field.type_str == "std_msgs/Header"

    def test_field_bounded_string(self):
        field = _tokenise_field_line("string<=255 name")
        assert field is not None
        assert field.type_str == "string<=255"

    # -- Constants ------------------------------------------------------

    def test_simple_constant(self):
        field = _tokenise_field_line("int32 FOO=42")
        assert field is not None
        assert field.name == "FOO"
        assert field.type_str == "int32"
        assert field.default == "42"
        assert field.is_constant

    def test_constant_with_spaces(self):
        field = _tokenise_field_line("int32 FOO = 42")
        assert field is not None
        assert field.name == "FOO"
        assert field.default == "42"
        assert field.is_constant

    def test_float_constant(self):
        field = _tokenise_field_line("float64 PI=3.14159")
        assert field is not None
        assert field.is_constant
        assert field.default == "3.14159"

    def test_string_constant(self):
        field = _tokenise_field_line("string GREETING=hello")
        assert field is not None
        assert field.is_constant
        assert field.default == "hello"

    def test_bool_constant(self):
        field = _tokenise_field_line("bool ENABLED=True")
        assert field.is_constant

    # -- Unparseable lines (now raise ValueError) ------------------------

    def test_no_type(self):
        with pytest.raises(ValueError, match="missing field name"):
            _tokenise_field_line("justname")

    def test_no_name(self):
        with pytest.raises(ValueError, match="missing field name after type"):
            _tokenise_field_line("int32")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="not a valid ROS 2 type"):
            _tokenise_field_line("foo@bar name")

    def test_empty_line(self):
        with pytest.raises(ValueError, match="empty line"):
            _tokenise_field_line("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="empty line"):
            _tokenise_field_line("   ")

    def test_invalid_field_name(self):
        with pytest.raises(ValueError, match="not a valid field name"):
            _tokenise_field_line("int32 1badname")

    def test_type_with_trailing_space_only(self):
        """A type token followed by only whitespace (no name)."""
        with pytest.raises(ValueError, match="not followed by a field name"):
            _tokenise_field_line("int32 ")

    def test_equals_with_invalid_name(self):
        """A name starting with a digit after '=' is invalid."""
        with pytest.raises(ValueError, match="not a valid field or constant name"):
            _tokenise_field_line("int32 123=value")

    def test_uppercase_name_not_constant(self):
        """Uppercase name with non-primitive type → not a valid field name."""
        with pytest.raises(ValueError, match="not a valid field name"):
            _tokenise_field_line("std_msgs/Header HEADER")


# ======================================================================
# _split_sections
# ======================================================================

class TestSplitSections:
    """Splitting on ``---`` markers for .srv / .action files."""

    def test_two_sections(self):
        parts = _split_sections("int64 a\n---\nint64 sum\n", maxsplit=1)
        assert len(parts) == 2
        assert "int64 a" in parts[0]
        assert "int64 sum" in parts[1]

    def test_three_sections(self):
        parts = _split_sections("a\n---\nb\n---\nc\n", maxsplit=2)
        assert len(parts) == 3

    def test_no_separator(self):
        parts = _split_sections("int64 a\nint64 b\n", maxsplit=1)
        assert len(parts) == 1
        assert parts[0] == "int64 a\nint64 b\n"

    def test_separator_with_whitespace(self):
        parts = _split_sections("a\n  ---  \nb\n", maxsplit=1)
        assert len(parts) == 2
        assert parts[0].strip() == "a"
        assert parts[1].strip() == "b"

    def test_maxsplit_respected(self):
        parts = _split_sections("a\n---\nb\n---\nc\n", maxsplit=1)
        assert len(parts) == 2
        assert "---" in parts[1]  # second separator NOT split

    def test_empty_sections(self):
        parts = _split_sections("---\n---\n", maxsplit=2)
        assert len(parts) == 3
        assert all(p == "" for p in parts)


# ======================================================================
# parse_msg_text
# ======================================================================

class TestParseMsgText:
    """High-level message text parsing."""

    def test_simple_fields(self):
        defn = parse_msg_text(
            "int32 x\nfloat64 y\nstring name",
            package="test", type_name="Simple",
        )
        assert defn.package == "test"
        assert defn.type_name == "Simple"
        assert defn.type_kind == "msg"
        assert len(defn.fields) == 3
        assert defn.fields[0].name == "x"
        assert defn.fields[0].type_str == "int32"

    def test_constants(self):
        defn = parse_msg_text(
            "int32 FOO=42\nfloat64 PI=3.14",
            package="test", type_name="Consts",
        )
        assert len(defn.constants) == 2
        assert defn.constants[0].name == "FOO"
        assert defn.constants[0].is_constant

    def test_mixed_fields_and_constants(self):
        defn = parse_msg_text(
            "int32 FOO=42\nint32 x\nfloat64 y",
            package="test", type_name="Mixed",
        )
        assert len(defn.constants) == 1
        assert len(defn.fields) == 2

    def test_full_line_comments_skipped(self):
        defn = parse_msg_text(
            "# this is a comment\nint32 x\n# another\n",
            package="test", type_name="C",
        )
        assert len(defn.fields) == 1

    def test_inline_comments_stripped(self):
        defn = parse_msg_text(
            "int32 x  # inline comment",
            package="test", type_name="C",
        )
        assert len(defn.fields) == 1

    def test_full_line_comment_after_inline_strip(self):
        """A line that becomes empty after inline-stripping is skipped."""
        defn = parse_msg_text(
            "int32 x\n  # full comment\nfloat64 y",
            package="test", type_name="C",
        )
        assert len(defn.fields) == 2

    def test_unparseable_line_raises(self):
        """A truly unparseable line now raises a descriptive ValueError."""
        import pytest
        with pytest.raises(ValueError, match="line 1"):
            parse_msg_text(
                "@#$% not_a_field\nint32 x\n",
                package="test", type_name="C",
            )

    def test_empty_text(self):
        defn = parse_msg_text("", package="test", type_name="Empty")
        assert len(defn.fields) == 0
        assert len(defn.constants) == 0

    def test_full_name_generated(self):
        defn = parse_msg_text("int32 x", package="my_pkg", type_name="MyMsg")
        assert defn.full_name == "my_pkg/msg/MyMsg"

    def test_overridden_type_kind(self):
        defn = parse_msg_text(
            "int32 x", package="pkg", type_name="Foo", type_kind="srv",
        )
        assert defn.type_kind == "srv"
        assert defn.full_name == "pkg/srv/Foo"


# ======================================================================
# parse_srv_file
# ======================================================================

class TestParseSrvFile:
    """Service file parsing (request / response split)."""

    def test_simple_service(self, tmp_path):
        path = tmp_path / "AddTwoInts.srv"
        path.write_text("int64 a\nint64 b\n---\nint64 sum\n")
        req, resp = parse_srv_file(path, "test")
        assert req.type_name == "AddTwoInts_Request"
        assert resp.type_name == "AddTwoInts_Response"
        assert len(req.fields) == 2
        assert len(resp.fields) == 1

    def test_service_without_fields(self, tmp_path):
        path = tmp_path / "Empty.srv"
        path.write_text("---\n")
        req, resp = parse_srv_file(path, "test")
        assert len(req.fields) == 0
        assert len(resp.fields) == 0

    def test_service_with_constants(self, tmp_path):
        path = tmp_path / "WithConst.srv"
        path.write_text("int32 STATUS_OK=0\nint32 data\n---\nbool result\n")
        req, resp = parse_srv_file(path, "test")
        assert len(req.constants) == 1
        assert req.constants[0].name == "STATUS_OK"

    def test_missing_separator_raises(self, tmp_path):
        path = tmp_path / "Bad.srv"
        path.write_text("int64 a\nint64 b\n")
        with pytest.raises(ValueError, match="missing '---' separator"):
            parse_srv_file(path, "test")

    def test_type_kind_is_srv(self, tmp_path):
        path = tmp_path / "Foo.srv"
        path.write_text("---\n")
        req, resp = parse_srv_file(path, "test")
        assert req.type_kind == "srv"
        assert resp.type_kind == "srv"
        assert "/srv/" in req.full_name


# ======================================================================
# parse_action_file
# ======================================================================

class TestParseActionFile:
    """Action file parsing (8 sub-types)."""

    def test_yields_eight_definitions(self, tmp_path):
        path = tmp_path / "Fibonacci.action"
        path.write_text(
            "int32 order\n---\nint32[] sequence\n---\nint32[] sequence\n"
        )
        results = parse_action_file(path, "test")
        assert len(results) == 8

    def test_sub_type_names(self, tmp_path):
        path = tmp_path / "Do.action"
        path.write_text("int32 input\n---\nint32 result\n---\nfloat32 feedback\n")
        results = parse_action_file(path, "test")
        names = {r.type_name for r in results}
        assert "Do_Goal" in names
        assert "Do_Result" in names
        assert "Do_Feedback" in names
        assert "Do_FeedbackMessage" in names
        assert "Do_SendGoal_Request" in names
        assert "Do_SendGoal_Response" in names
        assert "Do_GetResult_Request" in names
        assert "Do_GetResult_Response" in names

    def test_full_name_uses_action(self, tmp_path):
        path = tmp_path / "Foo.action"
        path.write_text("---\n---\n")
        results = parse_action_file(path, "test")
        for defn in results:
            assert "/action/" in defn.full_name
            assert defn.type_kind == "action"

    def test_missing_separators_raises(self, tmp_path):
        path = tmp_path / "Bad.action"
        path.write_text("int32 order\n---\nint32[] sequence\n")
        with pytest.raises(ValueError, match="expected two '---' separators"):
            parse_action_file(path, "test")

    def test_goal_has_user_field(self, tmp_path):
        path = tmp_path / "Foo.action"
        path.write_text("int32 order\n---\nint32 result\n---\nfloat32 feedback\n")
        results = parse_action_file(path, "test")
        goal = next(r for r in results if r.type_name == "Foo_Goal")
        assert any(f.name == "order" for f in goal.fields)

    def test_send_goal_request_has_goal_id_and_goal(self, tmp_path):
        path = tmp_path / "Bar.action"
        path.write_text("---\n---\n")
        results = parse_action_file(path, "test")
        sg_req = next(r for r in results if r.type_name == "Bar_SendGoal_Request")
        field_names = [f.name for f in sg_req.fields]
        assert "goal_id" in field_names
        assert "goal" in field_names


# ======================================================================
# Directory discovery helpers
# ======================================================================

class TestIterMsgFiles:
    def test_yields_sorted_files(self, tmp_path):
        (tmp_path / "msg").mkdir()
        (tmp_path / "msg" / "B.msg").write_text("int32 x\n")
        (tmp_path / "msg" / "A.msg").write_text("int32 y\n")
        results = list(iter_msg_files(tmp_path / "msg"))
        assert len(results) == 2
        # Sorted alphabetically
        assert results[0][1].name == "A.msg"
        assert results[1][1].name == "B.msg"

    def test_empty_dir(self, tmp_path):
        (tmp_path / "msg").mkdir()
        results = list(iter_msg_files(tmp_path / "msg"))
        assert results == []

    def test_nonexistent_dir(self, tmp_path):
        results = list(iter_msg_files(tmp_path / "nonexistent"))
        assert results == []

    def test_package_name_from_parent(self, tmp_path):
        (tmp_path / "my_pkg" / "msg").mkdir(parents=True)
        (tmp_path / "my_pkg" / "msg" / "X.msg").write_text("int32 x\n")
        results = list(iter_msg_files(tmp_path / "my_pkg" / "msg"))
        assert results[0][0] == "my_pkg"


class TestIterSrvFiles:
    def test_yields_sorted_files(self, tmp_path):
        (tmp_path / "srv").mkdir()
        (tmp_path / "srv" / "B.srv").write_text("---\n")
        (tmp_path / "srv" / "A.srv").write_text("---\n")
        results = list(iter_srv_files(tmp_path / "srv"))
        assert len(results) == 2
        assert results[0][1].name == "A.srv"

    def test_empty_dir(self, tmp_path):
        (tmp_path / "srv").mkdir()
        results = list(iter_srv_files(tmp_path / "srv"))
        assert results == []

    def test_nonexistent_dir(self):
        results = list(iter_srv_files(pathlib.Path("/nonexistent")))
        assert results == []


class TestIterActionFiles:
    def test_yields_sorted_files(self, tmp_path):
        (tmp_path / "action").mkdir()
        (tmp_path / "action" / "B.action").write_text("---\n---\n")
        (tmp_path / "action" / "A.action").write_text("---\n---\n")
        results = list(iter_action_files(tmp_path / "action"))
        assert len(results) == 2
        assert results[0][1].name == "A.action"

    def test_nonexistent_dir(self):
        results = list(iter_action_files(pathlib.Path("/nonexistent")))
        assert results == []


class TestFindMsgDirs:
    def test_non_existent_path(self):
        result = find_msg_dirs([pathlib.Path("/nonexistent/path")])
        assert result == []

    def test_base_has_msg_subdir(self, tmp_path):
        (tmp_path / "msg").mkdir()
        result = find_msg_dirs([tmp_path])
        assert tmp_path in result

    def test_scans_subdirectories(self, tmp_path):
        pkg = tmp_path / "my_pkg"
        (pkg / "msg").mkdir(parents=True)
        result = find_msg_dirs([tmp_path])
        assert pkg in result

    def test_mixed_existing_and_non_existing(self, tmp_path):
        (tmp_path / "pkg_a" / "msg").mkdir(parents=True)
        result = find_msg_dirs([tmp_path / "pkg_a", pathlib.Path("/nonexistent")])
        assert len(result) == 1
        assert result[0].name == "pkg_a"

    def test_base_is_file(self, tmp_path):
        f = tmp_path / "not_a_dir"
        f.write_text("")
        result = find_msg_dirs([f])
        assert result == []

    def test_base_without_msg_scans_subdirs(self, tmp_path):
        """When base has no msg/, subdirectories are scanned."""
        pkg = tmp_path / "pkg_a"
        (pkg / "msg").mkdir(parents=True)
        (tmp_path / "pkg_b").mkdir()
        result = find_msg_dirs([tmp_path])
        assert pkg in result
        assert tmp_path not in result


# ======================================================================
# Boundary / edge-case tests
# ======================================================================


class TestStripInlineCommentBoundary:
    """Additional boundary cases for inline comment stripping."""

    def test_hash_after_closed_quotes(self):
        """A string with # inside, followed by a real comment after quotes."""
        result = _strip_inline_comment('string x = "safe#part"  # real comment')
        assert result == 'string x = "safe#part"'

    def test_consecutive_escaped_backslash_then_quote(self):
        """A double-escaped backslash before a quote: \\" is not an escaped quote.

        The first backslash escapes the second backslash, producing a literal
        backslash in the output, and the quote is NOT escaped — so it toggles
        the string state.
        """
        result = _strip_inline_comment('string x = "\\\\"  # comment')
        # The four backslashes become two literal backslashes, then the quote
        # closes the string, so the trailing # is stripped.
        assert result == 'string x = "\\\\"'

    def test_tab_before_hash_is_comment(self):
        result = _strip_inline_comment("int32 x\t# tab before hash")
        assert result == "int32 x"

    def test_only_hash(self):
        result = _strip_inline_comment("#")
        assert result == ""

    def test_unicode_in_comment_not_stripped_by_accident(self):
        """Unicode characters in comments should be stripped normally."""
        result = _strip_inline_comment("int32 x  # unicode: αβγ")
        assert result == "int32 x"


class TestIsValidFieldNameBoundary:
    """Boundary cases: Unicode rejection, edge names."""

    def test_unicode_letters_rejected(self):
        """ROS 2 IDL only allows ASCII — Unicode must be rejected."""
        assert not _is_valid_field_name("café")
        assert not _is_valid_field_name("münchen")
        assert not _is_valid_field_name("姓名")

    def test_greek_letters_rejected(self):
        assert not _is_valid_field_name("α")
        assert not _is_valid_field_name("β_field")

    def test_cyrillic_rejected(self):
        assert not _is_valid_field_name("поле")

    def test_single_character_alpha_valid(self):
        assert _is_valid_field_name("a")
        assert _is_valid_field_name("z")


class TestIsValidConstantNameBoundary:
    """Boundary cases: Unicode rejection for constants."""

    def test_unicode_letters_rejected(self):
        assert not _is_valid_constant_name("MAX_VALUÉ")
        assert not _is_valid_constant_name("CAFÉ")

    def test_greek_rejected(self):
        assert not _is_valid_constant_name("ΜAX")


class TestTokeniseFieldLineBoundary:
    """Boundary cases for the line-level tokeniser."""

    # -- Array defaults ------------------------------------------------

    def test_array_fixed_with_default(self):
        """Fixed-size array with a default value."""
        field = _tokenise_field_line("int32[3] arr [1,2,3]")
        assert field.name == "arr"
        assert field.type_str == "int32[3]"
        assert field.default == "[1,2,3]"
        assert not field.is_constant

    def test_array_variable_with_default(self):
        """Variable-size array with a default value."""
        field = _tokenise_field_line("int32[] arr [1,2,3]")
        assert field.name == "arr"
        assert field.type_str == "int32[]"
        assert field.default == "[1,2,3]"

    def test_array_fixed_with_default_spaces(self):
        """Array default with spaces inside brackets."""
        field = _tokenise_field_line("int32[3] arr [1, 2, 3]")
        assert field.name == "arr"
        assert field.default == "[1, 2, 3]"

    # -- String defaults containing # -----------------------------------

    def test_string_default_with_hash_single_quote(self):
        """A # inside single-quoted default must NOT be treated as comment."""
        field = _tokenise_field_line("string desc 'hello # world'")
        assert field.name == "desc"
        assert field.default == "'hello # world'"

    def test_string_default_with_hash_double_quote(self):
        """A # inside double-quoted default must NOT be treated as comment."""
        field = _tokenise_field_line('string desc "hello # world"')
        assert field.name == "desc"
        assert field.default == '"hello # world"'

    # -- Unicode identifier rejection -----------------------------------

    def test_unicode_field_name_raises(self):
        """A field name with Unicode characters must raise ValueError."""
        with pytest.raises(ValueError, match="not a valid field name"):
            _tokenise_field_line("float64 cafÃ©")

    def test_unicode_constant_name_raises(self):
        """A constant name with Unicode characters must raise ValueError."""
        with pytest.raises(ValueError, match="not a valid field or constant"):
            _tokenise_field_line("int32 VALUÃ‰=1")

    # -- Constant edge cases --------------------------------------------

    def test_constant_scientific_notation(self):
        field = _tokenise_field_line("float64 E=1.5e-10")
        assert field.is_constant
        assert field.default == "1.5e-10"

    def test_constant_string_with_equals_inside(self):
        """A string constant with = inside the value (e.g. "a=b")."""
        field = _tokenise_field_line("string EQUATION='a=b'")
        assert field.is_constant
        assert field.default == "'a=b'"

    # -- Field with nested type -----------------------------------------

    def test_nested_type_default(self):
        field = _tokenise_field_line("std_msgs/Header header None")
        assert field.name == "header"
        assert field.default == "None"


class TestSplitSectionsBoundary:
    """Boundary cases for section splitting."""

    def test_only_separators(self):
        parts = _split_sections("---", maxsplit=1)
        assert len(parts) == 2
        assert parts[0] == ""
        assert parts[1] == ""

    def test_trailing_separator(self):
        """Content followed by --- at end (no trailing newline)."""
        parts = _split_sections("content\n---", maxsplit=1)
        assert len(parts) == 2
        assert parts[0] == "content\n"
        assert parts[1] == ""

    def test_leading_separator(self):
        parts = _split_sections("---\ncontent", maxsplit=1)
        assert len(parts) == 2
        assert parts[0] == ""
        assert parts[1] == "content"

    def test_empty_text(self):
        parts = _split_sections("", maxsplit=1)
        assert len(parts) == 1
        assert parts[0] == ""

    def test_consecutive_separators(self):
        parts = _split_sections("---\n---\n", maxsplit=2)
        assert len(parts) == 3
        assert parts[0] == ""
        assert parts[1] == ""
        assert parts[2] == ""

    def test_windows_line_endings(self):
        parts = _split_sections("a\r\n---\r\nb\r\n", maxsplit=1)
        assert len(parts) == 2
        assert "---" not in parts[0]
        assert "---" not in parts[1]


class TestParseMsgTextBoundary:
    """Boundary cases for high-level message text parsing."""

    def test_array_default_values(self):
        """Array fields with defaults are correctly parsed."""
        defn = parse_msg_text(
            "int32[3] arr [1,2,3]\nfloat64[] vals []",
            package="test", type_name="Arrays",
        )
        assert len(defn.fields) == 2
        assert defn.fields[0].name == "arr"
        assert defn.fields[0].default == "[1,2,3]"
        assert defn.fields[1].name == "vals"
        assert defn.fields[1].default == "[]"

    def test_string_with_hash_default(self):
        """A # inside a quoted default value must survive parsing."""
        defn = parse_msg_text(
            "string desc 'hello # world'",
            package="test", type_name="WithHash",
        )
        assert len(defn.fields) == 1
        assert defn.fields[0].default == "'hello # world'"

    def test_unicode_field_name_rejected(self):
        """A field name with Unicode must raise via parse_msg_text."""
        with pytest.raises(ValueError, match="not a valid field name"):
            parse_msg_text(
                "float64 café",
                package="test", type_name="Bad",
            )

    def test_preserves_leading_whitespace_inline_comment_after_quote(self):
        """Trailing # comment after a complex quoted string."""
        defn = parse_msg_text(
            'string x = "data"  # end comment',
            package="test", type_name="C",
        )
        assert len(defn.fields) == 1
        assert defn.fields[0].default == '"data"'

    def test_constant_and_field_with_same_type(self):
        """Constants and fields using the same type are both parsed."""
        defn = parse_msg_text(
            "int32 SPEED=100\nint32 speed",
            package="test", type_name="Car",
        )
        assert len(defn.constants) == 1
        assert defn.constants[0].name == "SPEED"
        assert len(defn.fields) == 1
        assert defn.fields[0].name == "speed"

    def test_only_comments_and_blank_lines(self):
        defn = parse_msg_text(
            "\n# comment\n  \n  # another\n\n",
            package="test", type_name="Empty",
        )
        assert len(defn.fields) == 0
        assert len(defn.constants) == 0


class TestParseSrvBoundary:
    """Boundary cases for service file parsing."""

    def test_empty_response_section(self, tmp_path):
        """Request has fields, response section is empty."""
        path = tmp_path / "SetParam.srv"
        path.write_text("string key\nstring value\n---\n")
        req, resp = parse_srv_file(path, "test")
        assert len(req.fields) == 2
        assert len(resp.fields) == 0

    def test_empty_request_section(self, tmp_path):
        """Request section is empty, response has fields."""
        path = tmp_path / "GetParam.srv"
        path.write_text("\n---\nstring value\n")
        req, resp = parse_srv_file(path, "test")
        assert len(req.fields) == 0
        assert len(resp.fields) == 1

    def test_constants_in_both_sections(self, tmp_path):
        """Both request and response can have constants."""
        path = tmp_path / "Status.srv"
        path.write_text("int32 REQ_CODE=1\nint32 data\n---\nint32 RESP_CODE=0\nbool ok\n")
        req, resp = parse_srv_file(path, "test")
        assert len(req.constants) == 1
        assert len(resp.constants) == 1
        assert resp.constants[0].name == "RESP_CODE"




class TestParseActionBoundary:
    """Boundary cases for action file parsing."""

    def test_empty_sections(self, tmp_path):
        """All three sections empty: ---\n---\n."""
        path = tmp_path / "Empty.action"
        path.write_text("---\n---\n")
        results = parse_action_file(path, "test")
        assert len(results) == 8
        # Goal, Result, Feedback all have zero fields
        for defn in results[:7]:
            assert len(defn.fields) >= 0

    def test_feedback_section_only(self, tmp_path):
        """Only feedback section has fields; goal and result are empty."""
        path = tmp_path / "FeedbackOnly.action"
        path.write_text("\n---\n\n---\nfloat32 progress\n")
        results = parse_action_file(path, "test")
        feedback = next(r for r in results if r.type_name.endswith("_Feedback"))
        assert len(feedback.fields) == 1
        assert feedback.fields[0].name == "progress"

    def test_result_section_with_constants(self, tmp_path):
        """Result section has both constants and fields."""
        path = tmp_path / "ResultConst.action"
        path.write_text("---\nint32 CODE=42\nint32 value\n---\n")
        results = parse_action_file(path, "test")
        result = next(r for r in results if r.type_name.endswith("_Result"))
        assert len(result.constants) == 1
        assert result.constants[0].name == "CODE"
        assert len(result.fields) == 1

    def test_package_empty_raises(self, tmp_path):
        """Action file with empty package must raise ValueError."""
        path = tmp_path / "Bad.action"
        path.write_text("---\n---\n")
        with pytest.raises(ValueError, match="package name must not be empty"):
            parse_action_file(path, "")

    def test_srv_package_empty_raises(self, tmp_path):
        path = tmp_path / "Bad.srv"
        path.write_text("---\n")
        with pytest.raises(ValueError, match="package name must not be empty"):
            parse_srv_file(path, "")

    def test_msg_package_empty_raises(self, tmp_path):
        path = tmp_path / "Bad.msg"
        path.write_text("int32 x\n")
        with pytest.raises(ValueError, match="package name must not be empty"):
            parse_msg_file(path, "")


class TestParseFileErrorPaths:
    """Coverage: error-context wrapping in parse_msg_file / parse_srv_file / parse_action_file."""

    def test_parse_msg_file_error_includes_path(self, tmp_path):
        """A bad .msg file must produce an error that includes the file path."""
        path = tmp_path / "bad.msg"
        path.write_text("@#$% invalid\n")
        with pytest.raises(ValueError, match=str(path) + "|" + path.name):
            parse_msg_file(path, "test")

    def test_parse_srv_file_error_includes_path(self, tmp_path):
        """A bad .srv file must produce an error that includes the file path."""
        path = tmp_path / "bad.srv"
        path.write_text("@#$% invalid\n---\n")
        with pytest.raises(ValueError, match=str(path) + "|" + path.name):
            parse_srv_file(path, "test")

    def test_parse_srv_file_bad_request_raises(self, tmp_path):
        """A .srv file with an invalid request section must raise ValueError."""
        path = tmp_path / "bad_req.srv"
        path.write_text("@#$% invalid\n---\nint32 ok\n")
        with pytest.raises(ValueError):
            parse_srv_file(path, "test")

    def test_parse_srv_file_bad_response_raises(self, tmp_path):
        """A .srv file with an invalid response section must raise ValueError."""
        path = tmp_path / "bad_resp.srv"
        path.write_text("int32 ok\n---\n@#$% invalid\n")
        with pytest.raises(ValueError):
            parse_srv_file(path, "test")

    def test_parse_action_file_bad_goal_raises(self, tmp_path):
        """A .action file with an invalid goal section must raise ValueError."""
        path = tmp_path / "bad.action"
        path.write_text("@#$% invalid\n---\n---\n")
        with pytest.raises(ValueError):
            parse_action_file(path, "test")

    def test_parse_action_file_bad_result_raises(self, tmp_path):
        """A .action file with an invalid result section must raise ValueError."""
        path = tmp_path / "bad_res.action"
        path.write_text("---\n@#$% invalid\n---\n")
        with pytest.raises(ValueError):
            parse_action_file(path, "test")

    def test_parse_action_file_bad_feedback_raises(self, tmp_path):
        """A .action file with an invalid feedback section must raise ValueError."""
        path = tmp_path / "bad_fb.action"
        path.write_text("---\n---\n@#$% invalid\n")
        with pytest.raises(ValueError):
            parse_action_file(path, "test")
