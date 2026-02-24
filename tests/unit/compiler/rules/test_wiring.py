import pytest
from odl.types import NodeField
from odl.compiler.rules import wiring
from odl.compiler.exceptions import OdlCompilationError

class TestWiringRules:
    """
    BP-L1-04-ODL-RULES: Wiring Rules
    IDの整合性（一意性、参照、循環）を検証する。
    注意: 入力データは Resolver 通過後を想定し、
    Input参照は 'DocName#NodeID' の形式で記述する。
    """

    def test_tc_wiring_001_duplicate_id_detection(self):
        """TC-RULES-WIRING-001: 深い階層にある重複IDを検知すること"""
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "A", NodeField.OPCODE: "worker"},
                # 別の枝にある同じID "A"
                {
                    NodeField.STACK_PATH: "sub", NodeField.OPCODE: "serial", 
                    NodeField.CHILDREN: [{NodeField.STACK_PATH: "A", NodeField.OPCODE: "worker"}]
                }
            ]
        }
        with pytest.raises(OdlCompilationError, match="Duplicate ID found"):
            wiring.validate(root)

    def test_tc_wiring_002_valid_complex_dag(self):
        """TC-RULES-WIRING-002: 循環ではない複雑なDAG（菱形構造）は許可されること"""
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                # Top -> output: "Top" -> Physical: "Top#Top"
                {NodeField.STACK_PATH: "Top", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "Top"}},
                
                # Left -> inputs: ["Top#Top"] -> output: "Left#Left"
                {NodeField.STACK_PATH: "Left", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["Top#Top"], NodeField.OUTPUT: "Left"}},
                
                # Right -> inputs: ["Top#Top"] -> output: "Right#Right"
                {NodeField.STACK_PATH: "Right", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["Top#Top"], NodeField.OUTPUT: "Right"}},
                
                # Bottom -> inputs: ["Left#Left", "Right#Right"]
                {NodeField.STACK_PATH: "Bottom", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["Left#Left", "Right#Right"]}}
            ]
        }
        # エラーにならないこと
        wiring.validate(root)

    def test_tc_wiring_003_circular_dependency(self):
        """TC-RULES-WIRING-003: 循環参照(A->B->A)および自己参照(A->A)を検知すること"""
        # Case A: Self Reference (Node A references Doc A produced by Node A)
        self_ref = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "A", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["Doc#A"], NodeField.OUTPUT: "Doc"}}
            ]
        }
        # Aの検証時点で "Doc#A" はまだ見えていない（自分が生成中）
        with pytest.raises(OdlCompilationError, match="Undefined Artifact ID"):
            wiring.validate(self_ref)

        # Case B: Loop (A->B->A)
        loop_graph = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "A", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["DocB#B"], NodeField.OUTPUT: "DocA"}},
                {NodeField.STACK_PATH: "B", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["DocA#A"], NodeField.OUTPUT: "DocB"}}
            ]
        }
        # Aの時点で B の出力 "DocB#B" は見えていない（弟）
        with pytest.raises(OdlCompilationError, match="Undefined Artifact ID"):
            wiring.validate(loop_graph)

    def test_tc_wiring_004_dangling_reference(self):
        """TC-RULES-WIRING-004: 存在しないIDへの参照を検知すること"""
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "A", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["GhostID"]}}
            ]
        }
        with pytest.raises(OdlCompilationError, match="Undefined Artifact ID"):
            wiring.validate(root)

    def test_tc_wiring_005_artifact_reference_validation(self):
        """TC-RULES-WIRING-005: InputsはOutput ID(Name#ID)を参照すること"""
        # 正常系: n1が出す "DocA#n1" を n2が参照
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "n1", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "DocA"}},
                {NodeField.STACK_PATH: "n2", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["DocA#n1"]}}
            ]
        }
        wiring.validate(root)

        # 異常系: ノードID "n1" そのものを参照しようとしている（Artifactではない）
        invalid_root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "n1", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "DocA"}},
                {NodeField.STACK_PATH: "n2", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["n1"]}}
            ]
        }
        with pytest.raises(OdlCompilationError, match="Undefined Artifact ID"):
            wiring.validate(invalid_root)

    def test_tc_wiring_006_forward_reference_prohibition(self):
        """TC-RULES-WIRING-006: Serial内での前方参照（未来への参照）を禁止すること"""
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.STACK_PATH: "consumer", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["FutureDoc#producer"]}},
                {NodeField.STACK_PATH: "producer", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "FutureDoc"}}
            ]
        }
        with pytest.raises(OdlCompilationError, match="Undefined Artifact ID"):
            wiring.validate(root)

    def test_tc_wiring_007_dynamic_reference_ignore(self):
        """TC-RULES-WIRING-007: $を含む動的参照は静的チェックをスキップすること"""
        root = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                # "Doc#v{$LOOP-1}" はまだ定義されていないが、動的変数を含むため許可される
                {
                    NodeField.STACK_PATH: "n1", NodeField.OPCODE: "worker", 
                    NodeField.WIRING: {NodeField.INPUTS: ["Doc#v{$LOOP-1}"], NodeField.OUTPUT: "Result"}
                }
            ]
        }
        wiring.validate(root)

    def test_tc_wiring_008_self_reference_in_loop(self):
        """TC-RULES-WIRING-008: ループ内での過去の自己参照が許可されること"""
        root = {
            NodeField.STACK_PATH: "loop_root", 
            NodeField.OPCODE: "loop",
            NodeField.CONTENTS: {
                NodeField.OPCODE: "serial",
                NodeField.CHILDREN: [
                    {
                        NodeField.STACK_PATH: "worker", 
                        NodeField.OPCODE: "worker",
                        # outputと同じ名前をinputに取る（前回ループの結果）
                        # $LOOP等が含まれていればOK
                        NodeField.WIRING: {NodeField.INPUTS: ["MyDoc#v{$LOOP-1}"], NodeField.OUTPUT: "MyDoc"}
                    }
                ]
            }
        }
        wiring.validate(root)

    def test_tc_wiring_009_scope_resolution_visibility(self):
        """TC-RULES-WIRING-009: scope_resolveで公開されたIDが、親スコープの兄弟から参照可能であること"""
        root = {
            NodeField.STACK_PATH: "root", 
            NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                # 1. 内部で成果物を作り、scope_resolveで外に出すブロック (team_block)
                {
                    NodeField.STACK_PATH: "team_block",
                    NodeField.OPCODE: "serial",
                    NodeField.CHILDREN: [
                        # 内部Worker (Output: Draft)
                        {NodeField.STACK_PATH: "worker", NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "Draft"}},
                        
                        # Draft を FinalDoc#v1 として外に公開
                        # (Expander通過後を想定し、map_toには物理IDが入っている前提)
                        {
                            NodeField.OPCODE: "scope_resolve", 
                            "map_to": "FinalDoc#v1", 
                            NodeField.WIRING: {} 
                        }
                    ]
                },
                # 2. その成果物を参照する兄弟ノード (consumer)
                {
                    NodeField.STACK_PATH: "consumer", 
                    NodeField.OPCODE: "worker",
                    NodeField.WIRING: {
                        # team_blockから公開された "FinalDoc#v1" を参照できるはず
                        NodeField.INPUTS: ["FinalDoc#v1"], 
                        NodeField.OUTPUT: "Done"
                    } 
                }
            ]
        }
        # エラーにならなければ、scope_resolveの可視性が正しく親スコープへ伝播している
        wiring.validate(root)

    def test_tc_wiring_010_invalid_system_variable_typo(self):
        """TC-RULES-WIRING-010: 無効なシステム変数（タイポ等）が含まれている場合にエラーになること"""
        
        # Case A: Invalid Typo ($LOOOP)
        root_typo = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {
                    NodeField.STACK_PATH: "n1", NodeField.OPCODE: "worker", 
                    # $LOOOP は存在しないためエラーになるべき
                    NodeField.WIRING: {NodeField.INPUTS: ["Doc#v{$LOOOP}"], NodeField.OUTPUT: "Out"}
                }
            ]
        }
        with pytest.raises(OdlCompilationError, match="Invalid system variable usage"):
            wiring.validate(root_typo)

        # Case B: Invalid Case ($loop - lowercase is not allowed if strict)
        # 実装が完全一致チェックなら弾かれるはず
        root_case = {
            NodeField.STACK_PATH: "root2", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {
                    NodeField.STACK_PATH: "n2", NodeField.OPCODE: "worker", 
                    NodeField.WIRING: {NodeField.INPUTS: ["Doc#v{$loop}"], NodeField.OUTPUT: "Out"}
                }
            ]
        }
        with pytest.raises(OdlCompilationError, match="Invalid system variable usage"):
            wiring.validate(root_case)

        # Case C: Valid Variable ($LOOP) - Should pass (ignored by wiring rule)
        root_valid = {
            NodeField.STACK_PATH: "root3", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {
                    NodeField.STACK_PATH: "n3", NodeField.OPCODE: "worker", 
                    NodeField.WIRING: {NodeField.INPUTS: ["Doc#v{$LOOP}"], NodeField.OUTPUT: "Out"}
                }
            ]
        }
        # エラーにならないこと
        wiring.validate(root_valid)