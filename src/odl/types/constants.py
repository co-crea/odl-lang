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

from typing import Final

# Artifact ID Generation Constants
# システムが自動生成する成果物IDに含まれる予約語（Infix）
# Format: {TargetDoc}__{Infix}{AgentName}
REVIEW_ARTIFACT_INFIX: Final[str] = "__Review_"

# Compiler Reserved Keys (Syntactic Sugar Parameters)
# チーム組成系シュガー構文において、内部Workerへコンテキストを注入するための予約キー
KEY_BRIEFING: Final[str] = "briefing"

# Source上で、反復中の現在のキー(または要素)を参照するための予約語
KEY_ITERATION_BINDING: Final[str] = "__key"