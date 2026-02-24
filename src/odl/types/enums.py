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

from enum import StrEnum, auto

class NodeType(StrEnum):
    """
    ノードの振る舞いを決定する基本属性
    """
    ACTION = "ACTION"   # 外部委譲型（Worker/Persona）待つのが仕事
    CONTROL = "CONTROL" # 内部制御型（Serial/Loop...）産んで管理するのが仕事
    LOGIC = "LOGIC"     # 内部論理型（ScopeResolve/IteratorInit）即時計算して完了する仕事

class OpCode(StrEnum):
    """
    ODL (Organizational Definition Language) における命令コード
    コンパイラ(cocrea-2002)とカーネル(cocrea-2003)が共有する命令セットの語彙
    """
    # --- Atoms (原子) ---
    WORKER = "worker"           # I/Oを持つ最小の処理単位
    DIALOGUE = "dialogue"       # 外部との同期通信単位
    APPROVER = "approver"       # 承認者
    
    # --- Control Structures (制御構造) ---
    SERIAL = "serial"           # 定義順実行
    PARALLEL = "parallel"       # 同時実行
    LOOP = "loop"               # 条件付き反復
    ITERATE = "iterate"         # リストに基づく反復展開 (Fan-outの実体)

    # --- Logic / Internal (内部論理) ---
    SCOPE_RESOLVE = "scope_resolve"  # ブロック終了時の成果物解決
    ITERATOR_INIT = "iterator_init"  # 反復用カーソルの初期化

    # 2. OpCode自身に性質を問えるようにする
    @property
    def node_type(self) -> NodeType:
        if self in (OpCode.WORKER, OpCode.DIALOGUE, OpCode.APPROVER):
            return NodeType.ACTION
        elif self in (OpCode.SERIAL, OpCode.PARALLEL, OpCode.LOOP, OpCode.ITERATE):
            return NodeType.CONTROL
        elif self in (OpCode.SCOPE_RESOLVE, OpCode.ITERATOR_INIT):
            return NodeType.LOGIC
        raise ValueError(f"Unknown NodeType for OpCode: {self}")
    
class NodeField(StrEnum):
    """
    ODLノード（辞書/IR）を構成する予約済みフィールドキー
    """
    # Structural Identifiers
    STACK_PATH = "stack_path"
    OPCODE = "opcode"
    DESCRIPTION = "description"

    # Container / Recursion
    CHILDREN = "children"  # List container
    CONTENTS = "contents"  # Block container

    # Configuration Buckets
    PARAMS = "params"      # Static parameters
    WIRING = "wiring"      # I/O Definition

    # Wiring Specific Keys (これらはパース時に wiring バケットへ移動される)
    INPUTS = "inputs"
    OUTPUT = "output"

class WorkerMode(StrEnum):
    """
    Workerノードの実行モード
    """
    GENERATE = "generate"   # 新規生成
    VALIDATE = "validate"   # 検証