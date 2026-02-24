# ODL (Organizational Definition Language) Specification
---

## 1. Introduction

ODL (Organizational Definition Language) is a declarative language designed to define the **Structure**, **Behavior**, and **Data Flow** of autonomous agent organizations.

### Core Philosophy
* **Organization as Code:** Structure must be version-controlled, reproducible, and diffable.
* **Declarative:** Define the *shape* of the team (e.g., "A self-correcting design team"), not the imperative loop counters.
* **Deterministic:** The same Source YAML always compiles to the exact same Logical Path structure.

---

# Part I: The Language Guide (For Users)

This section describes how to write ODL files to define your organization's behavior.

## 2. Anatomy of a Node

In ODL, everything is a **Node**. The compiler infers the node's type (**OpCode**) directly from the **YAML Key**.

### 2.1. Basic Structure
A node consists of three primary buckets:

1.  **Identity (Key/OpCode):** What is this node? (e.g., `worker`, `serial`)
2.  **Configuration (Params):** Static settings (e.g., `agent`, `count`).
3.  **Connections (Wiring):** Input/Output flow (`inputs`, `output`).

**Shorthand Syntax:**
You do not need to separate these buckets manually. The compiler organizes them automatically.

```yaml
# User Shorthand (Source)
worker:                 # <--- Key acts as OpCode (Identity)
  agent: "Writer"       # -> Params
  inputs: ["Topic"]     # -> Wiring
  output: "Draft"       # -> Wiring
```

### 2.2. Document Naming & References
ODL distinguishes between external resources and internal artifacts based on syntax.

* **Job Document (Internal Variable):**
    * **Syntax:** `MyDocument`
    * **Description:** Intermediate artifacts generated during execution.
    * **Restrictions:**
        * Must NOT contain `:` (Colon) or `#` (Hash).
        * **Reserved:** Names containing `__` (double underscore) are forbidden (System Reserved).
        * **Private:** Names starting with `_` (single underscore) are forbidden (Private Variables).

* **Project Document (External Reference):**
    * **Syntax:** `Name:ResourceID[@Version]`
    * **Description:** Read-only references to external official documents.
    * **Example:** `MarketData:MKT_2024@stable`
    * **Note:** If `@Version` is omitted, it defaults to `@stable`.

---

## 3. The Standard Library (High-Level Constructs)

These "Syntactic Sugars" are the primary building blocks for defining organizational patterns.

### 3.1. `generate_team`
Defines a self-correcting loop where a **Generator** creates content and **Validators** critique it.

* **Behavior:**
    1.  Generator produces an artifact.
    2.  Validators review it in parallel.
    3.  If rejected, the Generator tries again, receiving the previous feedback and artifact.
    4.  Repeats until approved or `loop` limit is reached.

```yaml
generate_team:
  generator: Designer
  validators: [ReviewerA, ReviewerB]
  loop: 3
  inputs: [Spec]
  output: DesignDraft
```

### 3.2. `approval_gate`
Inserts a mandatory **Human-in-the-Loop** checkpoint.

* **Scope Isolation Principle (Critical):**
    * **Inside `contents` (Mutable):** Tasks that must be *re-executed* upon rejection.
    * **Outside (Immutable):** Tasks that should happen only once.
    * *Bad Pattern:* Putting "Initial Research" inside the gate. It will be re-done every time the approver says no, which is inefficient.

```yaml
approval_gate:
  approver: CTO
  target: FinalSpec
  contents:
    # Only place logic that needs to be revised here
    worker:
      agent: Architect
      output: FinalSpec
```

### 3.3. `ensemble`
Executes multiple workers in parallel (Diversity) and consolidates their outputs into a single result (Convergence).

```yaml
ensemble:
  generators: [CopywriterA, CopywriterB]
  consolidator: Editor
  samples: 2          # Runs each generator twice
  output: FinalCopy
```

### 3.4. `fan_out`
Dynamically spawns workers based on a data list.

