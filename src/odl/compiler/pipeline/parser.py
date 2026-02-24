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
import copy
from typing import Any, Dict, List
from odl.types import NodeField
from ..exceptions import OdlCompilationError

# 構造維持すべきキー（これ以外は params/wiring に移動する）
STRUCTURAL_KEYS = {
    NodeField.STACK_PATH,
    NodeField.OPCODE,
    NodeField.CHILDREN,
    NodeField.CONTENTS,
    NodeField.DESCRIPTION,
    NodeField.PARAMS,
    NodeField.WIRING
}

# Wiringブロックに移動すべきキー
WIRING_KEYS = {
    NodeField.INPUTS,
    NodeField.OUTPUT
}

def parse(source: str) -> dict[str, Any]:
    """
    YAML形式のODLソースコードをパースし、IR形式（params/wiring分離）に正規化された辞書に変換する。
    """
    try:
        data = yaml.safe_load(source)
    except yaml.YAMLError as e:
        raise OdlCompilationError(f"YAML syntax error: {str(e)}", stage="Parser") from e

    if data is None:
        raise OdlCompilationError("Empty ODL source", stage="Parser")
    
    if not isinstance(data, dict):
        raise OdlCompilationError(
            f"Invalid ODL structure: Root must be a dictionary, got {type(data).__name__}",
            stage="Parser"
        )

    # 再帰的な正規化と構造化
    normalized_data = _normalize_recursive(data)

    if NodeField.OPCODE not in normalized_data:
        keys = list(normalized_data.keys())
        raise OdlCompilationError(
            f"Invalid ODL structure: Missing '{NodeField.OPCODE}' field. Found keys: {keys}",
            stage="Parser"
        )

    return normalized_data


def _normalize_recursive(data: Any) -> Any:
    """
    辞書やリストを再帰的に探索し、ODLノード構造を正規化（OpCode解決 + フィールド構造化）する。
    """
    if isinstance(data, list):
        return [_normalize_recursive(item) for item in data]

    if isinstance(data, dict):
        new_node = None

        # Case A: 既に opcode を持っている場合
        if NodeField.OPCODE in data:
            new_node = data.copy()

        # Case B: 単一キーで、そのキーがOpCodeと推測される場合
        elif len(data) == 1:
            opcode_key = next(iter(data))
            body = data[opcode_key]
            
            # Case B-1: List Body -> children
            if isinstance(body, list):
                new_node = {
                    NodeField.OPCODE: opcode_key,
                    NodeField.CHILDREN: body
                }
            # Case B-2: Dict Body -> merge
            elif isinstance(body, dict):
                new_node = body.copy()
                new_node[NodeField.OPCODE] = opcode_key
            # Case B-3: None
            elif body is None:
                new_node = {NodeField.OPCODE: opcode_key}
            # Case B-4: Primitive -> params (short syntax)
            else:
                new_node = {
                    NodeField.OPCODE: opcode_key,
                    NodeField.PARAMS: body # 暫定
                }
        
        # Case C: 複数キーでopcodeなし (Parameter Dictの可能性)
        else:
            return data

        # 構造が決まったら、中身を再帰的に処理
        if NodeField.CHILDREN in new_node:
            new_node[NodeField.CHILDREN] = _normalize_recursive(new_node[NodeField.CHILDREN])
        if NodeField.CONTENTS in new_node:
            new_node[NodeField.CONTENTS] = _normalize_recursive(new_node[NodeField.CONTENTS])
            
        # 最後にフィールドを params/wiring に振り分ける
        return _restructure_fields(new_node)

    return data


def _restructure_fields(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    フラットな辞書を params / wiring 構造に変換する。
    例: { "agent": "A", "inputs": [] } -> { "params": {"agent": "A"}, "wiring": {"inputs": []} }
    """
    # 既存のコンテナを取得（なければ作成）
    params = node.get(NodeField.PARAMS, {})
    wiring = node.get(NodeField.WIRING, {})
    
    keys_to_move = []
    
    for key, value in node.items():
        if key in STRUCTURAL_KEYS:
            continue
            
        if key in WIRING_KEYS:
            wiring[key] = value
            keys_to_move.append(key)
        else:
            # それ以外は全て params へ (agent, source, strategy, count, etc.)
            params[key] = value
            keys_to_move.append(key)
            
    # 移動したキーを削除
    for key in keys_to_move:
        del node[key]
        
    # コンテナをノードに戻す
    if params:
        node[NodeField.PARAMS] = params
    if wiring:
        node[NodeField.WIRING] = wiring
        
    return node