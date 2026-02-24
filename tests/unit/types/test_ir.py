import pytest
from pydantic import ValidationError
from odl.types import IrComponent, WiringObject, OpCode, NodeType

class TestIr:
    """
    TDD Blueprint: BP-L0-ODL-STRUCTS
    Target: services/shared/src/shared/domains/odl/structs.py
    """

    def test_wiring_object_defaults(self):
        """TC-ODL-STRUCT-001: WiringObject Validation"""
        # デフォルト値の確認
        wiring = WiringObject()
        assert wiring.inputs == []
        assert wiring.output is None

        # 値設定時の確認
        wiring_full = WiringObject(inputs=["var_a"], output="var_b")
        assert wiring_full.inputs == ["var_a"]
        assert wiring_full.output == "var_b"

    def test_ir_component_basic(self):
        """TC-ODL-STRUCT-002: IrComponent Basic Creation"""
        node = IrComponent(
            stack_path="node_basic",
            opcode=OpCode.WORKER,
            params={"model": "gpt-4"},
            wiring=WiringObject(inputs=["in1"], output="out1")
        )
        assert node.opcode == OpCode.WORKER
        assert node.params["model"] == "gpt-4"
        assert node.wiring.inputs == ["in1"]
        # デフォルト値
        assert node.children == []
        assert node.contents is None

    def test_ir_component_recursion_children(self):
        """TC-ODL-STRUCT-003: IrComponent Recursion (Children List)"""
        # 子ノード定義
        child1 = IrComponent(stack_path="c1", opcode=OpCode.WORKER)
        child2 = IrComponent(stack_path="c2", opcode=OpCode.WORKER)

        # 親ノード (Serial)
        parent = IrComponent(
            stack_path="root",
            opcode=OpCode.SERIAL,
            children=[child1, child2]
        )

        # 検証
        assert len(parent.children) == 2
        assert parent.children[0].stack_path == "c1"
        assert parent.children[1].stack_path == "c2"
        
        # model_dumpでの辞書化確認
        dumped = parent.model_dump()
        assert dumped["children"][0]["opcode"] == "worker"

    def test_ir_component_recursion_contents(self):
        """TC-ODL-STRUCT-004: IrComponent Recursion (Contents Block)"""
        # 内部ブロック
        body_node = IrComponent(stack_path="body", opcode=OpCode.SERIAL)

        # 親ノード (Loop)
        parent = IrComponent(
            stack_path="loop_root",
            opcode=OpCode.LOOP,
            contents=body_node
        )

        # 検証
        assert parent.contents is not None
        assert parent.contents.stack_path == "body"
        assert parent.contents.opcode == OpCode.SERIAL

    def test_validation_error(self):
        """不正なデータのバリデーション"""
        with pytest.raises(ValidationError):
            # opcodeはEnum必須
            IrComponent(stack_path="bad", opcode="INVALID_CODE")

        with pytest.raises(ValidationError):
            # childrenはIrComponentのリストでなければならない
            IrComponent(stack_path="bad_tree", opcode=OpCode.SERIAL, children=["not_a_node_object"])

    def test_ir_component_node_type_property(self):
        """TC-ODL-STRUCT-005: IrComponent NodeType Property Access"""
        # Case 1: Action Node (Worker)
        node_action = IrComponent(
            stack_path="w1", 
            opcode=OpCode.WORKER, 
            wiring=WiringObject(inputs=[], output="out")
        )
        assert node_action.node_type == NodeType.ACTION

        # Case 2: Control Node (Serial)
        node_control = IrComponent(
            stack_path="s1", 
            opcode=OpCode.SERIAL
        )
        assert node_control.node_type == NodeType.CONTROL

        # Case 3: Logic Node (ScopeResolve)
        node_logic = IrComponent(
            stack_path="sr1", 
            opcode=OpCode.SCOPE_RESOLVE,
            params={"target": "doc"}
        )
        assert node_logic.node_type == NodeType.LOGIC