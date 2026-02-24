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

import re
from typing import Any, Dict, List, Optional

from odl.types import OpCode, NodeField, KEY_ITERATION_BINDING
from ..exceptions import OdlCompilationError

# 禁止文字: : (Colon), / (Slash), { } (Braces), @ (At sign)
# # (Hash) はExplicit ID Binding用のセパレータとして許容するため除外
FORBIDDEN_CHARS_PATTERN = re.compile(r"[:/{}\@]")

# Parallel戦略下で使用してはならない修飾子
SERIAL_ONLY_MODIFIERS = ["@prev", "@history"]

# Fan-outのItem Binding用サフィックス
ITEM_BINDING_SUFFIX = f".{KEY_ITERATION_BINDING}"

def validate(
    node: Dict[str, Any],
    parent_opcodes: Optional[List[str]] = None,
    inside_parallel_fanout: bool = False
) -> None:
    """
    ODLノードの構文的妥当性を再帰的に検証する（静的解析）。

    Args:
        node: 検証対象のノード辞書
        parent_opcodes: 親ノードのOpCode履歴（ネスト制約チェック用）
        inside_parallel_fanout: Parallel Fan-outのスコープ内か否か（修飾子制約チェック用）

    Raises:
        OdlCompilationError: 構文違反が見つかった場合
    """
    if parent_opcodes is None:
        parent_opcodes = []

    # 1. Basic Field Extraction
    opcode = node.get(NodeField.OPCODE)
    params = node.get(NodeField.PARAMS, {})
    wiring = node.get(NodeField.WIRING, {})

    # OpCode自体の存在チェックは parser/syntax の初期段階で行われる想定だが、念のため
    if not opcode:
        pass

    # =========================================================
    # 2. Contextual Rules (文脈制約)
    # =========================================================

    # Fan-out Nesting Check
    if opcode == "fan_out":
        if "fan_out" in parent_opcodes:
            raise OdlCompilationError(
                f"Nested fan_out is not allowed. Found inside: {parent_opcodes}",
                stage="SyntaxRule"
            )

    # Parallel Strategy Constraint Check
    if inside_parallel_fanout and wiring:
        inputs = wiring.get(NodeField.INPUTS, [])
        for inp in inputs:
            if isinstance(inp, str):
                for modifier in SERIAL_ONLY_MODIFIERS:
                    if modifier in inp:
                        raise OdlCompilationError(
                            f"Invalid modifier '{modifier}' found in inputs under parallel strategy. "
                            "These are allowed only in 'serial' strategy.",
                            stage="SyntaxRule"
                        )

    # =========================================================
    # 3. OpCode Specific Checks (命令ごとの必須要件)
    # =========================================================

    if opcode == OpCode.LOOP:
        if NodeField.CONTENTS not in node:
            raise OdlCompilationError(f"Missing required field '{NodeField.CONTENTS}' for opcode '{opcode}'", stage="SyntaxRule")

        count = params.get("count")
        if count is not None and not isinstance(count, int):
             raise OdlCompilationError(f"loop 'count' must be integer, got {type(count).__name__}", stage="SyntaxRule")

    elif opcode == "fan_out":
        for field in ["source", "item_key", NodeField.CONTENTS]:
            if field not in node and field not in params:
                 raise OdlCompilationError(f"Missing required field '{field}' for opcode '{opcode}'", stage="SyntaxRule")

    elif opcode == OpCode.WORKER:
        if not wiring:
             raise OdlCompilationError(f"Missing or empty '{NodeField.WIRING}' block for worker", stage="SyntaxRule")

        if NodeField.INPUTS not in wiring:
             raise OdlCompilationError(f"Worker must have '{NodeField.INPUTS}' in {NodeField.WIRING}", stage="SyntaxRule")

        if NodeField.OUTPUT not in wiring:
             raise OdlCompilationError(f"Worker must have '{NodeField.OUTPUT}' in {NodeField.WIRING}", stage="SyntaxRule")

    elif opcode == "ensemble":
        generators = params.get("generators") or node.get("generators", [])
        if isinstance(generators, list):
            if len(generators) != len(set(generators)):
                raise OdlCompilationError(
                    f"Duplicate generator agent IDs found in ensemble: {generators}",
                    stage="SyntaxRule"
                )

    elif opcode == OpCode.ITERATOR_INIT:
        for field in ["source", "item_key"]:
            if field not in node and field not in params:
                raise OdlCompilationError(f"Missing required field '{field}' for opcode '{opcode}'", stage="SyntaxRule")

    elif opcode == OpCode.SCOPE_RESOLVE:
        for field in ["target", "from_scope", "strategy", "map_to"]:
            if field not in node and field not in params:
                raise OdlCompilationError(f"Missing required field '{field}' for opcode '{opcode}'", stage="SyntaxRule")

    # =========================================================
    # 4. Naming Convention Check (命名規則 & Inputs検証)
    # =========================================================
    
    # 4-1. Output Name Validation
    if NodeField.OUTPUT in wiring:
        _validate_name(wiring[NodeField.OUTPUT])

    # scope_resolve map_to check
    if opcode == OpCode.SCOPE_RESOLVE:
        map_to = node.get("map_to") or params.get("map_to")
        if map_to:
            _validate_name(map_to)

    # 4-2. Inputs Validation (Item Binding Check)
    if NodeField.INPUTS in wiring:
        for inp in wiring[NodeField.INPUTS]:
            if not isinstance(inp, str):
                continue
            
            if inp == KEY_ITERATION_BINDING:
                raise OdlCompilationError(
                    f"Invalid item binding '{KEY_ITERATION_BINDING}'. It must be qualified with a LocalName (e.g. 'Doc.{KEY_ITERATION_BINDING}').",
                    stage="SyntaxRule"
                )

            if inp.endswith(ITEM_BINDING_SUFFIX):
                prefix = inp[:-len(ITEM_BINDING_SUFFIX)]
                
                # Check LocalName validity
                if not prefix:
                    raise OdlCompilationError(
                        f"Invalid item binding '{inp}'. LocalName cannot be empty.",
                        stage="SyntaxRule"
                    )

                if FORBIDDEN_CHARS_PATTERN.search(prefix):
                    raise OdlCompilationError(
                        f"Invalid LocalName in item binding '{inp}'. "
                        "Characters ':', '/', '{', '}', '@' are forbidden in LocalName.",
                        stage="SyntaxRule"
                    )

    # =========================================================
    # 5. Recursive Validation (再帰検証)
    # =========================================================

    next_parent_opcodes = parent_opcodes + [str(opcode)] if opcode else parent_opcodes

    next_inside_parallel = inside_parallel_fanout
    if opcode == "fan_out":
        strategy = params.get("strategy") or node.get("strategy")
        if strategy == "parallel":
            next_inside_parallel = True
        elif strategy == "serial":
            pass

    if NodeField.CHILDREN in node:
        children = node[NodeField.CHILDREN]
        if not isinstance(children, list):
             raise OdlCompilationError(f"'{NodeField.CHILDREN}' must be a list", stage="SyntaxRule")
        for child in children:
            validate(child, next_parent_opcodes, next_inside_parallel)

    if NodeField.CONTENTS in node:
        contents = node[NodeField.CONTENTS]
        if not isinstance(contents, dict):
             raise OdlCompilationError(f"'{NodeField.CONTENTS}' must be a dictionary", stage="SyntaxRule")
        validate(contents, next_parent_opcodes, next_inside_parallel)


