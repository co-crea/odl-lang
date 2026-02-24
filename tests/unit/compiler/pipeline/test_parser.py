import pytest

from odl.types import NodeField
from odl.compiler.pipeline import parser
from odl.compiler.exceptions import OdlCompilationError

class TestParser:
    """
    BP-L1-02-ODL-PARSER: Pipeline Parser
    YAMLパースと基本構造チェックを検証する。
    """

    def test_tc_parser_001_valid_yaml_parsing(self):
        """TC-PARSER-001: 正常なYAMLが辞書として返却されること"""
        # Pattern A: Explicit OpCode
        source = "opcode: serial\nchildren: []"
        result = parser.parse(source)
        assert isinstance(result, dict)
        assert result[NodeField.OPCODE] == "serial"

        # Pattern B: Root Key as OpCode
        source_sugar = "worker:\n  params: {a: 1}"
        result_sugar = parser.parse(source_sugar)
        assert result_sugar[NodeField.OPCODE] == "worker"
        assert result_sugar[NodeField.PARAMS]["a"] == 1

    def test_tc_parser_002_invalid_yaml_syntax(self):
        """TC-PARSER-002: YAML構文エラーがOdlCompilationErrorにラップされること"""
        invalid_yaml = "opcode: serial\n  indent_error: value"
        with pytest.raises(OdlCompilationError) as exc:
            parser.parse(invalid_yaml)
        assert "YAML syntax error" in str(exc.value)

    def test_tc_parser_003_invalid_root_structure(self):
        """TC-PARSER-003: ルートが辞書でない場合エラーになること"""
        # List Root (Valid YAML but Invalid ODL Root)
        with pytest.raises(OdlCompilationError, match="Root must be a dictionary"):
            parser.parse("- item1")

        # Empty
        with pytest.raises(OdlCompilationError, match="Empty ODL source"):
            parser.parse("")

    def test_tc_parser_004_missing_identity(self):
        """TC-PARSER-004: OpCodeが特定できない構造（複数キーかつopcodeなし）を弾くこと"""
        # 単一キーの場合は "Root Key Syntax" として解釈されるためエラーにならない。
        # したがって、曖昧さを生むために「2つ以上のキー」を持たせる。
        ambiguous_source = """
        params: {key: value}
        wiring: {inputs: []}
        """
        # これは 'params' が命令なのか 'wiring' が命令なのか判断できないためエラーになるべき
        with pytest.raises(OdlCompilationError, match="Invalid ODL structure"):
            parser.parse(ambiguous_source)

    def test_tc_parser_005_security_check(self):
        """TC-PARSER-005: 危険なタグを含むYAMLを弾くこと"""
        malicious_yaml = "!!python/object/apply:os.system ['echo pwned']"
        with pytest.raises(OdlCompilationError):
            parser.parse(malicious_yaml)

    def test_tc_parser_006_auto_restructuring(self):
        """
        TC-PARSER-006: Auto-Restructuring (Params & Wiring)
        フラットな属性が params と wiring に自動的に振り分けられること。
        """
        # params行き: agent, count / wiring行き: inputs, output
        source = """
        opcode: worker
        agent: Bob
        count: 5
        inputs: [DocA]
        output: DocB
        """
        result = parser.parse(source)
        
        # 構造化の検証
        assert result[NodeField.OPCODE] == "worker"
        
        # Params check
        assert result[NodeField.PARAMS]["agent"] == "Bob"
        assert result[NodeField.PARAMS]["count"] == 5
        assert "agent" not in result # 元の場所からは消えていること
        
        # Wiring check
        assert result[NodeField.WIRING][NodeField.INPUTS] == ["DocA"]
        assert result[NodeField.WIRING][NodeField.OUTPUT] == "DocB"
        assert NodeField.INPUTS not in result

    def test_tc_parser_007_shorthand_normalization(self):
        """
        TC-PARSER-007: Shorthand Normalization
        単一キー辞書が正規化されること。
        """
        # Case 1: Dict Body -> merge
        source_dict = """
        worker:
          agent: Alice
        """
        result_dict = parser.parse(source_dict)
        assert result_dict[NodeField.OPCODE] == "worker"
        assert result_dict[NodeField.PARAMS]["agent"] == "Alice"

        # Case 2: Primitive -> params (簡易記法)
        # 実装上の _normalize_recursive ケース B-4
        source_prim = "worker: {a: 1}" # これはB-2扱いになる可能性が高いが、None等のケースも想定
        result_prim = parser.parse(source_prim)
        assert result_prim[NodeField.OPCODE] == "worker"
        assert result_prim[NodeField.PARAMS]["a"] == 1

    def test_tc_parser_008_list_body_normalization(self):
        """
        TC-PARSER-008: List Body Normalization
        リストを値に持つショートハンドが children に正規化されること。
        """
        source = """
        serial:
          - worker: {agent: A}
          - worker: {agent: B}
        """
        result = parser.parse(source)
        
        assert result[NodeField.OPCODE] == "serial"
        assert NodeField.CHILDREN in result
        assert isinstance(result[NodeField.CHILDREN], list)
        assert len(result[NodeField.CHILDREN]) == 2
        
        # 子要素も再帰的に正規化されていること
        child0 = result[NodeField.CHILDREN][0]
        assert child0[NodeField.OPCODE] == "worker"
        assert child0[NodeField.PARAMS]["agent"] == "A"