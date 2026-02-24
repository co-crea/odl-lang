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

from typing import Any, List, Optional
from pydantic import ValidationError

from odl.types import IrComponent, NodeField
from ..exceptions import OdlCompilationError

def assemble(data: dict[str, Any]) -> IrComponent:
    """
    展開・解決済みの辞書データを、L0定義の IrComponent (Pydantic Model) に変換・確定する。
    最終的な型チェックと構造バリデーションを行う。

    Note:
        再帰的に assemble を呼び出すことで、全ての子孫ノードに対しても
        明示的なアセンブリ処理（辞書 -> IrComponent）を適用する。

    Args:
        data (dict): Resolved Dictionary

    Returns:
        IrComponent: Validated IR Object Tree

    Raises:
        OdlCompilationError: バリデーション失敗時
    """
    try:
        # 1. 再帰要素の先行アセンブリ (Recursive Assembly)
        # children: List[IrComponent]
        raw_children = data.get(NodeField.CHILDREN, [])
        assembled_children: List[IrComponent] = [
            assemble(child) for child in raw_children
        ]

        # contents: Optional[IrComponent]
        raw_contents = data.get(NodeField.CONTENTS)
        assembled_contents: Optional[IrComponent] = (
            assemble(raw_contents) if raw_contents else None
        )

        # 2. コンポーネントの構築 (Explicit Construction)
        # NodeField Enum を使用して安全にフィールドへマッピングする
        return IrComponent(
            stack_path=data[NodeField.STACK_PATH],
            opcode=data[NodeField.OPCODE],
            wiring=data.get(NodeField.WIRING),
            params=data.get(NodeField.PARAMS, {}),
            children=assembled_children,
            contents=assembled_contents
        )

    except ValidationError as e:
        # エラーメッセージを整形してラップする
        error_msg = f"Assembly failed: {str(e)}"
        raise OdlCompilationError(error_msg, stage="Assembler") from e
    except Exception as e:
        raise OdlCompilationError(f"Unexpected assembly error: {str(e)}", stage="Assembler") from e