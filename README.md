# LLMon – RV Monitor Generator from Natural Language

[![Python 3.10](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/) [![License Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

<p align="center">
  <img src="./images/logo.png" alt="LLMon logo" width="280">
</p>

LLMon is an interactive research tool that lets you:

* **📝 Describe temporal requirements in plain English** – and get runnable runtime-verification (RV) monitors back.
* **🍋 Define brand-new temporal constructs on the fly** using natural-language descriptions and rapid ambiguity-resolving workflows.
* **⚙️ Combine classical RV algorithms with LLM reasoning** to bridge the gap between natural language and formal specifications.

---

## Table of Contents  
1. [About LLMon](#about-llmon)  
2. [Why LLMon 🍋](#why-llmon-🍋)  
3. [Main Features](#main-features)  
   3.1 [Algorithmic Foundation](#algorithmic-foundation)  
4. [Installation](#installation)  
5. [Quick Start](#quick-start)  
   5.1 [Set the OpenAI API key](#set-the-openai-api-key)  
   5.2 [Choose the trace length](#choose-the-trace-length)  
   5.3 [Three interactive stages](#three-interactive-stages)  
6. [Verifying PT-LTL-Equivalent Operators](#verifying-pt-ltl-equivalent-operators)  
7. [Verifying Rule-Based Constructs (Beyond PT-LTL)](#verifying-rule-based-constructs-beyond-pt-ltl)  🍋 **NEW**  
8. [Key Project Files](#key-project-files)  
9. [Output Artifacts](#output-artifacts)  
10. [License](#license)
11.  [Contributors](#contributors)

---

## About LLMon

LLMon is the tool used in the paper **“The Power of Reframing: Using LLMs in Synthesizing RV Monitors.”**
It couples Large Language Models (LLMs) with deterministic monitor-generation code so that ambiguity is handled *with* the user, while all safety-critical synthesis remains pure Python.

> **Screenshots (placeholders)**
> ![UI shot-1](images/shot1.png)
> ![UI shot-2](images/shot2.png)

---

## Why LLMon 🍋

* **Bridging the NL–logic gap** – Engineers write specs the way they think; LLMon handles the translation.
* **Extensible temporal logic** – Users can *teach* the tool new temporal constructs in minutes.
* **Human-in-the-loop safety** – LLMs propose; exhaustive trace comparison plus your decisions dispose.
* **Single-file output** – End-to-end monitor synthesis yields a ready-to-run `monitor.py`.

---

## Main Features

* Natural-language constructs creation with automated ambiguity exploration.
* NL specification → formula conversion *or* direct formula entry.
* GUI powered by Gradio for smooth, pause-resume interaction.
* Stores every learnt operator in `operators_data.json` for future sessions.
* Outputs self-contained Python monitors.

### Algorithmic Foundation

Under the hood LLMon employs the **Havelund & Rosu past-time LTL monitor-synthesis algorithm**.
Each user-defined operator is compiled into a constant-time, constant-memory *update rule* that plugs into the classical bottom-up summary update pass, ensuring monitors remain efficient even as the logic grows.

---

## Installation

### System Requirements

* Python ≥ 3.10
* An OpenAI account & API key (`OPENAI_API_KEY`).

### Dependencies

```text
openai~=1.52.1
gradio~=5.29.0
yaml~=0.2.5
pyyaml~=6.0.2
```

### From Source

```bash
# Clone the repository
git clone https://github.com/itay99988/llmon.git
cd llmon

# (Recommended) create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install python dependencies
pip install -r requirements.txt
```

---

## Quick Start

Run the Gradio front-end and open your browser to the printed URL.

```bash
export OPENAI_API_KEY="sk-..."          # ↩︎ or set permanently in your shell
python gradio_agent.py --trace_length 5 # optional, default = 3
```

Then click the link, e.g. `http://127.0.0.1:7860`, and chat away!

### Set the OpenAI API key

LLMon talks to the OpenAI Chat Completion API.
Provide your key **once** as an environment variable:

```bash
export OPENAI_API_KEY="your-key-here"
```

### Choose the trace length

`--trace_length N` controls how long distinguishing traces may be when the tool compares alternative operator interpretations.
*Default = 3 (minimum allowed).*

### Three interactive stages

1. **Extend the logic:** add or refine temporal constructs in plain English.
2. **Describe the requirement:**

   * Option 1 – natural-language sentence (LLM translates).
   * Option 2 – direct formula (`q1`, `q2`, `S`, `H`, your new operators…).
3. **Generate the monitor:** LLMon compiles your formula plus all learnt operators into `monitor.py`.

---

## Verifying PT-LTL-Equivalent Operators

### What happens behind the scenes 🍋
1. **Expansion** – every custom construct \(𝒪\) is replaced by its *past-time LTL* equivalence template that uses only the basic PT-LTL operators `@  P  H  S`.  
2. **Dual monitor synthesis** – LLMon builds two monitors:  
   * one for the *original* formula (with \(𝒪\)),  
   * one for the *expanded* formula (without \(𝒪\)).  
3. **Exhaustive comparison** – `compare_monitors.py` runs **10 000 random traces** and checks verdict-by-verdict equality. A 100 % match gives high confidence that the operator’s update rule is correct.

---

### Reproducing the paper’s experiments
```bash
# 1️⃣  Put the full operator catalogue in place
cp operator_files/operators_data_full.json operators_data.json

# 2️⃣  Move to the experiment directory
cd past_ltl_operators_experiments

# 3️⃣  Test one construct (example: PTH)
python batch_formula_tester.py --new-op PTH --equiv "@(H({arg}))"
```


| CLI flag   | Meaning                                                                                                                                                        |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--new-op` | Token of the construct under test (e.g. `PTH`).                                                                                                                |
| `--equiv`  | **Past-time LTL template** that replaces the construct. <br>• **Unary** templates use **`{arg}`**.<br>• **Binary** templates use **`{left}`** & **`{right}`**. |

Unary template example → @(H({arg}))

Binary template example → ({left}) S ({right})

### Ready-to-run examples for all constructs in the paper
| Construct                      | Notation   | NL description (abridged)                                     | PT-LTL equivalence template                                                       | One-liner                                                                                                  |
| ------------------------------ | ---------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **weak since**                 | `q₁ WS q₂` | `q₁` holds since the last `q₂` (or from start if `q₂` never). | `(({left}) S ({right})) \|\| H(({left}))`                                         | `python batch\_formula\_tester.py --new-op WS --equiv "(({left}) S ({right}))`                              |
| **previous-time historically** | `PTH(q)`   | `q` held from start until one step before now.                | `@(H({arg}))`                                                                     | `python batch_formula_tester.py --new-op PTH --equiv "@(H({arg}))"`                                        |
| **value alternation**          | `VA(q)`    | `q` flips every step.                                         | `H(@(({arg})<->({arg})) -> (({arg}) <-> (@(!({arg})))))`                          | `python batch_formula_tester.py --new-op VA --equiv "H(@(({arg})<->({arg})) -> (({arg}) <-> (@(!({arg})))))"` |
| **consistent Boolean value**   | `CBA(q)`   | `q` never changes.                                            | `(H({arg}) \|\| H(!({arg})))`                                                     | `python batch\_formula\_tester.py --new-op CBA --equiv "(H({arg})`                                          |
| **never**                      | `N(q)`     | `q` never holds.                                              | `H(!({arg}))`                                                                     | `python batch_formula_tester.py --new-op N --equiv "(H(!({arg})))"`                                        |
| **happened before**            | `q₁ HB q₂` | If `q₂` now, then `q₁` happened earlier.                      | `H(({right}) -> P(({left})))`                                                     | `python batch_formula_tester.py --new-op HB --equiv "(H(({right}) -> P(({left}))))"`                       |
| **false since**                | `q₂ FS q₁` | After `q₁`, `q₂` has been false.                              | `P(({right})) -> (!({left}) S ({right}))`                                         | `python batch_formula_tester.py --new-op FS --equiv "P(({right})) -> (!({left}) S ({right}))"`             |
| **false before**               | `q₁ FB q₂` | Before latest `q₂`, `q₁` always false.                        | `{right} -> H(!({left}))`                                                         | `python batch_formula_tester.py --new-op falsebefore --equiv "{right} -> (H(!({left})))"`                  |
| **once at start**              | `OAS(q)`   | `q` happened at least once since start.                       | `P(H({arg}))`                                                                     | `python batch_formula_tester.py --new-op OAS --equiv "P(H({arg}))"`                                        |
| **changes only once**          | `COO(q)`   | `q` flips exactly once.                                       | `(({arg}) && (({arg}) S H(!({arg})))) \|\| (!({arg}) && (!({arg}) S H(({arg}))))` | `python batch\_formula\_tester.py --new-op COO --equiv "(({arg}) && (({arg}) S H(!({arg}))))`              |

### Helper scripts inside past_ltl_operators_experiments/

* syntax_translator.py – expands templates by replacing {arg}, {left}, {right}.

* compare_monitors.py – compares two monitors on 10 000 random traces.

* batch_formula_tester.py – generates 100 random formulas containing one construct and invokes the two scripts above automatically.

---

## Verifying Rule-Based Constructs (Beyond PT-LTL)

### What happens behind the scenes 🍋
Some custom operators cannot be expressed with past-time LTL alone.  
Instead, they are given **transition rules** that introduce *auxiliary Boolean
variables* (`a1`, `a2`, …).  
LLMon’s experiment harness:

1. **Adds** the auxiliary variables and their rules to the monitor generator.  
2. **Synthesises** two monitors  
   * one using the operator plus auxiliary variables,  
   * one using the operator’s *rule-based* expansion template.  
3. **Compares** both monitors on 10 000 random traces with
   `compare_monitors.py`, exactly as in the PT-LTL experiments.

---

### Reproducing the paper’s rule-based experiments
We show here how to run rule-based construct by demonstrating it on the `ODD` construct from the paper.
```bash
# 1️⃣  Copy the full operator catalogue into place
cp operator_files/operators_data_full.json  operators_data.json
```

```bash
# 2️⃣  Move to the rule-based experiment directory
cd rules_experiments
```

```bash
# 3️⃣  ODD construct (holds at *odd* time-steps) – set up auxiliary rules
cp rules_experiments/exp1/aux_vars_data_exp1.json  aux_vars_data.json
```

```bash
# 4️⃣  Run the experiment (100 random formulas containing ODD)
python ./batch_formula_tester.py --new-op ODD --equiv "H((a1) -> {arg})"
```

#### What the flags mean

| Flag       | Purpose                                                                                                     |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| `--new-op` | Token of the construct to test (`ODD`).                                                                     |
| `--equiv`  | Rule-based **template** that refers to auxiliary variables (here `a1`) and the operand placeholder `{arg}`. |

---

### The auxiliary-variable file `aux_vars_data.json`

For rule-based experiments this JSON file defines **how each auxiliary
variable evolves**:

```json
{
  "var_name": "a1",
  "transition_rule": "next(a1) := !a1"
}
```

* **`var_name`** – the auxiliary symbol.
* **`transition_rule`** – update rule in the form
  `next(<var>) := <Boolean expression involving existing vars>`.

In the ODD example the rule toggles `a1` every step;
the equivalence template `H((a1) -> {arg})` therefore means:

> “`{arg}` must hold on every **odd** step (when `a1` is `True`).”

---

> **Helper scripts inside `rules_experiments/`**  
> * `recursive_aux_var.py` – runtime support for **recursive auxiliary variables**.  
>   Implements the `RecursiveAuxVar` class, which evaluates self-referential
>   transition rules such as `next(a1) := !a1`.  
>   Internally it contains a light-weight parser / evaluator for past-time LTL
>   so the variable can update itself every step.  
> * `syntax_translator.py` – fills the placeholders (`{arg}`, `{left}`, `{right}`, `a1`, …) in the PT-LTL template.  
> * `compare_monitors.py` – checks verdict-by-verdict equality on 10 000 random traces.  
> * `batch_formula_tester.py` – generates 100 random formulas with the target operator and orchestrates the full test run.
---

## Key Project Files

| File                      | Purpose                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------- |
| **`prompts_code.yml`**    | All system prompts used to steer the LLM at each step. Edit to customise behaviour. |
| **`operators_data.json`** | Knowledge-base of every operator LLMon has learnt. Must live in the project root.   |




Example snippet:&#x20;

Fields

* `op_name`, `op_notation` – human & symbolic names
* `op_description` – NL semantics
* `is_unary` – operator arity
* `class_name`, `class_content` – Python code implementing the update rule

---

## Output Artifacts

After a successful run LLMon drops **`monitor.py`** in the project root – a single-file Python RV monitor for your specification. 🍋✅

---

## License

Apache License 2.0 – free to use, modify, and share.

---

## Contributors
* Itay Cohen - Bar Ilan University, Israel
* Doron Peled - Bar Ilan University, Israel
* Klaus Havelund - Jet Propulsion Laboratory/NASA, USA
* Yoav Goldberg - Bar Ilan University, Israel
