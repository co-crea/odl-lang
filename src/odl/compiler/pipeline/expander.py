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
from typing import Any, List, Dict, Optional, Tuple

from odl.types import OpCode, NodeField, WorkerMode, REVIEW_ARTIFACT_INFIX, KEY_BRIEFING, KEY_ITERATION_BINDING
from ..exceptions import OdlCompilationError

# マッチパターン: (LocalName.)?__key
# Group 1: LocalName (Optional)
# 例: "DocA.__key" -> g1="DocA"
# 例: "__key"      -> g1=None
ITEM_BINDING_PATTERN = re.compile(rf"^(?:(.*)\.)?{KEY_ITERATION_BINDING}$")

def expand(node: Dict[str, Any]) -> Dict[str, Any]:
    # 親パス（Namespace）として "root" を指定し、
    # トップノード自身のIDは OpCode (serial) に基づいて自動生成させる
    initial_scope_id = "default"

    # defined_id=None にすることで、_generate_deterministic_id が走り、
    # root/serial_0 (あるいは root/parallel_0) が生成される
    return _expand_recursive(node, parent_path="root", defined_id=None, output_scope_id=initial_scope_id)

def _expand_recursive(
    node: Dict[str, Any],
    parent_path: str,
    defined_id: Optional[str] = None,
    sibling_index: int = 0,
    output_scope_id: Optional[str] = None
) -> Dict[str, Any]:
    opcode = node.get(NodeField.OPCODE)
    if not opcode:
        raise OdlCompilationError(f"Missing '{NodeField.OPCODE}' field", stage="Expander")

    # =========================================================
    # [FIX] ID生成のための物理OpCode解決
    # Sugar Syntax (ensemble, fan_out等) は、展開されると物理的には
    # "serial" コンテナになるため、IDも "serial_N" とすべきである。
    # =========================================================
    physical_opcode = opcode
    if opcode in ["fan_out", "ensemble", "generate_team", "approval_gate"]:
        physical_opcode = OpCode.SERIAL
    # =========================================================

    if defined_id:
        current_id = defined_id
    else:
        # 修正: opcode ではなく physical_opcode を使用してID生成
        current_id = _generate_deterministic_id(parent_path, physical_opcode, sibling_index)

    current_output_scope = output_scope_id if output_scope_id else current_id

    current_node = copy.deepcopy(node)
    current_node[NodeField.STACK_PATH] = current_id

    # Sugar Syntax Expansion
    # Note: These keys are sugar opcodes, not in the standard OpCode enum
    if opcode == "fan_out":
        return _expand_fan_out(current_node, current_id, current_output_scope)
    elif opcode == "ensemble":
        return _expand_ensemble(current_node, current_id, current_output_scope)
    elif opcode == "generate_team":
        return _expand_generate_team(current_node, current_id, current_output_scope)
    elif opcode == "approval_gate":
        return _expand_approval_gate(current_node, current_id, current_output_scope)
    else:
        return _process_standard_node(current_node, current_id, current_output_scope)


def _generate_deterministic_id(parent_path: str, opcode: str, index: int) -> str:
    separator = "/" if parent_path else ""
    opcode_str = str(opcode).lower()
    return f"{parent_path}{separator}{opcode_str}_{index}"


