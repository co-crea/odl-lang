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

from typing import Any, Set
from odl.types import OpCode, NodeField
from ..exceptions import OdlCompilationError

# 許可されるシステム変数リスト (cocrea-2003準拠)
ALLOWED_SYSTEM_VARS = {"$LOOP", "$KEY", "$PREV", "$HISTORY"}

def validate(node: dict[str, Any]) -> None:
    """
    IDの整合性と参照ルール（Wiring Rules）を検証する。
    """
    
    seen_node_ids = set()

    def validate_scope(current_node: dict[str, Any], visible_artifacts: Set[str]) -> Set[str]:
        """
        現在のノードとその子孫を検証し、このノードによって新たに生成（可視化）されるOutput IDのセットを返す。
        """
        node_id = current_node.get(NodeField.STACK_PATH)
        if node_id:
            if node_id in seen_node_ids:
                raise OdlCompilationError(f"Duplicate ID found: {node_id}", stage="WiringRule")
            seen_node_ids.add(node_id)

        opcode = current_node.get(NodeField.OPCODE)
        wiring = current_node.get(NodeField.WIRING, {})
        inputs = wiring.get(NodeField.INPUTS, [])
        output = wiring.get(NodeField.OUTPUT)
        params = current_node.get(NodeField.PARAMS, {})

        # 1. Input Reference Check
        for ref_id in inputs:
            # 外部参照はスキップ
            if ":" in ref_id:
                continue
            
            # 動的変数の検証
            if "$" in ref_id:
                # 修正箇所: 文字列の中に ALLOWED_SYSTEM_VARS (例: {$KEY}) が含まれているか判定
                # これにより "会員情報.{$KEY}" のような形式も動的変数として許容される
                is_valid_var = any(v in ref_id for v in ALLOWED_SYSTEM_VARS)
                
                if not is_valid_var:
                     raise OdlCompilationError(
                        f"Invalid system variable usage in '{ref_id}'. "
                        f"Allowed variables must include one of: {sorted(list(ALLOWED_SYSTEM_VARS))}",
                        stage="WiringRule"
                    )
                # 有効な動的変数の場合は、解決不能なため静的チェックをスキップ (Soft Binding)
                continue
            
            if ref_id not in visible_artifacts:
                raise OdlCompilationError(
                    f"Undefined Artifact ID referenced: '{ref_id}'. "
                    f"It may be undefined, or a forward reference (future sibling). "
                    f"Visible artifacts: {sorted(list(visible_artifacts))}",
                    stage="WiringRule"
                )

        # 2. Collect Produced Output
        produced_here = set()
        
        # Case A: Standard Output (Worker, etc.)
        if output:
            produced_here.add(_construct_physical_id(output, node_id))

        # Case B: Scope Resolution Output (scope_resolve)
        # scope_resolveは 'map_to' で指定されたIDを外部へ公開する
        if opcode == OpCode.SCOPE_RESOLVE:
            map_to = current_node.get("map_to") or params.get("map_to")
            if map_to:
                produced_here.add(_construct_physical_id(map_to, node_id))

        # 3. Recursive Scope Processing
        children = current_node.get(NodeField.CHILDREN, [])
        contents = current_node.get(NodeField.CONTENTS)

        if opcode == OpCode.SERIAL:
            current_scope = visible_artifacts.copy()
            block_produced = set()
            
            for child in children:
                child_produced = validate_scope(child, current_scope)
                current_scope.update(child_produced)
                block_produced.update(child_produced)
            
            produced_here.update(block_produced)

        elif opcode == OpCode.PARALLEL:
            block_produced = set()
            for child in children:
                # 兄弟間の成果物は見えない
                child_produced = validate_scope(child, visible_artifacts)
                block_produced.update(child_produced)
            produced_here.update(block_produced)

        elif contents:
            child_produced = validate_scope(contents, visible_artifacts)
            produced_here.update(child_produced)
        
        elif children:
            current_scope = visible_artifacts.copy()
            for child in children:
                child_produced = validate_scope(child, current_scope)
                current_scope.update(child_produced)
                produced_here.update(child_produced)

        return produced_here

    validate_scope(node, set())

def _construct_physical_id(logical_name: str, node_id: str | None) -> str:
    """物理IDの再構築ロジック"""
    if "#" in logical_name:
        return logical_name
    elif node_id:
        return f"{logical_name}#{node_id}"
    else:
        return logical_name