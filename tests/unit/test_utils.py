import pytest
import yaml
from odl import utils
from odl.types import IrComponent, OpCode, WiringObject, NodeField

class TestUtils:
    """
    Utility Functions Test
    Target: src/odl/utils.py
    """

    def test_load_ir_from_spec_basic(self):
        """
        TC-UTILS-001: Basic Loading (Flat structure)
        YAMLのフラットな記述が、IrComponentの構造化された属性(wiring/params)に変換されることを確認
        """
        yaml_str = """
        worker:
          stack_path: root/w1
          # Params (Reserved Key以外はparamsへ)
          agent: GPT-4
          timeout: 30
          # Wiring (inputs/outputはwiringへ)
          inputs: ["DocA"]
          output: "DocB"
        """
        ir = utils.load_ir_from_spec(yaml_str)

        assert isinstance(ir, IrComponent)
        assert ir.opcode == OpCode.WORKER
        assert ir.stack_path == "root/w1"

        # Params Check
        assert ir.params["agent"] == "GPT-4"
        assert ir.params["timeout"] == 30
        assert "inputs" not in ir.params

        # Wiring Check
        assert ir.wiring is not None
        assert ir.wiring.inputs == ["DocA"]
        assert ir.wiring.output == "DocB"

    def test_load_ir_from_spec_recursive(self):
        """
        TC-UTILS-002: Recursive Loading (Children & Contents)
        ネストされた構造が正しくオブジェクトツリーに変換されることを確認
        """
        yaml_str = """
        serial:
          stack_path: root
          children:
            - loop:
                stack_path: root/loop
                count: 3
                contents:
                  worker:
                    stack_path: root/loop/inner
                    output: "Result"
        """
        root = utils.load_ir_from_spec(yaml_str)

        # Level 1: Serial
        assert root.opcode == OpCode.SERIAL
        assert len(root.children) == 1

        # Level 2: Loop
        loop_node = root.children[0]
        assert loop_node.opcode == OpCode.LOOP
        assert loop_node.params["count"] == 3
        assert loop_node.contents is not None

        # Level 3: Worker (Inside Contents)
        inner = loop_node.contents
        assert inner.opcode == OpCode.WORKER
        assert inner.wiring.output == "Result"

    def test_dump_ir_to_spec_basic(self):
        """
        TC-UTILS-003: Basic Dumping
        IrComponentオブジェクトがSpec形式のYAML辞書構造にフラット化されることを確認
        """
        ir = IrComponent(
            stack_path="root/task",
            opcode=OpCode.WORKER,
            params={"model": "v1", "temp": 0.7},
            wiring=WiringObject(inputs=["In"], output="Out")
        )

        # 文字列としてダンプ
        dumped_str = utils.dump_ir_to_spec(ir)
        # 検証のためにパースして戻す
        data = yaml.safe_load(dumped_str)

        assert "worker" in data
        body = data["worker"]
        
        # フラット化の確認
        assert body["stack_path"] == "root/task"
        assert body["model"] == "v1"
        assert body["inputs"] == ["In"]
        assert body["output"] == "Out"
        # ネストされたキーが存在しないこと
        assert "params" not in body
        assert "wiring" not in body

    def test_case_131_round_trip(self):
        """
        TC-UTILS-004: Case 1_3_1 Round Trip
        generate_team (expansion_ir) の実データを用いた往路・復路の検証
        """
        # Case 1_3_1 の expansion_ir (YAML)
        spec_yaml = """
        serial:
          stack_path: root
          children:
            - loop:
                stack_path: root/loop_0
                count: 3
                break_on: success
                contents:
                  serial:
                    stack_path: root/loop_0/v{$LOOP}/serial_0
                    children:
                      - worker:
                          stack_path: root/loop_0/v{$LOOP}/serial_0/worker_0
                          agent: ProjectArchitect
                          mode: generate
                          inputs: 
                            - 全社規定:Rules01@stable
                            - 市場レポート:Mkt05@latest
                            - プロジェクト定義書#default/v{$LOOP-1}
                            - プロジェクト定義書__Review_SecuritySpecialist#default/v{$LOOP-1}
                          output: プロジェクト定義書#default/v{$LOOP}
                      - parallel:
                          stack_path: root/loop_0/v{$LOOP}/serial_0/parallel_1
                          children:
                            - worker:
                                stack_path: root/loop_0/v{$LOOP}/serial_0/parallel_1/worker_0
                                agent: SecuritySpecialist
                                mode: validate
                                inputs:
                                  - 全社規定:Rules01@stable
                                  - 市場レポート:Mkt05@latest
                                  - プロジェクト定義書#default/v{$LOOP}
                                output: プロジェクト定義書__Review_SecuritySpecialist#default/v{$LOOP}
            - scope_resolve:
                stack_path: root/scope_resolve_1
                target: プロジェクト定義書
                from_scope: loop
                strategy: take_latest_success
                map_to: プロジェクト定義書#default
        """

        # -----------------------------------------------------
        # 1. 往路テスト (Load: YAML Spec -> IrComponent)
        # -----------------------------------------------------
        ir_root = utils.load_ir_from_spec(spec_yaml)

        # 構造チェック
        assert ir_root.opcode == OpCode.SERIAL
        assert ir_root.stack_path == "root"
        assert len(ir_root.children) == 2

        # Loop部分のチェック
        loop_node = ir_root.children[0]
        assert loop_node.opcode == OpCode.LOOP
        assert loop_node.params["break_on"] == "success"
        
        # 最深部のWorkerチェック (generate)
        inner_serial = loop_node.contents
        generator = inner_serial.children[0]
        assert generator.opcode == OpCode.WORKER
        assert generator.params["agent"] == "ProjectArchitect"
        # inputsの数と内容
        assert len(generator.wiring.inputs) == 4
        assert "全社規定:Rules01@stable" in generator.wiring.inputs

        # -----------------------------------------------------
        # 2. 復路テスト (Dump: IrComponent -> YAML Spec)
        # -----------------------------------------------------
        dumped_yaml = utils.dump_ir_to_spec(ir_root)

        # 文字列比較ではなく、辞書構造として一致するか確認 (フォーマット差分吸収のため)
        original_dict = yaml.safe_load(spec_yaml)
        dumped_dict = yaml.safe_load(dumped_yaml)

        # デバッグ: 不一致の場合は詳細を表示
        if original_dict != dumped_dict:
             import json
             print("Original:", json.dumps(original_dict, ensure_ascii=False))
             print("Dumped:  ", json.dumps(dumped_dict, ensure_ascii=False))

        assert original_dict == dumped_dict

    def test_error_handling(self):
        """
        TC-UTILS-005: Error Handling
        不正な入力に対する挙動確認
        """
        # Case 1: Empty
        with pytest.raises(ValueError, match="Empty YAML"):
            utils.load_ir_from_spec("")

        # Case 2: Missing stack_path
        invalid_node = "worker: {agent: A}"
        with pytest.raises(ValueError, match="Missing 'stack_path'"):
            utils.load_ir_from_spec(invalid_node)

        # Case 3: Invalid Root (Two keys)
        invalid_root = """
        worker1: {stack_path: a}
        worker2: {stack_path: b}
        """
        with pytest.raises(ValueError, match="single opcode key"):
            utils.load_ir_from_spec(invalid_root)