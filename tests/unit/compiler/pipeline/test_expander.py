import pytest
import copy

from odl.types import OpCode, NodeField, KEY_ITERATION_BINDING
from odl.compiler.pipeline import expander

class TestExpander:
    """
    BP-L1-05-ODL-EXPANDER: Pipeline Expander
    Sugar展開、ID生成、メタデータ継承を検証する。
    """

    def test_tc_expander_001_passthrough_and_order(self):
        """TC-EXPANDER-001: Sugarを含まないノードはそのまま返却され、順序が維持されること"""
        raw = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "A"}},
                {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "B"}}
            ]
        }
        result = expander.expand(raw)
        
        # 構造が変わっていないこと
        assert result[NodeField.OPCODE] == "serial"
        assert len(result[NodeField.CHILDREN]) == 2
        # IDが自動付与されていること
        assert result[NodeField.CHILDREN][0][NodeField.STACK_PATH] == "root/serial_0/worker_0"
        assert result[NodeField.CHILDREN][1][NodeField.STACK_PATH] == "root/serial_0/worker_1"

        # Outputが正規化されていること
        # 修正: 自身のIDではなく、親(Scope)のID "#default" が付与される
        assert result[NodeField.CHILDREN][0][NodeField.WIRING][NodeField.OUTPUT] == "A#default"

    def test_tc_expander_002_fanout_expansion_structure(self):
        """TC-EXPANDER-002: fan_out が serial [ iterator_init, iterate ] に展開されること"""
        sugar = {
            NodeField.STACK_PATH: None, NodeField.OPCODE: "fan_out",
            "source": "users", "item_key": "uid",
            NodeField.CONTENTS: {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "doc"}}
        }
        result = expander.expand(sugar)

        # 1. Wrapper Check
        assert result[NodeField.OPCODE] == OpCode.SERIAL
        assert result[NodeField.STACK_PATH] == "root/serial_0"

        # 2. Children Check
        children = result[NodeField.CHILDREN]
        assert len(children) == 2
        
        # Child 1: Iterator Init
        assert children[0][NodeField.OPCODE] == "iterator_init"
        assert children[0][NodeField.PARAMS]["source"] == "users"
        assert children[0][NodeField.PARAMS]["item_key"] == "uid"

        # Child 2: Iterate
        assert children[1][NodeField.OPCODE] == "iterate"
        # Iterateの中身も展開されていること
        inner = children[1][NodeField.CONTENTS]
        assert inner[NodeField.OPCODE] == "worker"
        
        # --- 修正箇所: iter_1 -> iterate_1 ---
        # IDが階層化されていること (root -> serial_0 -> iterate_1 -> worker_0)
        assert "root/serial_0/iterate_1/{$KEY}/worker_0" == inner[NodeField.STACK_PATH]

    def test_tc_expander_003_recursive_expansion(self):
        """TC-EXPANDER-003: ネストされたSugarが再帰的に全て展開されること"""
        nested_sugar = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "fan_out",
            "source": "L1", "item_key": "K1",
            NodeField.CONTENTS: {
                NodeField.OPCODE: "fan_out", # Nested Fan-out
                "source": "L2", "item_key": "K2",
                NodeField.CONTENTS: {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "doc"}}
            }
        }
        result = expander.expand(nested_sugar)

        def check_no_sugar(node):
            assert node[NodeField.OPCODE] != "fan_out"
            for child in node.get(NodeField.CHILDREN, []):
                check_no_sugar(child)
            if NodeField.CONTENTS in node:
                check_no_sugar(node[NodeField.CONTENTS])

        check_no_sugar(result)

    def test_tc_expander_004_deterministic_id(self):
        """TC-EXPANDER-004: ID生成が決定論的であること"""
        sugar = {
            NodeField.STACK_PATH: None, NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [{NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "A"}}]
        }
        
        result1 = expander.expand(copy.deepcopy(sugar))
        result2 = expander.expand(copy.deepcopy(sugar))

        id1 = result1[NodeField.CHILDREN][0][NodeField.STACK_PATH]
        id2 = result2[NodeField.CHILDREN][0][NodeField.STACK_PATH]

        assert id1 == id2
        assert id1 == "root/serial_0/worker_0"

    def test_tc_expander_005_metadata_preservation(self):
        """TC-EXPANDER-005: Sugarの属性がWrapperに継承されること"""
        sugar = {
            NodeField.STACK_PATH: "task", NodeField.OPCODE: "fan_out",
            NodeField.PARAMS: {"timeout": 100},
            NodeField.WIRING: {"retry": "always"}, # Custom field in wiring
            "description": "Desc",
            "source": "src", "item_key": "key",
            NodeField.CONTENTS: {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "A"}}
        }
        result = expander.expand(sugar)

        assert result[NodeField.PARAMS]["timeout"] == 100
        assert result[NodeField.WIRING]["retry"] == "always"
        assert result["description"] == "Desc"

    def test_tc_expander_006_payload_mapping(self):
        """TC-EXPANDER-006: fan_outの中身がiterate配下に正しく移動していること"""
        sugar = {
            NodeField.STACK_PATH: "par", NodeField.OPCODE: "fan_out",
            "source": "s", "item_key": "k",
            NodeField.CONTENTS: {NodeField.OPCODE: "worker", NodeField.PARAMS: {"p": 999}, NodeField.WIRING: {NodeField.OUTPUT: "A"}}
        }
        result = expander.expand(sugar)
        
        iterate_node = result[NodeField.CHILDREN][1]
        payload = iterate_node[NodeField.CONTENTS]
        
        assert payload[NodeField.OPCODE] == "worker"
        assert payload[NodeField.PARAMS]["p"] == 999

    def test_tc_expander_007_ensemble_expansion(self):
        """TC-EXPANDER-007: EnsembleがDiverge/Convergeパターンへ正しく展開されること"""
        sugar = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "ensemble",
            NodeField.PARAMS: {
                "generators": ["AgentA", "AgentB"],
                "samples": 2,
                "consolidator": "Boss"
            },
            NodeField.WIRING: {NodeField.OUTPUT: "Idea"}
        }
        result = expander.expand(sugar)

        # 1. Wrapper
        assert result[NodeField.OPCODE] == OpCode.SERIAL
        
        # 2. Diverge (Parallel)
        parallel = result[NodeField.CHILDREN][0]
        assert parallel[NodeField.OPCODE] == OpCode.PARALLEL
        # A*2 + B*2 = 4 workers
        assert len(parallel[NodeField.CHILDREN]) == 4
        
        # Check ID Stacking logic
        # {OutputName}#{AgentID}/{Index} -> Private Naming: _{OutputName}#...
        w1 = parallel[NodeField.CHILDREN][0]
        assert w1[NodeField.PARAMS]["agent"] == "AgentA"
        # 【修正】内部成果物は `_` (Private) で始まるIDになる
        assert w1[NodeField.WIRING][NodeField.OUTPUT] == "_Idea#default/AgentA/1"

        # 3. Converge (Worker)
        converge = result[NodeField.CHILDREN][1]
        assert converge[NodeField.OPCODE] == OpCode.WORKER
        assert converge[NodeField.PARAMS]["agent"] == "Boss"
        
        # Inputsに発散した成果物が全て含まれていること
        inputs = converge[NodeField.WIRING][NodeField.INPUTS]
        # 【修正】Converge側も `_` 付きのIDを参照していること
        assert "_Idea#default/AgentA/1" in inputs
        assert "_Idea#default/AgentA/2" in inputs
        assert "_Idea#default/AgentB/1" in inputs
        assert "_Idea#default/AgentB/2" in inputs
        
        # 最終的なOutputはPublic（_なし）であること
        # Note: expander.pyのルート呼び出し仕様により、output_scope_id=node_id("root") となる
        assert converge[NodeField.WIRING][NodeField.OUTPUT] == "Idea#default"

    def test_tc_expander_008_output_normalization(self):
        """TC-EXPANDER-008: Outputが論理名のみの場合、物理IDに正規化されること"""
        node = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "worker",
            NodeField.WIRING: {NodeField.OUTPUT: "Doc"}
        }
        result = expander.expand(node)
        
        # root#default (Expander logic: if defined_id is root, normalize uses root)
        # _process_standard_node -> _normalize_output
        assert result[NodeField.WIRING][NodeField.OUTPUT] == "Doc#default"

    def test_tc_expander_009_variable_scope_definition(self):
        """TC-EXPANDER-009: __key が $KEY に置換されること"""
        sugar = {
            NodeField.STACK_PATH: "root", NodeField.OPCODE: "fan_out",
            "source": "list", "item_key": "k",
            NodeField.CONTENTS: {
                NodeField.OPCODE: "worker",
                NodeField.WIRING: {
                    NodeField.INPUTS: [KEY_ITERATION_BINDING, "OtherDoc"],
                    NodeField.OUTPUT: "Res"
                }
            }
        }
        result = expander.expand(sugar)
        
        iterate_node = result[NodeField.CHILDREN][1]
        inner_worker = iterate_node[NodeField.CONTENTS]
        
        inputs = inner_worker[NodeField.WIRING][NodeField.INPUTS]
        assert "{$KEY}" in inputs
        assert KEY_ITERATION_BINDING not in inputs
        assert "OtherDoc" in inputs # 他は変わっていないこと

    def test_tc_expander_010_generate_team_expansion(self):
        """
        Generate Team Expansion
        Loop構造への展開と、Feedback LoopのID生成、Scope IDの透過を検証する。
        """
        sugar = {
            NodeField.STACK_PATH: "team_root",
            NodeField.OPCODE: "generate_team",
            NodeField.PARAMS: {"generator": "GenA", "validators": ["ValA"], "loop": 5},
            NodeField.WIRING: {NodeField.INPUTS: ["Req"], NodeField.OUTPUT: "Draft"}
        }
        # ルートなので output_scope_id="team_root" として展開される
        result = expander.expand(sugar)

        # 1. Loop Check
        loop_node = result[NodeField.CHILDREN][0]
        assert loop_node[NodeField.OPCODE] == OpCode.LOOP
        assert loop_node[NodeField.PARAMS]["count"] == 5

        # 2. Inner Structure Check
        inner_serial = loop_node[NodeField.CONTENTS]
        generator = inner_serial[NodeField.CHILDREN][0]
        
        # Generator Output Check
        # GenerateTeamは自前で v{$LOOP} をつける仕様
        # ID: Output#Scope/v{$LOOP}
        expected_output = "Draft#default/v{$LOOP}"
        assert generator[NodeField.WIRING][NodeField.OUTPUT] == expected_output

        # 3. Feedback Injection Check
        inputs = generator[NodeField.WIRING][NodeField.INPUTS]
        # Previous Output
        assert "Draft#default/v{$LOOP-1}" in inputs
        # Validator Feedback (Review ID)
        assert "Draft__Review_ValA#default/v{$LOOP-1}" in inputs

    def test_tc_expander_011_approval_gate_expansion(self):
        """
        Approval Gate Expansion
        Scope IDへの 'v{$LOOP}' の動的スタックと、内部ノードへの伝播を検証する。
        """
        sugar = {
            NodeField.STACK_PATH: "gate_root",
            NodeField.OPCODE: "approval_gate",
            NodeField.PARAMS: {"approver": "Boss", "target": "FinalDoc"},
            # 内部は普通のWorker（Scope透過の確認用）
            NodeField.CONTENTS: {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["Base"], NodeField.OUTPUT: "FinalDoc"}}
        }
        result = expander.expand(sugar)

        loop_node = result[NodeField.CHILDREN][0]
        inner_serial = loop_node[NodeField.CONTENTS]

        # 1. Inner Logic (Worker) Output Check
        # Gateが Scope ID に "/v{$LOOP}" を追加して渡しているはず
        # 期待値: FinalDoc#default/v{$LOOP}
        inner_worker = inner_serial[NodeField.CHILDREN][0]
        assert inner_worker[NodeField.WIRING][NodeField.OUTPUT] == "FinalDoc#default/v{$LOOP}"

        # 2. Feedback Injection Check (Gate -> Inner Worker)
        # Gateのフィードバック(Bossのコメント)が注入されているか
        assert "FinalDoc__Review_Boss#default/v{$LOOP-1}" in inner_worker[NodeField.WIRING][NodeField.INPUTS]

        # 3. Dialogue Output Check
        # Dialogueも同じScope(Loop内)にいるが、OutputはFeedback ID
        dialogue = inner_serial[NodeField.CHILDREN][1]
        assert dialogue[NodeField.OPCODE] == OpCode.APPROVER
        assert dialogue[NodeField.WIRING][NodeField.OUTPUT] == "FinalDoc__Review_Boss#default/v{$LOOP}"

    def test_tc_expander_012_complex_nesting(self):
        """
        Master Case 2_2_4 (Fan-out > Serial > Ensemble + GenerateTeam)
        Fan-outとSerialを経由した深い階層での Scope ID 透過とスタッキングを検証。
        """
        sugar = {
            NodeField.STACK_PATH: "root_fanout",
            NodeField.OPCODE: "fan_out",
            "source": "Regions", "item_key": "RegID",
            "strategy": "parallel",
            NodeField.CONTENTS: {
                NodeField.OPCODE: "serial",
                NodeField.CHILDREN: [
                    # Step 1: Ensemble
                    {
                        NodeField.OPCODE: "ensemble",
                        "generators": ["P1"], "samples": 1, "consolidator": "Dir",
                        NodeField.WIRING: {NodeField.INPUTS: ["MarketData"], NodeField.OUTPUT: "Concept"}
                    },
                    # Step 2: Generate Team
                    {
                        NodeField.OPCODE: "generate_team",
                        "generator": "Eng", "validators": ["QA"], "loop": 3,
                        NodeField.WIRING: {NodeField.INPUTS: ["Concept"], NodeField.OUTPUT: "Blueprint"}
                    }
                ]
            }
        }
        result = expander.expand(sugar)

        # 階層掘り下げ
        iterate_node = result[NodeField.CHILDREN][1] # Fan-outのIterate部分
        inner_serial = iterate_node[NodeField.CONTENTS] # 内部のSerial
        
        # 期待される親スコープID
        # Fan-outが "{$KEY}" をスタックし、Serialはそれを透過させる
        expected_scope_id = "default/{$KEY}"

        # --- 1. Ensemble Check ---
        ensemble_wrapper = inner_serial[NodeField.CHILDREN][0]
        ens_converge = ensemble_wrapper[NodeField.CHILDREN][1]
        
        # Ensembleの出力は親スコープIDで正規化される
        assert ens_converge[NodeField.WIRING][NodeField.OUTPUT] == f"Concept#{expected_scope_id}"

        # --- 2. Generate Team Check ---
        gt_wrapper = inner_serial[NodeField.CHILDREN][1]
        gt_loop = gt_wrapper[NodeField.CHILDREN][0]
        gt_inner_serial = gt_loop[NodeField.CONTENTS]
        gt_generator = gt_inner_serial[NodeField.CHILDREN][0]

        # Generate Teamの出力は、親スコープID + v{$LOOP}
        assert gt_generator[NodeField.WIRING][NodeField.OUTPUT] == f"Blueprint#{expected_scope_id}/v{{$LOOP}}"

        # Scope Resolveのマップ先も確認
        gt_resolve = gt_wrapper[NodeField.CHILDREN][1]
        assert gt_resolve[NodeField.PARAMS]["map_to"] == f"Blueprint#{expected_scope_id}"

    def test_tc_expander_013_explicit_id_binding(self):
        """
        【NEW】TC-EXPANDER-013: Explicit ID Binding
        明示的にID(#)を指定した場合、デフォルトスコープ(#default)で上書きされず、
        指定したIDが優先して使用されることを検証する。
        """
        node = {
            NodeField.STACK_PATH: "root", 
            NodeField.OPCODE: "serial",
            NodeField.CHILDREN: [
                # Case A: Implicit (省略) -> #default
                {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "ImplicitDoc"}},
                # Case B: Explicit (明示) -> #SpecificID (Preserved)
                {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.OUTPUT: "ExplicitDoc#FixedVer"}},
                # Case C: Explicit in Input -> #SpecificID (Preserved)
                {NodeField.OPCODE: "worker", NodeField.WIRING: {NodeField.INPUTS: ["ExplicitDoc#FixedVer"], NodeField.OUTPUT: "Final"}}
            ]
        }
        result = expander.expand(node)
        
        # A: Implicit -> default
        assert result[NodeField.CHILDREN][0][NodeField.WIRING][NodeField.OUTPUT] == "ImplicitDoc#default"
        
        # B: Explicit -> FixedVer (NOT #default)
        assert result[NodeField.CHILDREN][1][NodeField.WIRING][NodeField.OUTPUT] == "ExplicitDoc#FixedVer"
        
        # C: Input Explicit -> FixedVer
        assert result[NodeField.CHILDREN][2][NodeField.WIRING][NodeField.INPUTS][0] == "ExplicitDoc#FixedVer"

    def test_tc_expander_14_briefing_injection(self):
        """
        TC-EXPANDER-14: Briefing Parameter Injection
        Feature 'Briefing': generate_team/ensemble で指定したコンテキストが
        内部の全Workerへ正しく、かつ安全に注入されることを検証する。
        """
        
        # --- Case A: Generate Team ---
        gt_sugar = {
            NodeField.STACK_PATH: "root_gt",
            NodeField.OPCODE: "generate_team",
            NodeField.PARAMS: {
                "generator": "GenAgent",
                "validators": ["ValAgent"],
                "briefing": {
                    "project_code": "PRJ-999",  # 注入したい値
                    "mode": "hacked"            # システム予約語との衝突（無視されるべき）
                }
            },
            NodeField.WIRING: {NodeField.OUTPUT: "Draft"}
        }
        gt_result = expander.expand(gt_sugar)

        # 構造掘り下げ: Serial -> Loop -> Serial -> Worker(Generator)
        loop_node = gt_result[NodeField.CHILDREN][0]
        inner_serial = loop_node[NodeField.CONTENTS]
        generator_worker = inner_serial[NodeField.CHILDREN][0]
        
        # 1. Briefingの値が入っているか
        assert generator_worker[NodeField.PARAMS]["project_code"] == "PRJ-999"
        
        # 2. Systemパラメータが優先されているか (mode: generate != hacked)
        assert generator_worker[NodeField.PARAMS]["mode"] == "generate"
        assert generator_worker[NodeField.PARAMS]["agent"] == "GenAgent"

        # Validatorへの注入確認
        val_parallel = inner_serial[NodeField.CHILDREN][1]
        val_worker = val_parallel[NodeField.CHILDREN][0]
        assert val_worker[NodeField.PARAMS]["project_code"] == "PRJ-999"
        assert val_worker[NodeField.PARAMS]["mode"] == "validate"

        # --- Case B: Ensemble ---
        ens_sugar = {
            NodeField.STACK_PATH: "root_ens",
            NodeField.OPCODE: "ensemble",
            NodeField.PARAMS: {
                "generators": ["AgentA", "AgentB"],
                "consolidator": "Boss",
                "briefing": {
                    "tone": "formal",
                    "max_length": 100
                }
            },
            NodeField.WIRING: {NodeField.OUTPUT: "Idea"}
        }
        ens_result = expander.expand(ens_sugar)

        # 構造掘り下げ: Serial -> [Parallel(Diverge), Worker(Converge)]
        diverge_parallel = ens_result[NodeField.CHILDREN][0]
        converge_worker = ens_result[NodeField.CHILDREN][1]

        # 1. Diverge (Generator) への注入確認
        gen_worker_a = diverge_parallel[NodeField.CHILDREN][0]
        assert gen_worker_a[NodeField.PARAMS]["agent"] == "AgentA"
        assert gen_worker_a[NodeField.PARAMS]["tone"] == "formal"
        assert gen_worker_a[NodeField.PARAMS]["max_length"] == 100

        # 2. Converge (Consolidator) への注入確認
        assert converge_worker[NodeField.PARAMS]["agent"] == "Boss"
        assert converge_worker[NodeField.PARAMS]["tone"] == "formal"