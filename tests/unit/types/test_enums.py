import pytest
from odl.types import OpCode, NodeType

class TestEnums:
    """
    TDD Blueprint: BP-L0-ODL-ENUMS
    Target: services/shared/src/shared/domains/odl/enums.py
    Reference: cocrea-2003 (Kernel Specification)
    """

    def test_opcode_coverage(self):
        """TC-ODL-ENUM-001: OpCode Coverage"""
        # Atoms
        assert OpCode.WORKER == "worker"
        assert OpCode.DIALOGUE == "dialogue"
        assert OpCode.APPROVER == "approver"
        
        # Controls
        assert OpCode.SERIAL == "serial"
        assert OpCode.PARALLEL == "parallel"
        assert OpCode.LOOP == "loop"
        assert OpCode.ITERATE == "iterate"
        
        # Logic
        assert OpCode.SCOPE_RESOLVE == "scope_resolve"
        assert OpCode.ITERATOR_INIT == "iterator_init"

        # 必須メンバーが8つ定義されていること
        assert len(OpCode) == 9

    def test_strenum_type_check(self):
        """TC-ODL-ENUM-002: StrEnum Type Check"""
        # JSONシリアライズ時の互換性のため、文字列として振る舞うことを検証
        assert isinstance(OpCode.WORKER, str)
        assert OpCode.WORKER.value == "worker"
        assert OpCode.WORKER + "_test" == "worker_test"

    def test_node_type_definition(self):
        """TC-ODL-ENUM-003: NodeType Definition"""
        # 定義値の確認
        assert NodeType.ACTION == "ACTION"
        assert NodeType.CONTROL == "CONTROL"
        assert NodeType.LOGIC == "LOGIC"
        
        # StrEnumとしての振る舞い確認
        assert isinstance(NodeType.ACTION, str)

    def test_opcode_property_node_type(self):
        """TC-ODL-ENUM-004: OpCode to NodeType Mapping"""
        # Action Group
        assert OpCode.WORKER.node_type == NodeType.ACTION
        assert OpCode.DIALOGUE.node_type == NodeType.ACTION
        
        # Control Group
        assert OpCode.SERIAL.node_type == NodeType.CONTROL
        assert OpCode.PARALLEL.node_type == NodeType.CONTROL
        assert OpCode.LOOP.node_type == NodeType.CONTROL
        assert OpCode.ITERATE.node_type == NodeType.CONTROL
        
        # Logic Group
        assert OpCode.SCOPE_RESOLVE.node_type == NodeType.LOGIC
        assert OpCode.ITERATOR_INIT.node_type == NodeType.LOGIC