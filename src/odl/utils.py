# Copyright (c) 2026 Centillion System, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import yaml
from typing import Any, Dict, Union, Tuple, Optional

from odl.types import IrComponent, WiringObject, OpCode, NodeField, REVIEW_ARTIFACT_INFIX


# Spec形式のYAMLにおける予約キー（これ以外はparamsとみなす）
SPEC_RESERVED_KEYS = {
    "stack_path", "children", "contents", "inputs", "output", "description"
}

def is_review_artifact(artifact_id: str) -> bool:
    """
    指定されたアーティファクトIDが、ODLの命名規則における「レビュー文書」かどうかを判定する。
    Host側でアイコンを出し分けたり、処理を分岐したりするために使用する。
    
    Args:
        artifact_id: 物理ID ("Doc__Review_Boss#v1") または 論理ID ("Doc__Review_Boss")
    """
    if not artifact_id:
        return False
        
    # 物理IDのサフィックス (#以降) を除去して論理名だけで判定する
    logical_name = artifact_id.split("#")[0]
    
    return REVIEW_ARTIFACT_INFIX in logical_name

def parse_review_artifact(artifact_id: str) -> Optional[Tuple[str, str]]:
    """
    レビュー文書IDから「対象文書名」と「レビュアー名」を抽出するヘルパー。
    
    Returns:
        (target_doc, reviewer_agent)
    """
    logical_name = artifact_id.split("#")[0]
    
    if REVIEW_ARTIFACT_INFIX not in logical_name:
        return None
        
    parts = logical_name.split(REVIEW_ARTIFACT_INFIX, 1)
    if len(parts) != 2:
        return None
        
    return (parts[0], parts[1])

def load_ir_from_spec(yaml_str: str) -> IrComponent:
    """
    テスト仕様書（Spec）形式のYAML文字列を、IrComponentオブジェクトに変換します。

    Args:
        yaml_str (str): expansion_ir に相当するYAML文字列
                        例: "serial:\n  stack_path: root\n  ..."

    Returns:
        IrComponent: 構築されたIRルートオブジェクト
    """
    data = yaml.safe_load(yaml_str)
    if not data:
        raise ValueError("Empty YAML string provided")
    
    # ルートがリスト形式の定義（- serial: ...）の場合と、辞書形式の場合に対応
    if isinstance(data, list):
        if len(data) != 1:
            raise ValueError("Root YAML list must contain exactly one element")
        data = data[0]

    return _dict_to_ir_recursive(data)


def dump_ir_to_spec(ir: IrComponent) -> str:
    """
    IrComponentオブジェクトを、テスト仕様書（Spec）形式のYAML文字列に変換します。

    Args:
        ir (IrComponent): 変換元のIRオブジェクト

    Returns:
        str: expansion_ir 形式のYAML文字列
    """
    spec_dict = _ir_to_dict_recursive(ir)
    
    # allow_unicode=True: 日本語をそのまま出力
    # sort_keys=False: 辞書作成順（stack_path先頭など）を維持
    return yaml.dump(spec_dict, allow_unicode=True, sort_keys=False, default_flow_style=False)


# --- Internal Converters ---

def _dict_to_ir_recursive(data: Dict[str, Any]) -> IrComponent:
    """
    辞書（{opcode: body}形式）からIrComponentへの再帰的変換
    """
    # Key（OpCode）とBodyの分離
    # 例: {"serial": {"stack_path": "root", ...}}
    if len(data) != 1:
         raise ValueError(f"Invalid node structure. Expected single opcode key, got: {list(data.keys())}")
    
    opcode_str, body = next(iter(data.items()))
    
    # 必須フィールドの抽出
    if "stack_path" not in body:
        raise ValueError(f"Missing 'stack_path' in node '{opcode_str}'")
    
    stack_path = body.get("stack_path")
    
    # 再帰構造の変換
    children = []
    if "children" in body:
        children = [_dict_to_ir_recursive(c) for c in body["children"]]
        
    contents = None
    if "contents" in body:
        contents = _dict_to_ir_recursive(body["contents"])

    # Wiringの構築 (inputs/output を wiring オブジェクトへ)
    inputs = body.get("inputs", [])
    output = body.get("output")
    wiring = None
    if inputs or output:
        wiring = WiringObject(inputs=inputs, output=output)

    # Paramsの抽出 (予約キー以外はすべてparamsへ)
    params = {}
    for k, v in body.items():
        if k not in SPEC_RESERVED_KEYS:
            params[k] = v

    return IrComponent(
        stack_path=stack_path,
        opcode=opcode_str, # PydanticがStrEnumへの変換を処理
        wiring=wiring,
        params=params,
        children=children,
        contents=contents
    )


def _ir_to_dict_recursive(ir: IrComponent) -> Dict[str, Any]:
    """
    IrComponentから辞書（{opcode: body}形式）への再帰的変換
    """
    # OpCodeを文字列化
    opcode_str = ir.opcode.value

    # Bodyの構築（表示順序を意識して格納）
    body = {}
    
    # 1. Identity
    body["stack_path"] = ir.stack_path
    
    # 2. Params (Flatten)
    if ir.params:
        body.update(ir.params)
    
    # 3. Wiring (Flatten)
    if ir.wiring:
        # 空リスト/Noneは出力しないなど、きれいなYAMLにするための調整
        if ir.wiring.inputs:
            # ソートはせず、元の順序を維持する (Round Tripの一貫性のため)
            body["inputs"] = ir.wiring.inputs
        if ir.wiring.output:
            body["output"] = ir.wiring.output
            
    # 4. Recursion
    if ir.children:
        body["children"] = [_ir_to_dict_recursive(c) for c in ir.children]
        
    if ir.contents:
        body["contents"] = _ir_to_dict_recursive(ir.contents)

    return {opcode_str: body}