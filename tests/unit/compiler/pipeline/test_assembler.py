import pytest
from pydantic import ValidationError

from odl.types import IrComponent, OpCode, NodeField
from odl.compiler.pipeline import assembler
from odl.compiler.exceptions import OdlCompilationError

class TestAssembler:
    """
    BP-L1-03-ODL-ASSEMBLER: Pipeline Assembler
    辞書データからIrComponentへの変換とバリデーションを検証する。
    """

    def test_tc_assembler_001_simple_component_assembly(self):
        """TC-ASSEMBLER-001: 最小構成の辞書が正しくオブジェクトに変換されること"""
        data = {
            NodeField.STACK_PATH: "node1",
            NodeField.OPCODE: "serial",
            NodeField.PARAMS: {"timeout": 100},
            NodeField.WIRING: {NodeField.INPUTS: ["A"], NodeField.OUTPUT: "B"}
        }
        result = assembler.assemble(data)
        
        assert isinstance(result, IrComponent)
        assert result.stack_path == "node1"
        assert result.opcode == OpCode.SERIAL
        assert result.params["timeout"] == 100
        assert result.wiring.inputs == ["A"]

    def test_tc_assembler_002_recursive_structure_assembly(self):
        """TC-ASSEMBLER-002: 入れ子構造(children/contents)が再帰的に構築されること"""
        # Case A: Children (List)
        list_data = {
            NodeField.STACK_PATH: "root",
            NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "c1", NodeField.OPCODE: "worker"},
                {NodeField.STACK_PATH: "c2", NodeField.OPCODE: "worker"}
            ]
        }
        res_list = assembler.assemble(list_data)
        assert len(res_list.children) == 2
        assert isinstance(res_list.children[0], IrComponent)
        assert res_list.children[0].stack_path == "c1"

        # Case B: Contents (Single Block)
        block_data = {
            NodeField.STACK_PATH: "loop1",
            NodeField.OPCODE: "loop",
            NodeField.CONTENTS: {
                NodeField.STACK_PATH: "inner", 
                NodeField.OPCODE: "worker"
            }
        }
        res_block = assembler.assemble(block_data)
        assert isinstance(res_block.contents, IrComponent)
        assert res_block.contents.stack_path == "inner"

    def test_tc_assembler_003_validation_error_context(self):
        """TC-ASSEMBLER-003: バリデーションエラー時にOdlCompilationErrorにラップされること"""
        # 不正なOpCode
        invalid_data = {
            NodeField.STACK_PATH: "bad",
            NodeField.OPCODE: "INVALID_CODE" 
        }
        with pytest.raises(OdlCompilationError) as exc:
            assembler.assemble(invalid_data)
        
        # エラーメッセージにフィールド名が含まれていることを期待
        assert NodeField.OPCODE in str(exc.value).lower() or "validation error" in str(exc.value).lower()

    def test_tc_assembler_004_extra_fields_handling(self):
        """TC-ASSEMBLER-004: 定義にない余計なフィールドは無視されること"""
        # Pydanticのデフォルト設定(extra='ignore')に依存
        data = {
            NodeField.STACK_PATH: "n1", 
            NodeField.OPCODE: "worker", 
            "unknown_field": "ignore_me"
        }
        result = assembler.assemble(data)
        assert not hasattr(result, "unknown_field")

    def test_tc_assembler_005_mixed_type_safety(self):
        """TC-ASSEMBLER-005: リスト内に辞書以外の型が混入した場合のエラーハンドリング"""
        mixed_data = {
            NodeField.STACK_PATH: "root",
            NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "ok", NodeField.OPCODE: "worker"},
                "this_is_not_a_dict" # Invalid item
            ]
        }
        with pytest.raises(OdlCompilationError):
            assembler.assemble(mixed_data)