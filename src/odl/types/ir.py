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

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .enums import OpCode, NodeType

class WiringObject(BaseModel):
    """
    入出力の配線定義 (Value Object)
    cocrea_runtime-2202: object_model.ir_types.WiringObject
    """
    inputs: List[str] = Field(
        default_factory=list, 
        description="入力として受け取る変数のキーリスト (e.g. ['Doc#v1'])"
    )
    output: Optional[str] = Field(
        None, 
        description="処理結果を出力する変数のキーサフィックス"
    )


class IrComponent(BaseModel):
    """
    ODLの中間表現（IR）コンポーネント (Recursive Data Schema)
    cocrea_runtime-2202: object_model.ir_types.IrComponent
    """
    stack_path: str = Field(
        ..., 
        description=(
            "ルートからの論理的な階層位置を一意に示すパス文字列（例: 'root/LoopA/v{$LOOP}/Step1'）。"
            "実行時に物理ID(UUID)を決定論的に導出するためのシードとして使用される。"
        )
    )
    opcode: OpCode = Field(..., description="命令コード")
    
    # 配線情報 (Atom系で必須、Control系ではOptional)
    wiring: Optional[WiringObject] = Field(None, description="入出力依存関係")
    
    # パラメータ (静的な設定値)
    params: Dict[str, Any] = Field(
        default_factory=dict, 
        description="命令固有の静的パラメータ (e.g. {'timeout': 30})"
    )

    # --- 再帰構造 (Recursion) ---
    
    # 1. List構造 (Serial, Parallelのbodyなど)
    children: List[IrComponent] = Field(
        default_factory=list, 
        description="子ノードのリスト（順序付き）"
    )
    
    # 2. Block構造 (Loop, Iterateの内部ブロックなど)
    contents: Optional[IrComponent] = Field(
        None, 
        description="単一の内部ブロック（コンテナ用）"
    )

    # 3. 利便性のためのプロパティ
    @property
    def node_type(self) -> NodeType:
        return self.opcode.node_type

# Pydanticモデルの再帰定義を解決
IrComponent.model_rebuild()