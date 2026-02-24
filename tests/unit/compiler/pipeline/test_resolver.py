import pytest

from odl.types import OpCode, NodeField
from odl.compiler.pipeline import resolver

class TestResolver:
    """
    BP-L1-06-ODL-RESOLVER: Pipeline Resolver
    配線解決、スコープ探索、Deep Collectionを検証する。
    """

    def test_tc_resolver_001_sibling_resolution(self):
        """TC-RESOLVER-001: 同一階層内の兄ノードの出力を解決できること"""
        root = {
            NodeField.OPCODE: OpCode.SERIAL,
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "n1", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.OUTPUT: "Design#n1"}},
                {NodeField.STACK_PATH: "n2", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.INPUTS: ["Design"]}}
            ]
        }
        result = resolver.resolve(root)
        inputs = result[NodeField.CHILDREN][1][NodeField.WIRING][NodeField.INPUTS]
        
        # 論理名 "Design" が 物理ID "Design#n1" に置換されていること
        assert len(inputs) == 1
        assert inputs[0] == "Design#n1"

    def test_tc_resolver_002_parent_scope_escalation(self):
        """TC-RESOLVER-002: 親スコープの出力を解決できること（ネスト対応）"""
        root = {
            NodeField.OPCODE: OpCode.SERIAL,
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "parent", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.OUTPUT: "Spec#p1"}},
                {
                    NodeField.OPCODE: OpCode.SERIAL, # Nested block
                    NodeField.CHILDREN: [
                        {NodeField.STACK_PATH: "child", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.INPUTS: ["Spec"]}}
                    ]
                }
            ]
        }
        result = resolver.resolve(root)
        child = result[NodeField.CHILDREN][1][NodeField.CHILDREN][0]
        
        assert child[NodeField.WIRING][NodeField.INPUTS][0] == "Spec#p1"

    def test_tc_resolver_003_visibility_constraints(self):
        """TC-RESOLVER-003: 弟や従兄弟（Parallelの隣）は見えないこと"""
        root = {
            NodeField.OPCODE: OpCode.PARALLEL,
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "A", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.INPUTS: ["DocB"]}}, 
                {NodeField.STACK_PATH: "B", NodeField.OPCODE: OpCode.WORKER, NodeField.WIRING: {NodeField.OUTPUT: "DocB#b1"}}
            ]
        }
        # 解決できない場合、現状の実装ではそのまま残る（外部参照扱いの可能性）
        # バリデーションエラーにする場合はWiringRuleでチェックする
        result = resolver.resolve(root)
        inputs = result[NodeField.CHILDREN][0][NodeField.WIRING][NodeField.INPUTS]
        
        # DocB#b1 に解決されず、DocB のまま残っていること
        assert inputs[0] == "DocB"

    def test_tc_resolver_004_deep_collection(self):
        """TC-RESOLVER-004: 複合ブロックの出力をDeep Collectionできること"""
        root = {
            NodeField.OPCODE: OpCode.SERIAL,
            NodeField.CHILDREN: [
                {
                    NodeField.OPCODE: OpCode.PARALLEL,
                    NodeField.CHILDREN: [
                        {NodeField.WIRING: {NodeField.OUTPUT: "Draft#w1"}},
                        {NodeField.WIRING: {NodeField.OUTPUT: "Draft#w2"}}
                    ]
                },
                {NodeField.WIRING: {NodeField.INPUTS: ["Draft"]}}
            ]
        }
        result = resolver.resolve(root)
        inputs = result[NodeField.CHILDREN][1][NodeField.WIRING][NodeField.INPUTS]

        # w1, w2 両方がリストとして収集されていること
        assert len(inputs) == 2
        assert "Draft#w1" in inputs
        assert "Draft#w2" in inputs

    def test_tc_resolver_005_ignore_physical_ids(self):
        """TC-RESOLVER-007: 既に物理IDや動的変数が含まれる場合は探索をスキップすること"""
        root = {
            NodeField.OPCODE: OpCode.SERIAL,
            NodeField.CHILDREN: [
                {NodeField.WIRING: {NodeField.OUTPUT: "Doc#old"}},
                {NodeField.WIRING: {NodeField.INPUTS: [
                    "Doc#explicit", # Explicit ID
                    "Doc#v{$LOOP}", # Dynamic Var
                    "Doc"           # Should be resolved to Doc#old
                ]}}
            ]
        }
        result = resolver.resolve(root)
        inputs = result[NodeField.CHILDREN][1][NodeField.WIRING][NodeField.INPUTS]

        assert "Doc#explicit" in inputs
        assert "Doc#v{$LOOP}" in inputs
        assert "Doc#old" in inputs

    def test_tc_resolver_006_scope_resolve_mapping(self):
        """TC-RESOLVER-009: scope_resolve の map_to がOutputとして認識されること"""
        root = {
            NodeField.OPCODE: OpCode.SERIAL,
            NodeField.CHILDREN: [
                {
                    NodeField.OPCODE: OpCode.SERIAL,
                    NodeField.CHILDREN: [
                        {
                            NodeField.OPCODE: "scope_resolve",
                            NodeField.PARAMS: {"target": "Final", "map_to": "Final#resolved"}
                        }
                    ]
                },
                {NodeField.WIRING: {NodeField.INPUTS: ["Final"]}}
            ]
        }
        result = resolver.resolve(root)
        inputs = result[NodeField.CHILDREN][1][NodeField.WIRING][NodeField.INPUTS]
        
        assert inputs[0] == "Final#resolved"