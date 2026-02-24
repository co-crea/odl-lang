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

import copy
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from odl.types import OpCode, NodeField, REVIEW_ARTIFACT_INFIX
from ..exceptions import OdlCompilationError

# =========================================================
# Constants
# =========================================================
PHYSICAL_ID_MARKER = "#"
DYNAMIC_VAR_MARKER = "$"
EXTERNAL_REF_MARKER = ":"

# =========================================================
# Helper Functions
# =========================================================
def _shift_loop_var_depth(text: str) -> str:
    """
    文字列内の $LOOP 変数の深度を1つ深くする（親スコープ参照用）。
    $LOOP -> $LOOP^1
    $LOOP^1 -> $LOOP^2
    """
    if DYNAMIC_VAR_MARKER not in text:
        return text
        
    def replacer(match):
        current_depth = int(match.group(1)) if match.group(1) else 0
        return f"$LOOP^{current_depth + 1}"

    return re.sub(r'\$LOOP(?:\^(\d+))?', replacer, text)

def _unshift_loop_var_depth(text: str) -> str:
    """
    文字列内の $LOOP 変数の深度を1つ浅くする（子スコープからの戻し用）。
    $LOOP^1 -> $LOOP
    $LOOP^2 -> $LOOP^1
    $LOOP -> $LOOP (これ以上浅くできない場合はそのまま、または本来エラーだが許容)
    """
    if DYNAMIC_VAR_MARKER not in text:
        return text

    def replacer(match):
        current_depth = int(match.group(1)) if match.group(1) else 0
        if current_depth <= 0:
            return match.group(0) # Cannot unshift $LOOP
        if current_depth == 1:
            return "$LOOP"
        return f"$LOOP^{current_depth - 1}"

    return re.sub(r'\$LOOP(?:\^(\d+))?', replacer, text)

# =========================================================
# Scope Management
# =========================================================
class Scope:
    def __init__(self, parent: Optional['Scope'] = None, is_loop_scope: bool = False):
        self.parent = parent
        self.outputs: Dict[str, List[str]] = {}
        self.is_loop_scope = is_loop_scope

    def register(self, name: str, physical_ids: List[str]) -> None:
        if name not in self.outputs:
            self.outputs[name] = []
        self.outputs[name].extend(physical_ids)

    def resolve(self, name: str) -> Optional[List[str]]:
        # 1. Current Scope
        if name in self.outputs:
            return self.outputs[name]
            
        # 2. Parent Scope (Recursive)
        if self.parent:
            parent_ids = self.parent.resolve(name)
            if parent_ids:
                # 自身がループ境界である場合のみ、親からのIDの深度をシフトする
                if self.is_loop_scope:
                    return [_shift_loop_var_depth(pid) for pid in parent_ids]
                else:
                    return parent_ids
                
        return None

# =========================================================
# Main Logic
# =========================================================
def resolve(node: Dict[str, Any]) -> Dict[str, Any]:
    root_scope = Scope(is_loop_scope=False)
    resolved_node = copy.deepcopy(node)
    
    _process_node(resolved_node, root_scope)
    
    return resolved_node


def _process_node(node: Dict[str, Any], current_scope: Scope) -> Tuple[List[str], Set[str]]:
    opcode = node.get(NodeField.OPCODE)
    
    resolved_inputs = _resolve_inputs_and_return(node, current_scope)
    consumed_externals = set(resolved_inputs)

    if opcode == OpCode.ITERATOR_INIT:
        _resolve_iterator_source(node, current_scope)

    produced_outputs: List[str] = []

    if opcode == OpCode.SERIAL:
        # Serialはループ境界ではない
        inner_scope = Scope(parent=current_scope, is_loop_scope=False)
        inner_produced_accumulated: List[str] = []
        block_externals = set()

        if NodeField.CHILDREN in node:
            for child in node[NodeField.CHILDREN]:
                child_produced, child_externals = _process_node(child, inner_scope)
                
                if _is_gate_approver(child):
                    _inject_gate_inputs(child, block_externals, inner_produced_accumulated)
                
                true_externals = child_externals - set(inner_produced_accumulated)
                block_externals.update(true_externals)
                
                _register_outputs_to_scope(child_produced, inner_scope)
                inner_produced_accumulated.extend(child_produced)

        produced_outputs = inner_produced_accumulated
        consumed_externals = block_externals 
        consumed_externals.update(resolved_inputs)
        
        produced_outputs = [pid for pid in produced_outputs if not _is_private_id(pid)]

    elif opcode == OpCode.LOOP or opcode == OpCode.ITERATE:
        # Loop/Iterateはループ境界
        inner_scope = Scope(parent=current_scope, is_loop_scope=True)
        block_externals = set()
        
        if NodeField.CONTENTS in node:
            child_produced, child_externals = _process_node(node[NodeField.CONTENTS], inner_scope)
            
            # Loop内から外への依存IDは、Loop境界を出る際に深度を戻す（Unshift）
            unshifted_externals = {
                _unshift_loop_var_depth(ext) for ext in child_externals
            }
            block_externals.update(unshifted_externals)

        consumed_externals.update(block_externals)

    elif opcode == OpCode.PARALLEL:
        # Parallelはループ境界ではない
        block_externals = set()
        if NodeField.CHILDREN in node:
            for child in node[NodeField.CHILDREN]:
                child_produced, child_externals = _process_node(child, current_scope)
                produced_outputs.extend(child_produced)
                block_externals.update(child_externals)
        consumed_externals.update(block_externals)

    else:
        my_output = _get_declared_output(node)
        if my_output:
            produced_outputs.append(my_output)

    if produced_outputs:
        consumed_externals = consumed_externals - set(produced_outputs)

    return produced_outputs, consumed_externals


