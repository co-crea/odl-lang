import pytest
import yaml
import traceback
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# [Migration] 公開API (Facade) を使用
import odl
from odl.types import IrComponent, OpCode
from odl.compiler.exceptions import OdlCompilationError

# =========================================================
# 1. Helpers & Adapters
# =========================================================

def load_cases_from_directory(target_dir_name: str) -> List[Dict[str, Any]]:
    """
    specsディレクトリからテストケース(YAML)を読み込む
    """
    base_dir = Path(__file__).parent / "specs" / target_dir_name
    if not base_dir.exists():
        return []

    test_cases = []
    for file_path in sorted(base_dir.glob("*.yml")) + sorted(base_dir.glob("*.yaml")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data: continue

            pac_code = data.get("pac_code", file_path.stem)
            cases = data.get("case", [])
            
            for case in cases:
                test_cases.append({
                    "file": file_path.name,
                    "pac_code": pac_code,
                    "id": case.get("id", "unknown"),
                    "description": case.get("description", ""),
                    "source_syntax": case.get("source_syntax"),
                    "expansion_ir": case.get("expansion_ir"),
                    "expected_error": case.get("expected_error")
                })
        except Exception as e:
            print(f"Warning: Failed to load spec file {file_path}: {e}")
    return test_cases

def convert_ir_to_spec_style(ir: IrComponent) -> Any:
    """
    IrComponentオブジェクトを、テスト仕様書(Spec)の辞書形式に変換するアダプタ。
    """
    opcode_str = str(ir.opcode.value) if hasattr(ir.opcode, 'value') else str(ir.opcode)
    value_dict = {}
    
    if not getattr(ir, "stack_path", None):
        raise AssertionError(f"Mandatory field 'stack_path' is missing or empty in node: {opcode_str}")

    value_dict["stack_path"] = ir.stack_path

    if ir.params:
        value_dict.update(ir.params)
        
    if ir.wiring:
        if ir.wiring.inputs: 
            value_dict["inputs"] = sorted(ir.wiring.inputs)
        if ir.wiring.output: 
            value_dict["output"] = ir.wiring.output
    
    # 2. 子供の変換
    if ir.children:
        converted_children = [convert_ir_to_spec_style(child) for child in ir.children]
        
        # === 修正箇所: 配列にするかオブジェクトにするかの分岐判定 ===
        is_container_op = opcode_str in ["serial", "parallel"]
        has_metadata = len(value_dict) > 0  # stack_pathやparamsがあるか？

        if is_container_op and not has_metadata:
            # メタデータが無いなら、従来通りの「省略記法（配列）」を返す
            return {opcode_str: converted_children}
        
        # メタデータがあるなら、「明示的記法（childrenキーを持つオブジェクト）」にする
        value_dict["children"] = converted_children

    if ir.contents:
        value_dict["contents"] = convert_ir_to_spec_style(ir.contents)

    return {opcode_str: value_dict}

def normalize_expected_data(data: Any) -> Any:
    """
    YAMLから読み込んだ期待値データ内の `inputs` リストを再帰的にソートする。
    """
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if k == "inputs" and isinstance(v, list):
                if all(isinstance(i, str) for i in v):
                    new_data[k] = sorted(v)
                else:
                    new_data[k] = v
            else:
                new_data[k] = normalize_expected_data(v)
        return new_data
    elif isinstance(data, list):
        return [normalize_expected_data(item) for item in data]
    else:
        return data

# =========================================================
# 2. Logging & Artifact Helpers
# =========================================================

def _dump_failure_log(
    case_data: Dict[str, Any], 
    error: Exception, 
    actual_ir: Optional[Any] = None
):
    """
    テスト失敗時に詳細なレポートを logs ディレクトリに出力する
    """
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    safe_id = str(case_data['id']).replace("/", "_")
    log_file = log_dir / f"FAIL_{case_data['pac_code']}_{safe_id}.log"

    content = []
    content.append(f"=== TEST FAILURE REPORT: {case_data['pac_code']} :: {case_data['id']} ===")
    content.append(f"File: {case_data['file']}")
    content.append(f"Description:\n{case_data['description']}")
    content.append("\n" + "="*40)
    
    content.append("\n[SOURCE YAML]")
    source_str = yaml.dump(case_data["source_syntax"], allow_unicode=True, default_flow_style=False)
    content.append(source_str)

    content.append("\n" + "="*40)
    content.append("\n[EXPECTED IR (Spec)]")
    expected_str = yaml.dump(case_data["expansion_ir"], allow_unicode=True, default_flow_style=False)
    content.append(expected_str)

    content.append("\n" + "="*40)
    content.append("\n[ACTUAL IR (Converted)]")
    if actual_ir:
        try:
            actual_str = yaml.dump(actual_ir, allow_unicode=True, default_flow_style=False)
            content.append(actual_str)
        except Exception:
            content.append(str(actual_ir))
    else:
        content.append("(Not generated due to compilation error)")

    content.append("\n" + "="*40)

    content.append("\n[ERROR DETAILS]")
    content.append(f"Error Type: {type(error).__name__}")
    content.append(f"Message: {str(error)}")
    content.append("\nTraceback:")
    content.append(traceback.format_exc())

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

def _dump_artifact(
    case_data: Dict[str, Any], 
    ir_root: IrComponent
):
    """
    【NEW】テスト成功時に、実際に生成されたIrComponentの完全なJSONをファイルに出力する。
    これにより、L3エンジンへの入力データ構造（事実）を可視化・確定させる。
    """
    # 出力先: tests/integration/artifacts/
    artifact_dir = Path(__file__).parent / "artifacts"
    artifact_dir.mkdir(exist_ok=True)

    safe_id = str(case_data['id']).replace("/", "_")
    # ファイル名: cocrea.5120_TC-001.json
    filename = f"{case_data['pac_code']}_{safe_id}.log"
    target_file = artifact_dir / filename

    try:
        # PydanticモデルをJSONシリアライズ
        # exclude_none=True: 不要なnullフィールドを排除して見やすくする
        json_content = ir_root.model_dump_json(indent=2, exclude_none=True)
        
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(json_content)
            
    except Exception as e:
        print(f"Warning: Failed to dump artifact for {case_data['id']}: {e}")

# =========================================================
# 3. Test Classes
# =========================================================

class TestCompilerIntegration:
    """
    Master ODL (cocrea-5xxx) を用いた統合テスト。
    ライブラリの公開インターフェース (odl.compile) を通じて仕様適合性を検証する。
    """
    
    success_cases = load_cases_from_directory("success")
    error_cases = load_cases_from_directory("error")

    def _to_yaml_string(self, source_data: Any) -> str:
        if isinstance(source_data, dict) or isinstance(source_data, list):
            return yaml.dump(source_data, allow_unicode=True)
        return str(source_data)

    def _assert_structure_subset(self, expected: Any, actual: Any, path: str = ""):
        """構造的部分一致（Subset Match）を検証するヘルパー"""

        # === 追加: stack_path 限定の厳密チェック ===
        # Actual(コンパイラ出力)に stack_path があるのに、Expected(YAML)に書いていない場合はNGとする
        if isinstance(actual, dict) and "stack_path" in actual:
            if isinstance(expected, dict) and "stack_path" not in expected:
                raise AssertionError(
                    f"Strict check failed at '{path}': "
                    f"Actual result has 'stack_path' ('{actual['stack_path']}'), "
                    "but it is missing in Expected YAML. Please define it."
                )
        # ===========================================

        if isinstance(expected, dict):
            assert isinstance(actual, dict), f"Type mismatch at {path}: expected dict, got {type(actual)}"
            for k, v in expected.items():
                assert k in actual, f"Missing key '{k}' in actual output at {path}"
                self._assert_structure_subset(v, actual[k], path=f"{path}.{k}")
        elif isinstance(expected, list):
            assert isinstance(actual, list), f"Type mismatch at {path}: expected list, got {type(actual)}"
            assert len(actual) >= len(expected), f"List length mismatch at {path}: expected {len(expected)}, got {len(actual)}"
            for i, item in enumerate(expected):
                self._assert_structure_subset(item, actual[i], path=f"{path}[{i}]")
        else:
            assert expected == actual, f"Value mismatch at {path}: expected {expected}, got {actual}"

    @pytest.mark.parametrize("case_data", success_cases, ids=lambda c: f"{c['pac_code']}::{c['id']}")
    def test_compilation_success(self, case_data):
        """正常系テスト (With Success Artifact Dump)"""
        source = self._to_yaml_string(case_data["source_syntax"])
        expected_spec_ir = normalize_expected_data(case_data["expansion_ir"])
        
        actual_spec_style = None

        try:
            # 1. Compile
            actual_ir_obj = odl.compile(source)

            if actual_ir_obj:
                _dump_artifact(case_data, actual_ir_obj)
            
            # 2. Convert for Comparison
            actual_spec_style = convert_ir_to_spec_style(actual_ir_obj)
            
            # 3. Compare (Validation)
            self._assert_structure_subset(expected_spec_ir, actual_spec_style)

        except Exception as e:
            _dump_failure_log(case_data, e, actual_spec_style)
            raise e

    @pytest.mark.parametrize("case_data", error_cases, ids=lambda c: f"{c['pac_code']}::{c['id']}")
    def test_compilation_error(self, case_data):
        """異常系テスト"""
        source = self._to_yaml_string(case_data["source_syntax"])
        expected_error_msg = case_data.get("expected_error")

        try:
            with pytest.raises(OdlCompilationError) as exc_info:
                odl.compile(source)
            
            if expected_error_msg:
                assert expected_error_msg in str(exc_info.value)

        except Exception as e:
            _dump_failure_log(case_data, e)
            raise e