def _validate_name(name: str) -> None:
    """出力変数名（ドキュメントID）の妥当性を検証する。"""
    if not isinstance(name, str):
        return

    hash_count = name.count("#")
    if hash_count > 1:
        raise OdlCompilationError(
            f"Invalid output name '{name}': Only one '#' separator is allowed.",
            stage="SyntaxRule"
        )

    parts = name.split("#")
    local_name = parts[0]

    if hash_count == 1:
        if not local_name:
            raise OdlCompilationError(
                f"Invalid output name '{name}': Local name before '#' cannot be empty.",
                stage="SyntaxRule"
            )
        if not parts[1]:
            raise OdlCompilationError(
                f"Invalid output name '{name}': Explicit ID suffix after '#' cannot be empty.",
                stage="SyntaxRule"
            )

    if "__" in local_name:
        raise OdlCompilationError(
            f"Invalid output name '{name}': Names containing '__' (Double Underscore) are reserved for system usage.",
            stage="SyntaxRule"
        )

    if local_name.startswith("_"):
        raise OdlCompilationError(
            f"Invalid output name '{name}': Names starting with '_' (Underscore) are reserved for private variables.",
            stage="SyntaxRule"
        )

    if FORBIDDEN_CHARS_PATTERN.search(name):
        raise OdlCompilationError(
            f"Invalid character in output name '{name}'. "
            "Characters ':', '/', '{', '}', '@' are forbidden.",
            stage="SyntaxRule"
        )