def _is_private_id(physical_id: str) -> bool:
    parts = physical_id.split(PHYSICAL_ID_MARKER)
    if not parts: return False
    local_name = parts[0]
    return local_name.startswith("_") and not local_name.startswith("__")


def _normalize_and_resolve_single_ref(ref: str, scope: Scope) -> List[str]:
    if DYNAMIC_VAR_MARKER in ref:
        return [ref]
    
    if EXTERNAL_REF_MARKER in ref:
        if "@" not in ref:
            return [f"{ref}@stable"]
        return [ref]

    # Explicit ID (#付き) の特別解決ロジック
    if PHYSICAL_ID_MARKER in ref:
        parts = ref.split(PHYSICAL_ID_MARKER, 1)
        local_name = parts[0]
        
        candidates = scope.resolve(local_name)
        if candidates:
            # ref と前方一致する物理IDを探す (e.g. "Doc#v1" matches "Doc#v1/v{$LOOP}")
            matched = [
                c for c in candidates 
                if c == ref or c.startswith(ref + "/")
            ]
            if matched:
                return matched
        
        return [ref]

    found_ids = scope.resolve(ref)
    if found_ids:
        return found_ids
    
    return [ref]


def _resolve_inputs_and_return(node: Dict[str, Any], scope: Scope) -> List[str]:
    wiring = node.get(NodeField.WIRING)
    if not wiring or NodeField.INPUTS not in wiring:
        return []
    
    resolved_inputs: List[str] = []
    for ref in wiring[NodeField.INPUTS]:
        resolved_list = _normalize_and_resolve_single_ref(ref, scope)
        resolved_inputs.extend(resolved_list)
    
    wiring[NodeField.INPUTS] = resolved_inputs
    return resolved_inputs


def _resolve_iterator_source(node: Dict[str, Any], scope: Scope) -> None:
    params = node.get(NodeField.PARAMS)
    if not params: return
    source = params.get("source")
    if not source or not isinstance(source, str):
        return
    resolved_list = _normalize_and_resolve_single_ref(source, scope)
    if resolved_list:
        params["source"] = resolved_list[-1]


def _register_outputs_to_scope(physical_ids: List[str], scope: Scope) -> None:
    if not physical_ids:
        return
    grouped: Dict[str, List[str]] = defaultdict(list)
    for pid in physical_ids:
        parts = pid.split(PHYSICAL_ID_MARKER)
        if len(parts) >= 2:
            local_name = parts[0]
            if not local_name.startswith("__"):
                grouped[local_name].append(pid)
    for name, ids in grouped.items():
        scope.register(name, ids)


def _get_declared_output(node: Dict[str, Any]) -> Optional[str]:
    wiring = node.get(NodeField.WIRING, {})
    output = wiring.get(NodeField.OUTPUT)
    if output:
        return output
    if node.get(NodeField.OPCODE) == OpCode.SCOPE_RESOLVE:
        return node.get(NodeField.PARAMS, {}).get("map_to")
    return None


def _is_gate_approver(node: Dict[str, Any]) -> bool:
    return node.get(NodeField.OPCODE) == OpCode.APPROVER


def _inject_gate_inputs(node: Dict[str, Any], external_refs: Set[str], internal_audit_trail: List[str]) -> None:
    """
    Approval GateのApprover（Dialogueノード）に対して、
    「内部成果物（Audit Trail）」と「外部入力（External Refs）」を自動的に配線する。
    """
    wiring = node.get(NodeField.WIRING)
    if NodeField.INPUTS not in wiring:
        wiring[NodeField.INPUTS] = []
    
    current_inputs = set(wiring[NodeField.INPUTS])
    
    # 1. External References (外部コンテキストの引き継ぎ)
    for ref in external_refs:
        if _is_private_id(ref): continue

        # $LOOPが含まれるものは、内部的な反復履歴（Context）であり、
        # 静的な外部資料（Reference）ではないため除外する。
        if "$LOOP" in ref:
            continue
        
        is_system_var = DYNAMIC_VAR_MARKER in ref
        is_item = "$ITEM" in ref
        is_key = "$KEY" in ref
        
        if (is_system_var and not is_item and not is_key) or REVIEW_ARTIFACT_INFIX in ref:
                continue

        if ref not in current_inputs:
            wiring[NodeField.INPUTS].append(ref)
            current_inputs.add(ref)

    # 2. Internal Audit Trail (チーム内成果物の全量)
    for pid in internal_audit_trail:
        if pid.startswith("__") or "/__" in pid: continue
        
        if pid not in current_inputs:
            wiring[NodeField.INPUTS].append(pid)
            current_inputs.add(pid)