def _process_standard_node(node: Dict[str, Any], current_id: str, output_scope_id: str) -> Dict[str, Any]:
    _normalize_output(node, output_scope_id)

    if node.get(NodeField.OPCODE) == OpCode.WORKER:
        if NodeField.PARAMS not in node:
            node[NodeField.PARAMS] = {}
        if "mode" not in node[NodeField.PARAMS]:
            node[NodeField.PARAMS]["mode"] = WorkerMode.GENERATE

    child_scope_id = output_scope_id
    # === [FIX START] ID生成用の子パス計算ロジックを追加 ===
    child_stack_path_base = current_id  # デフォルトは現在のIDをそのまま親とする
    # ===================================================

    if node.get(NodeField.OPCODE) == OpCode.LOOP:
        # 配線用スコープIDの更新（既存ロジック）
        child_scope_id = _shift_loop_depth(output_scope_id)
        child_scope_id = _join_path(child_scope_id, "v{$LOOP}")

        # [FIX] ID用パスの更新: Loopの中身は v{$LOOP} 下に配置する
        child_stack_path_base = _join_path(current_id, "v{$LOOP}")

    # Iterate (Fan-out) の対応も同様に追加
    if node.get(NodeField.OPCODE) == OpCode.ITERATE:
        # [FIX] ID用パスの更新: Iterateの中身は {$KEY} 下に配置する
        child_stack_path_base = _join_path(current_id, "{$KEY}")
        # 配線用スコープIDは呼び出し元(_expand_fan_out)で計算済みのためここでは触らない

    if NodeField.CHILDREN in node:
        expanded_children = []
        for i, child in enumerate(node[NodeField.CHILDREN]):
            expanded_child = _expand_recursive(
                child,
                parent_path=current_id, # Childrenはコンテナ直下なので current_id のまま (変更なし)
                sibling_index=i,
                output_scope_id=child_scope_id
            )
            expanded_children.append(expanded_child)
        node[NodeField.CHILDREN] = expanded_children

    if NodeField.CONTENTS in node:
        node[NodeField.CONTENTS] = _expand_recursive(
            node[NodeField.CONTENTS],
            # [FIX] 計算済みのトークン付きパスを渡す
            parent_path=child_stack_path_base,
            sibling_index=0,
            output_scope_id=child_scope_id
        )

    return node


def _normalize_output(node: Dict[str, Any], scope_id: str) -> None:
    wiring = node.get(NodeField.WIRING)
    if wiring and NodeField.OUTPUT in wiring:
        output = wiring[NodeField.OUTPUT]
        if output:
            wiring[NodeField.OUTPUT] = _derive_self_output_id(output, scope_id)


def _replace_variable_placeholders(node: Any, target: str, replacement: str) -> None:
    """
    Inputsリスト内のプレースホルダー変数を置換する。

    Args:
        node: 探索対象のノード（辞書またはリスト）
        target: 置換対象の文字列（例: "__key"）
        replacement: 置換後の文字列（例: "$KEY"）
    """
    if target == KEY_ITERATION_BINDING:
        # fan_out用のItem Bindingは、正規表現による厳密なバインディングを行う
        _replace_item_binding_recursive(node, replacement)
    else:
        # 従来通りの単純文字列置換
        _replace_generic_recursive(node, target, replacement)


def _replace_generic_recursive(node: Any, target: str, replacement: str) -> None:
    """単純な文字列置換を行う再帰関数"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == NodeField.INPUTS and isinstance(value, list):
                node[key] = [v.replace(target, replacement) if isinstance(v, str) else v for v in value]
            else:
                _replace_generic_recursive(value, target, replacement)
    elif isinstance(node, list):
        for item in node:
            _replace_generic_recursive(item, target, replacement)


def _replace_item_binding_recursive(node: Any, replacement: str) -> None:
    """
    __item バインディング専用の置換再帰関数。
    <LocalName>.__item 形式に対応する。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == NodeField.INPUTS and isinstance(value, list):
                new_inputs = []
                for v in value:
                    if isinstance(v, str):
                        # 正規表現でマッチング (Syntaxルールで正当性は検証済みとする)
                        match = ITEM_BINDING_PATTERN.match(v)
                        if match:
                            local_name = match.group(1)
                            if local_name:
                                # Case: <LocalName>.__item -> <LocalName>.$ITEM
                                v = f"{local_name}.{replacement}"
                            else:
                                # Case: __item -> $ITEM
                                v = replacement
                    new_inputs.append(v)
                node[key] = new_inputs
            else:
                _replace_item_binding_recursive(value, replacement)
    elif isinstance(node, list):
        for item in node:
            _replace_item_binding_recursive(item, replacement)


def _stack_id(base: str, suffix: str) -> str:
    if not suffix:
        return base
    if "#" in base:
        return f"{base}/{suffix}"
    return f"{base}#{suffix}"

def _join_path(base: str, suffix: str) -> str:
    if base:
        return f"{base}/{suffix}"
    return suffix

