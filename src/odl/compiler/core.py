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

import logging
from typing import Any

# [Migration] Shared依存から、自ライブラリ内の型定義への参照に変更
# Old: from shared.domains.odl.structs import IrComponent
from odl.types import IrComponent

# 相対インポートは、compiler/ディレクトリ直下に配置されるためそのまま機能します
from .exceptions import OdlCompilationError
from .pipeline import parser, expander, resolver, assembler
from .rules import syntax, wiring

logger = logging.getLogger(__name__)

def _debug_dump_structure(data: Any, depth: int = 0, max_depth: int = 20, path: str = "ROOT") -> str:
    """
    再帰的な構造を安全にダンプする。
    最大深度を超えた場合、そこで打ち切ってエラーメッセージを埋め込む。
    """
    indent = "  " * depth
    
    if depth > max_depth:
        return f"{indent}<!!! MAX DEPTH EXCEEDED at {path} !!!>"

    if isinstance(data, dict):
        # 重要な情報を先頭に
        node_id = data.get("id", "?")
        opcode = data.get("opcode", "?")
        header = f"(opcode={opcode}, id={node_id})"
        
        lines = [header]
        for k, v in data.items():
            # children/contents/wiring などの構造決定要素を優先表示
            if k in ["children", "contents", "wiring", "params"]:
                child_str = _debug_dump_structure(v, depth + 1, max_depth, path=f"{path}.{k}")
                lines.append(f"{indent}{k}: {child_str}")
            # それ以外は省略気味に（必要なら表示）
            elif k not in ["id", "opcode"]: 
                lines.append(f"{indent}{k}: <...>")
        return "\n".join(lines)

    elif isinstance(data, list):
        lines = []
        for i, item in enumerate(data):
            lines.append(f"\n{indent}- [{i}]: {_debug_dump_structure(item, depth + 1, max_depth, path=f'{path}[{i}]')}")
        return "".join(lines)

    else:
        return str(data)

def compile_odl(source: str) -> IrComponent:
    """
    ODLソースコード(YAML)をコンパイルし、実行可能な中間表現(IR)を生成する。
    
    Pipeline Sequence:
      1. Parse: YAML -> Dict
      2. Syntax Check: Static Validation
      3. Expand: Desugaring & ID Generation
      4. Resolve: Wiring Resolution
      5. Wiring Check: Logic Validation
      6. Assemble: Dict -> IrComponent (Pydantic Model)
    
    Args:
        source (str): ODL Source YAML string
        
    Returns:
        IrComponent: Compiled IR Root Object
        
    Raises:
        OdlCompilationError: コンパイル失敗時に送出
    """
    # 0. Input Guard
    if not source or not source.strip():
        raise OdlCompilationError("Empty ODL source provided", stage="InputGuard")

    try:
        # Step 1: Parsing
        # YAML文字列をPython辞書構造へ変換
        logger.debug("Starting Phase 1: Parsing")
        raw_dict = parser.parse(source)

        # Step 2: Syntax Validation
        # 必須フィールドや型制約のチェック (Fail Fast)
        logger.debug("Starting Phase 2: Syntax Validation")
        syntax.validate(raw_dict)

        # Step 3: Expansion (The Physics 1)
        # Sugarの展開と決定論的IDの付与
        logger.debug("Starting Phase 3: Expansion")
        expanded_dict = expander.expand(raw_dict)

        # --- DEBUG: 循環チェック ---
        # 循環だけでなく、深すぎるネストも検知してログに残します
        try:
            # 深さ30を超えたら異常とみなしてダンプ
            dump_str = _debug_dump_structure(expanded_dict, max_depth=30)
            if "<!!! MAX DEPTH EXCEEDED" in dump_str:
                logger.error(f"[FATAL] Infinite Structure Detected!\n{dump_str}")
                raise RuntimeError("Infinite Structure Detected in Expander! Check logs for trace.")
            
            # 正常時も念のためDEBUGログに残す（デバッグ用）
            # logger.debug(f"Expanded Structure:\n{dump_str}")
            
        except Exception as e:
            # ダンプ処理自体が失敗した場合の保険
            logger.error(f"Failed to check structure: {e}")
            raise
        # -------------------------

        # Step 4: Resolution (The Physics 2)
        # 論理名参照の物理IDへの解決
        logger.debug("Starting Phase 4: Resolution")
        resolved_dict = resolver.resolve(expanded_dict)

        # Step 5: Wiring Validation
        # 循環参照や未解決IDのチェック
        logger.debug("Starting Phase 5: Wiring Validation")
        wiring.validate(resolved_dict)

        # Step 6: Assembly
        # 最終的な型オブジェクトへの変換
        logger.debug("Starting Phase 6: Assembly")
        ir_root = assembler.assemble(resolved_dict)
        
        logger.info(f"ODL Compilation completed successfully. Stack Path: {ir_root.stack_path}")
        return ir_root

    except OdlCompilationError:
        # 既知のコンパイルエラーはそのまま通過させる
        raise
    except Exception as e:
        # 予期せぬ内部エラー（実装バグやライブラリエラー）をラップする
        logger.error(f"Unexpected compilation error: {str(e)}", exc_info=True)
        raise OdlCompilationError(
            message=f"Internal compilation error: {str(e)}",
            stage="Unknown"
        ) from e