* **Constraints:** Nested `fan_out` is **not allowed**.
* **Context Keywords:**
    * `MyInput.__key`: Binds the current iteration item (object) to the input `MyInput`.
    * `@prev`: (Serial only) References the result from the previous iteration (n-1).
    * `@history`: (Serial only) References results from all previous iterations as a list.

```yaml
fan_out:
  source: "RegionList"
  item_key: "region"
  strategy: serial
  worker:
    agent: Analyst
    inputs: ["Report@history"] # Accumulate results
    briefing: "Analyze for region: {$KEY}"
```

### 3.5. `briefing` (Context Injection)
The `briefing` block injects instructions into the team. Parameters are resolved in the following priority (Low to High):

1.  **Global:** Defined at the root of `briefing` (Applies to everyone).
2.  **Agent-Specific:** Defined under the Agent ID key (Overrides Global).
3.  **System:** Immutable values forced by the kernel (e.g., `mode`, `output`).

```yaml
briefing:
  tone: "Formal"          # Global: Applies to everyone
  Editor:
    tone: "Strict"        # Specific: Overrides for Editor only
```

---

## 4. Wiring & Data Flow

ODL uses a virtual file system for data dependency.

### 4.1. Implicit Scope Resolution
When you request an input (e.g., `inputs: ["DocA"]`), ODL looks for "DocA" in the following order:

1.  **Older Siblings:** Tasks defined *before* the current one in the same block.
2.  **Ancestors:** Artifacts produced in parent blocks.
3.  **Descendants of Older Siblings:** Artifacts produced inside a previous container (e.g., a loop that finished).

**Invisible Scopes (Out of Scope):**
* **Younger Siblings:** Tasks defined *after* the current one.
* **Cousins:** Artifacts produced in parallel branches (e.g., inside a different `parallel` arm).

### 4.2. Dynamic Variables

| Token | Description | Context |
| :--- | :--- | :--- |
| `$LOOP` | Current iteration index (1-based). | Inside `loop`, `generate_team` |
| `$KEY` | Current item key. | Inside `fan_out` |
| `$ITEM` | Current item value (Object). | Inside `fan_out` |
| `$PREV` | Result of the *previous* sibling. | Inside `serial` |
| `$HISTORY`| List of all past results in the current scope. | Inside `serial`, `loop` |

---

# Part II: Compiler & Internals (For Implementers)

This section details how the Source is compiled into the Intermediate Representation (IR).

## 5. The Compiler Pipeline

ODL compilation is a linear transformation: `Source (YAML) -> IR (JSON)`.

1.  **Parsing:** Normalizes YAML shorthand into explicit `params` and `wiring` buckets.
2.  **Syntax Validation:** Checks for forbidden characters (`__`, `_` prefix) and required fields.
3.  **Expansion (Desugaring):**
    * Recursively transforms Sugars (`generate_team`) into Primitives (`loop`, `worker`).
    * Generates **Deterministic IDs** (`stack_path`) based on the tree structure (e.g., `root/loop_0/v1`).
4.  **Resolution:**
    * Resolves Logical Names to Physical IDs (e.g., `Doc` -> `Doc#root/loop_0/v1`).
    * Handles variable substitution (`$LOOP`, `$KEY`).
5.  **Assembly:** Constructs the strongly-typed `IrComponent` object tree.

## 6. Primitive Instruction Set (OpCodes)

All high-level constructs compile down to these atomic primitives.

* **Atoms:** `worker`, `dialogue`, `approver`
* **Control:** `serial`, `parallel`, `loop`, `iterate` (fan_out implementation)
* **Logic:** `scope_resolve` (determines loop winners), `iterator_init`

## 7. Intermediate Representation (IR) Schema

The Output of `odl.compile()` is a recursive JSON structure.

```json
{
  "stack_path": "root/team_a",
  "opcode": "serial",
  "wiring": {
    "inputs": ["Spec"],
    "output": "Result"
  },
  "params": {
    "timeout": 3600
  },
  "children": [
    {
      "stack_path": "root/team_a/worker_1",
      "opcode": "worker",
      "params": { "agent": "GPT-4", "mode": "generate" },
      "wiring": { "inputs": ["Spec"], "output": "Draft" }
    }
  ]
}
```