def _derive_self_output_id(output_name: str, scope_id: str) -> str:
    if "#" in output_name:
        suffix_to_add = _strip_default_from_scope(scope_id)
        return _stack_id(output_name, suffix_to_add)
    return f"{output_name}#{scope_id}"

def _extract_logical_name(name: str) -> str:
    if "#" in name:
        return name.split("#", 1)[0]
    return name

def _create_feedback_id(target_doc: str, agent_name: str) -> str:
    if "#" in target_doc:
        local, explicit = target_doc.split("#", 1)
        return f"{local}{REVIEW_ARTIFACT_INFIX}{agent_name}#{explicit}"
    return f"{target_doc}{REVIEW_ARTIFACT_INFIX}{agent_name}"

def _shift_loop_depth(scope_id: str) -> str:
    def replacer(match):
        current_depth = int(match.group(1)) if match.group(1) else 0
        return f"$LOOP^{current_depth + 1}"
    return re.sub(r'\$LOOP(?:\^(\d+))?', replacer, scope_id)

def _strip_default_from_scope(scope_id: str) -> str:
    if scope_id == "default":
        return ""
    if scope_id.startswith("default/"):
        return scope_id[8:]
    return scope_id

def _merge_params(base_briefing: Dict[str, Any], system_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    パラメータのマージ処理。
    ユーザー定義の 'briefing' をベースとし、システムが生成する必須パラメータで上書きする。
    これにより、ユーザーが 'agent' や 'mode' などのシステム変数を意図せず破壊することを防ぐ。
    """
    return {**base_briefing, **system_overrides}


# --- Sugar Expansion Logics ---

def _expand_fan_out(sugar_node: Dict[str, Any], node_id: str, output_scope_id: str) -> Dict[str, Any]:
    params = sugar_node.get(NodeField.PARAMS, {})
    source = sugar_node.get("source") or params.get("source")
    item_key = sugar_node.get("item_key") or params.get("item_key")
    strategy = sugar_node.get("strategy") or params.get("strategy") or "serial"
    inner_contents = sugar_node.get(NodeField.CONTENTS) or sugar_node.get("worker")

    wrapper = {
        NodeField.STACK_PATH: node_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.PARAMS: params,
        NodeField.WIRING: sugar_node.get(NodeField.WIRING, {}),
        NodeField.DESCRIPTION: sugar_node.get(NodeField.DESCRIPTION)
    }

    iterator_init = {
        NodeField.STACK_PATH: _generate_deterministic_id(node_id, OpCode.ITERATOR_INIT, 0),
        NodeField.OPCODE: OpCode.ITERATOR_INIT,
        NodeField.PARAMS: {"source": source, "item_key": item_key},
        NodeField.WIRING: {}
    }

    # 変数バインディングの実施
    # ここで _replace_variable_placeholders が呼び出され、正規表現ロジックが適用される
    _replace_variable_placeholders(inner_contents, KEY_ITERATION_BINDING, "{$KEY}")

    if strategy == "serial":
        _replace_serial_modifiers(inner_contents)

    iter_id = _generate_deterministic_id(node_id, OpCode.ITERATE, 1)
    iter_content_base = _join_path(iter_id, "{$KEY}")
    inner_scope_id = _join_path(output_scope_id, "{$KEY}")

    expanded_contents = _expand_recursive(
        inner_contents,
        parent_path=iter_content_base,
        sibling_index=0,
        output_scope_id=inner_scope_id
    )

    iterate_node = {
        NodeField.STACK_PATH: iter_id,
        NodeField.OPCODE: OpCode.ITERATE,
        NodeField.PARAMS: {"strategy": strategy},
        NodeField.CONTENTS: expanded_contents,
        NodeField.WIRING: {}
    }

    wrapper[NodeField.CHILDREN] = [iterator_init, iterate_node]
    return wrapper

# =========================================================
# Helper: Parameter Resolution Logic (分配機能の実装)
# =========================================================

def _resolve_params_with_briefing(
    briefing_data: Dict[str, Any],
    agent_name: str,
    system_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Briefingデータ、エージェント固有設定、システム強制設定を正しい優先順位でマージする。

    Priority (Low to High):
        1. Global Briefing (briefing直下のプリミティブ値)
        2. Agent Specific Briefing (briefing[agent_name] の中身)
        3. System Overrides (mode, agent等、システムが強制する値)

    Args:
        briefing_data: ユーザー定義の briefing 辞書
        agent_name: 現在処理中のエージェントID
        system_overrides: カーネル/コンパイラが強制するパラメータ

    Returns:
        マージ済みのフラットなパラメータ辞書
    """
    # 1. Global Briefing: 辞書以外の値（文字列、数値等）を抽出
    #    例: { "test": "msg", "ProjectArchitect": {...} } -> { "test": "msg" }
    final_params = {
        k: v for k, v in briefing_data.items()
        if not isinstance(v, dict)
    }

    # 2. Agent Specific Briefing: エージェント名のキーがあればマージ
    #    例: briefing["ProjectArchitect"] -> { "template": "T01A" }
    if agent_name in briefing_data:
        agent_specific = briefing_data[agent_name]
        if isinstance(agent_specific, dict):
            final_params.update(agent_specific)

    # 3. System Overrides: システム予約値を強制上書き (Security Guard)
    #    例: "mode": "generate" (ユーザーが "mode": "hack" と書いていてもここで直る)
    final_params.update(system_overrides)

    return final_params


# =========================================================
# Sugar Expansion Logics
# =========================================================

def _expand_ensemble(sugar_node: Dict[str, Any], node_id: str, output_scope_id: str) -> Dict[str, Any]:
    params = sugar_node.get(NodeField.PARAMS, {})
    generators = sugar_node.get("generators") or params.get("generators", [])
    samples = sugar_node.get("samples") or params.get("samples", 1)
    consolidator = sugar_node.get("consolidator") or params.get("consolidator")
    wiring = sugar_node.get(NodeField.WIRING, {})
    output_name = wiring.get(NodeField.OUTPUT, "EnsembleResult")
    inputs = wiring.get(NodeField.INPUTS, [])

    # Briefing Context Injection (Feature: Briefing)
    briefing_data = params.get(KEY_BRIEFING, {})

    wrapper = {
        NodeField.STACK_PATH: node_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.PARAMS: params,
        NodeField.DESCRIPTION: sugar_node.get(NodeField.DESCRIPTION),
        NodeField.WIRING: {}
    }

    diverge_id = _generate_deterministic_id(node_id, OpCode.PARALLEL, 0)
    parallel_node = {
        NodeField.STACK_PATH: diverge_id,
        NodeField.OPCODE: OpCode.PARALLEL,
        NodeField.CHILDREN: []
    }

    base_output_name = output_name
    implicit_suffix = f"#{output_scope_id}"
    if output_name.endswith(implicit_suffix):
        base_output_name = output_name[:-len(implicit_suffix)]

    # --- Self-Reference ID Resolution ---
    prev_loop_suffix = "v{$LOOP-1}"
    prev_scope_id = output_scope_id.replace("v{$LOOP}", prev_loop_suffix)

    candidate_implicit = _derive_self_output_id(output_name, prev_scope_id)
    candidate_explicit = None
    if "#" in output_name:
        candidate_explicit = _derive_self_output_id(output_name, prev_scope_id)

    diverged_outputs = []
    child_idx = 0
    for agent in generators:
        for i in range(1, samples + 1):
            worker_id = _generate_deterministic_id(diverge_id, OpCode.WORKER, child_idx)
            output_suffix = f"{agent}/{i}"

            private_base_name = f"_{base_output_name}"
            if "#" in private_base_name:
                effective_scope = _strip_default_from_scope(output_scope_id)
                private_scoped_base = _stack_id(private_base_name, effective_scope)
            else:
                private_scoped_base = _derive_self_output_id(private_base_name, output_scope_id)

            physical_output = _stack_id(private_scoped_base, output_suffix)
            diverged_outputs.append(physical_output)

            worker_inputs = []
            for inp in inputs:
                is_self_ref = (inp == candidate_implicit) or (candidate_explicit and inp == candidate_explicit)
                if is_self_ref:
                    prev_physical_output = physical_output.replace("v{$LOOP}", "v{$LOOP-1}")
                    worker_inputs.append(prev_physical_output)
                else:
                    worker_inputs.append(inp)

            # [FIXED] Params Injection with Agent Specific Distribution
            worker_system_params = {"agent": agent, "mode": WorkerMode.GENERATE}
            worker_final_params = _resolve_params_with_briefing(briefing_data, agent, worker_system_params)

            worker = {
                NodeField.STACK_PATH: worker_id,
                NodeField.OPCODE: OpCode.WORKER,
                NodeField.PARAMS: worker_final_params,
                NodeField.WIRING: {
                    NodeField.INPUTS: worker_inputs,
                    NodeField.OUTPUT: physical_output
                }
            }
            parallel_node[NodeField.CHILDREN].append(worker)
            child_idx += 1

    converge_output = _derive_self_output_id(output_name, output_scope_id)

    # [FIXED] Params Injection for Consolidator
    consolidator_system_params = {"agent": consolidator, "mode": WorkerMode.GENERATE}
    consolidator_final_params = _resolve_params_with_briefing(briefing_data, consolidator, consolidator_system_params)

    converge_node = {
        NodeField.STACK_PATH: _generate_deterministic_id(node_id, OpCode.WORKER, 1),
        NodeField.OPCODE: OpCode.WORKER,
        NodeField.PARAMS: consolidator_final_params,
        NodeField.WIRING: {
            NodeField.INPUTS: inputs + diverged_outputs,
            NodeField.OUTPUT: converge_output
        }
    }

    wrapper[NodeField.CHILDREN] = [parallel_node, converge_node]
    return wrapper


def _expand_generate_team(sugar_node: Dict[str, Any], node_id: str, output_scope_id: str) -> Dict[str, Any]:
    params = sugar_node.get(NodeField.PARAMS, {})
    generator = sugar_node.get("generator") or params.get("generator")
    validators = sugar_node.get("validators") or params.get("validators", [])
    loop_count = sugar_node.get("loop") or params.get("loop", 3)

    wiring = sugar_node.get(NodeField.WIRING, {})
    output_name = wiring.get(NodeField.OUTPUT, "TeamResult")
    base_inputs = wiring.get(NodeField.INPUTS, [])

    # Briefing Context Injection (Feature: Briefing)
    briefing_data = params.get(KEY_BRIEFING, {})

    # ループ深度のシフト (Inner LoopからOuter Loop変数を参照するため)
    base_inputs = [_shift_loop_depth(inp) for inp in base_inputs]

    # Generator専用Inputの取り出しとシフト
    extra_inputs = sugar_node.get("_generator_extra_inputs", [])
    shifted_extra_inputs = [_shift_loop_depth(inp) for inp in extra_inputs]

    wrapper = {
        NodeField.STACK_PATH: node_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.PARAMS: params,
        NodeField.WIRING: {},
    }

    loop_id = _generate_deterministic_id(node_id, OpCode.LOOP, 0)
    loop_content_base = _join_path(loop_id, "v{$LOOP}")
    inner_serial_id = _generate_deterministic_id(loop_content_base, OpCode.SERIAL, 0)

    flat_validators: List[Tuple[str, List[str]]] = []
    for val in validators:
        if isinstance(val, str):
            flat_validators.append((val, []))
        elif isinstance(val, dict):
            refs = val.get("refs", [])
            if "agent" in val:
                flat_validators.append((val["agent"], refs))
            if "agents" in val and isinstance(val["agents"], list):
                for a in val["agents"]:
                    flat_validators.append((a, refs))

    shifted_scope = _shift_loop_depth(output_scope_id)
    loop_output_base = _derive_self_output_id(output_name, shifted_scope)

    loop_output_current = _stack_id(loop_output_base, "v{$LOOP}")
    loop_output_prev = _stack_id(loop_output_base, "v{$LOOP-1}")

    # Generator用Inputの構築
    gen_inputs = base_inputs.copy()
    gen_inputs.extend(shifted_extra_inputs)
    gen_inputs.append(loop_output_prev)

    for agent_name, _ in flat_validators:
        feedback_base = _create_feedback_id(output_name, agent_name)
        fb_output_base = _derive_self_output_id(feedback_base, shifted_scope)
        gen_inputs.append(_stack_id(fb_output_base, "v{$LOOP-1}"))

    # [FIXED] Params Injection for Generator
    gen_system_params = {"agent": generator, "mode": WorkerMode.GENERATE}
    gen_final_params = _resolve_params_with_briefing(briefing_data, generator, gen_system_params)

    generator_node = {
        NodeField.STACK_PATH: _generate_deterministic_id(inner_serial_id, OpCode.WORKER, 0),
        NodeField.OPCODE: OpCode.WORKER,
        NodeField.PARAMS: gen_final_params,
        NodeField.WIRING: {
            NodeField.INPUTS: gen_inputs,
            NodeField.OUTPUT: loop_output_current
        }
    }

    val_parallel_id = _generate_deterministic_id(inner_serial_id, OpCode.PARALLEL, 1)
    val_parallel = {
        NodeField.STACK_PATH: val_parallel_id,
        NodeField.OPCODE: OpCode.PARALLEL,
        NodeField.CHILDREN: []
    }

    for i, (agent_name, specific_refs) in enumerate(flat_validators):
        shifted_specific_refs = [_shift_loop_depth(r) for r in specific_refs] if specific_refs else []
        current_val_inputs = (shifted_specific_refs if shifted_specific_refs else base_inputs) + [loop_output_current]

        feedback_base = _create_feedback_id(output_name, agent_name)
        fb_output_base = _derive_self_output_id(feedback_base, shifted_scope)
        fb_output_current = _stack_id(fb_output_base, "v{$LOOP}")

        # [FIXED] Params Injection for Validators
        val_system_params = {"agent": agent_name, "mode": WorkerMode.VALIDATE}
        val_final_params = _resolve_params_with_briefing(briefing_data, agent_name, val_system_params)

        val_worker = {
            NodeField.STACK_PATH: _generate_deterministic_id(val_parallel_id, OpCode.WORKER, i),
            NodeField.OPCODE: OpCode.WORKER,
            NodeField.PARAMS: val_final_params,
            NodeField.WIRING: {
                NodeField.INPUTS: current_val_inputs,
                NodeField.OUTPUT: fb_output_current
            }
        }
        val_parallel[NodeField.CHILDREN].append(val_worker)

    inner_serial = {
        NodeField.STACK_PATH: inner_serial_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.CHILDREN: [generator_node, val_parallel]
    }

    loop_node = {
        NodeField.STACK_PATH: loop_id,
        NodeField.OPCODE: OpCode.LOOP,
        NodeField.PARAMS: {"count": loop_count, "break_on": "success"},
        NodeField.CONTENTS: inner_serial,
        NodeField.WIRING: {}
    }

    resolve_map_to = _derive_self_output_id(output_name, output_scope_id)
    resolve_target = _extract_logical_name(output_name)

    resolve_node = {
        NodeField.STACK_PATH: _generate_deterministic_id(node_id, OpCode.SCOPE_RESOLVE, 1),
        NodeField.OPCODE: OpCode.SCOPE_RESOLVE,
        NodeField.PARAMS: {
            "target": resolve_target,
            "from_scope": "loop",
            "strategy": "take_latest_success",
            "map_to": resolve_map_to
        },
        NodeField.WIRING: {}
    }

    wrapper[NodeField.CHILDREN] = [loop_node, resolve_node]
    return wrapper

def _expand_approval_gate(sugar_node: Dict[str, Any], node_id: str, output_scope_id: str) -> Dict[str, Any]:
    params = sugar_node.get(NodeField.PARAMS, {})
    approver = sugar_node.get("approver") or params.get("approver")
    target_doc = sugar_node.get("target") or params.get("target")
    inner_contents = sugar_node.get(NodeField.CONTENTS)

    # ラッパー(Serial)に残すパラメータを整理する
    # 'approver' と 'target' は展開ロジックで消費済みなので、ラッパーのparamsからは除外する
    wrapper_params = params.copy()
    wrapper_params.pop("approver", None)
    wrapper_params.pop("target", None)
    
    wrapper = {
        NodeField.STACK_PATH: node_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.PARAMS: wrapper_params,
        NodeField.WIRING: {},
    }

    loop_id = _generate_deterministic_id(node_id, OpCode.LOOP, 0)
    loop_content_base = _join_path(loop_id, "v{$LOOP}")
    inner_serial_id = _generate_deterministic_id(loop_content_base, OpCode.SERIAL, 0)

    shifted_scope = _shift_loop_depth(output_scope_id)

    feedback_base = _create_feedback_id(target_doc, approver)
    fb_base_id = _derive_self_output_id(feedback_base, shifted_scope)
    approver_feedback_id = _stack_id(fb_base_id, "v{$LOOP-1}")

    target_base_id = _derive_self_output_id(target_doc, shifted_scope)

    # 【NEW】ターゲットの前回バージョンIDを作成 (Target#.../v{$LOOP-1})
    target_prev_id = _stack_id(target_base_id, "v{$LOOP-1}")
    # ターゲットの論理名 (フィルタリング用)
    target_logical_name = _extract_logical_name(target_doc)

    inner_contents_copy = copy.deepcopy(inner_contents)

    # 1. Feedback Injection (既存): 全てのGenerator (Worker/Ensemble/Team) に注入
    _inject_input_to_leaf_generators(inner_contents_copy, approver_feedback_id)

    # 2. Target Snapshot Injection (新規): Generator専用フィールドに注入
    #    generate_team の inputs を汚染せず、Generatorだけに届ける
    _inject_generator_specific_input(
        node=inner_contents_copy,
        input_id=target_prev_id,
        required_output_name=target_logical_name
    )

    _inject_dynamic_self_reference(inner_contents_copy, shifted_scope)

    inner_scope_id = _join_path(shifted_scope, "v{$LOOP}")

    expanded_inner = _expand_recursive(
        inner_contents_copy,
        parent_path=inner_serial_id,
        sibling_index=0,
        output_scope_id=inner_scope_id
    )

    dialogue_inputs = [
        _stack_id(target_base_id, "v{$LOOP}"),
        _stack_id(target_base_id, "v{$LOOP-1}"),
        approver_feedback_id
    ]

    dialogue_node = {
        NodeField.STACK_PATH: _generate_deterministic_id(inner_serial_id, OpCode.APPROVER, 1),
        NodeField.OPCODE: OpCode.APPROVER,
        NodeField.PARAMS: {"agent": approver},
        NodeField.WIRING: {
            NodeField.INPUTS: dialogue_inputs,
            NodeField.OUTPUT: _stack_id(fb_base_id, "v{$LOOP}")
        }
    }

    inner_serial = {
        NodeField.STACK_PATH: inner_serial_id,
        NodeField.OPCODE: OpCode.SERIAL,
        NodeField.CHILDREN: [expanded_inner, dialogue_node]
    }

    loop_node = {
        NodeField.STACK_PATH: loop_id,
        NodeField.OPCODE: OpCode.LOOP,
        NodeField.PARAMS: {"count": 10, "break_on": "success"},
        NodeField.CONTENTS: inner_serial,
        NodeField.WIRING: {}
    }

    resolve_map_to = _derive_self_output_id(target_doc, output_scope_id)
    resolve_target = _extract_logical_name(target_doc)

    resolve_node = {
        NodeField.STACK_PATH: _generate_deterministic_id(node_id, OpCode.SCOPE_RESOLVE, 1),
        NodeField.OPCODE: OpCode.SCOPE_RESOLVE,
        NodeField.PARAMS: {
            "target": resolve_target,
            "from_scope": "loop",
            "strategy": "take_latest_success",
            "map_to": resolve_map_to
        },
        NodeField.WIRING: {}
    }

    wrapper[NodeField.CHILDREN] = [loop_node, resolve_node]
    return wrapper


def _inject_input_to_leaf_generators(
    node: Dict[str, Any],
    input_id: str,
    exclude_opcodes: List[str] = None,
    required_output_name: str = None
) -> None:
    if not isinstance(node, dict): return
    if exclude_opcodes is None: exclude_opcodes = []

    opcode = node.get(NodeField.OPCODE)
    wiring = node.get(NodeField.WIRING, {})

    if opcode in [OpCode.WORKER, "ensemble", "generate_team"]:
        if opcode in exclude_opcodes:
            return

        if required_output_name:
            current_output = wiring.get(NodeField.OUTPUT, "")
            logical_out = _extract_logical_name(current_output)
            if logical_out != required_output_name:
                return

        if NodeField.INPUTS not in wiring:
            wiring[NodeField.INPUTS] = []
        if input_id not in wiring[NodeField.INPUTS]:
            wiring[NodeField.INPUTS].append(input_id)
        node[NodeField.WIRING] = wiring

    if NodeField.CHILDREN in node:
        for child in node[NodeField.CHILDREN]:
            _inject_input_to_leaf_generators(child, input_id, exclude_opcodes, required_output_name)
    if NodeField.CONTENTS in node:
        _inject_input_to_leaf_generators(node[NodeField.CONTENTS], input_id, exclude_opcodes, required_output_name)


def _inject_generator_specific_input(
    node: Dict[str, Any],
    input_id: str,
    required_output_name: str = None
) -> None:
    """generate_team の Generator だけに渡したいInputを一時フィールドに退避させる"""
    if not isinstance(node, dict): return

    opcode = node.get(NodeField.OPCODE)

    if opcode == "generate_team":
        # 対象の成果物を作っているチームか確認
        if required_output_name:
            wiring = node.get(NodeField.WIRING, {})
            current_output = wiring.get(NodeField.OUTPUT, "")
            if _extract_logical_name(current_output) != required_output_name:
                return

        # 隠しフィールドに追記
        if "_generator_extra_inputs" not in node:
            node["_generator_extra_inputs"] = []
        if input_id not in node["_generator_extra_inputs"]:
            node["_generator_extra_inputs"].append(input_id)

    # 再帰探索
    if NodeField.CHILDREN in node:
        for child in node[NodeField.CHILDREN]:
            _inject_generator_specific_input(child, input_id, required_output_name)
    if NodeField.CONTENTS in node:
        _inject_generator_specific_input(node[NodeField.CONTENTS], input_id, required_output_name)


def _inject_dynamic_self_reference(node: Dict[str, Any], scope_prefix: str) -> None:
    if not isinstance(node, dict): return

    opcode = node.get(NodeField.OPCODE)

    if opcode == "generate_team":
        return

    if opcode in [OpCode.WORKER, "ensemble"]:
        wiring = node.get(NodeField.WIRING, {})
        output = wiring.get(NodeField.OUTPUT)
        if output:
            if "#" in output:
                scope_with_loop = _strip_default_from_scope(scope_prefix)
                prev_suffix = _join_path(scope_with_loop, "v{$LOOP-1}")
                prev_id = _stack_id(output, prev_suffix)
            else:
                suffix = f"{scope_prefix}/v{{$LOOP-1}}"
                if scope_prefix:
                    prev_id = f"{output}#{suffix}"
                else:
                    prev_id = f"{output}#v{{$LOOP-1}}"

            if NodeField.INPUTS not in wiring:
                wiring[NodeField.INPUTS] = []
            if prev_id not in wiring[NodeField.INPUTS]:
                wiring[NodeField.INPUTS].append(prev_id)
            node[NodeField.WIRING] = wiring

    if NodeField.CHILDREN in node:
        for child in node[NodeField.CHILDREN]:
            _inject_dynamic_self_reference(child, scope_prefix)

    if NodeField.CONTENTS in node and opcode not in ["ensemble", "fan_out"]:
        _inject_dynamic_self_reference(node[NodeField.CONTENTS], scope_prefix)


def _replace_serial_modifiers(node: Any) -> None:
    """
    Serial Fan-out用の修飾子 (@prev, @history) を物理IDサフィックス (#$PREV, #$HISTORY) に置換する。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == NodeField.INPUTS and isinstance(value, list):
                new_inputs = []
                for v in value:
                    if isinstance(v, str):
                        # @history -> #$HISTORY
                        if v.endswith("@history"):
                            v = v[:-len("@history")] + "#{$HISTORY}"
                        # @prev -> #$PREV
                        elif v.endswith("@prev"):
                            v = v[:-len("@prev")] + "#{$PREV}"
                    new_inputs.append(v)
                node[key] = new_inputs
            else:
                _replace_serial_modifiers(value)
    elif isinstance(node, list):
        for item in node:
            _replace_serial_modifiers(item)