from workflow import *
from pathlib import Path
import json, textwrap
from monitor_generator import make_monitor_code, gen_save_monitor_code

# ---------------------------------------------------------------------------
#  Main Tool Workflow - formalism translation, NL specification translation, and monitor generation stages
# ---------------------------------------------------------------------------

# Helper for (re)loading the operator catalogue
OPS_PATH = Path(__file__).with_name("operators_data.json")
with OPS_PATH.open(encoding="utf-8") as _f:
    _OPS_DATA = json.load(_f)

# ────────────────────────────────────────────────────────────────
# show catalogue & choose workflow branch
# ────────────────────────────────────────────────────────────────
class WelcomeState(BaseState):
    name = "WELCOME"
    ops_data = {}

    def _pretty_ops_md(self) -> str:
        lines = ["Welcome to LLMon! 🍋", "### 📚 Current temporal operators catalogue:"]
        for op in self.ops_data:
            lines.append(
                f"- **{op['op_name']}**  "
                f"`{op['op_notation']}`  – {op['op_description']}"
            )
        return "\n".join(lines)

    def on_enter(self, ctx: Context) -> None:
        # load operators data
        OPS_JSON = Path(__file__).with_name("operators_data.json")
        with OPS_JSON.open(encoding="utf-8") as f:
            self.ops_data = json.load(f)

        self.io.say(self._pretty_ops_md())
        self.io.say(
            textwrap.dedent(
                """
                **What would you like to do?**  
                1. ➕ *Add a new construct*  
                2. 🚀 *Generate a monitor from an existing specification*
                """
            )
        )
        choice = self.io.ask("Enter 1 or 2 → ").strip()
        self.io.flush()  # flush only this time
        ctx["welcome_choice"] = choice

    def next_state(self, ctx: Context) -> Optional[str]:
        if ctx["welcome_choice"] == "1":
            return "ORIG_DESC"
        if ctx["welcome_choice"] == "2":
            self.io.say(
                "\nHow would you like to provide the specification?\n"
                "  1. ✍️  Natural-language sentence\n"
                "  2. 🧮  Formula directly\n"
            )
            return "CHOOSE_SPEC_INPUT"
        self.io.say("I didn't understand. Let's try again.\n")
        return "WELCOME"   # loop until valid

# ── user provides original description ────────────────────────────
class OrigDescState(BaseState):
    name = "ORIG_DESC"
    # --- helper -----------------------------------------------------------
    _CODE_RE = re.compile(r"(```(?:python)?\n.*?```)", re.S)
    @staticmethod
    def _collapse_snippets(text: str) -> str:
        """
        Wrap every Markdown code-block in a <details>…</details> envelope
        so Gradio / Markdown UIs show it collapsed by default.
        """
        return OrigDescState._CODE_RE.sub(
            r"<details>\n  <summary><span class='ok'>code snippet</span></summary>\n\n\1\n</details>",
            text,
        )

    def on_enter(self, ctx: Context) -> None:

        line = self.io.ask("Please provide a new temporal‑operator description (name, notation, natural‑language semantics) and I will suggest some interpretations for it.\n")
        ctx["orig_desc"] = line

        # we ask now for alternative interpretation
        tmpl = self.prompts.get("produce_update_rules_new")
        self.chat.reset_history()
        reply_raw = self.chat.new_message(tmpl.format(ctx["orig_desc"])).strip()

        reply = self._collapse_snippets(reply_raw)

        # flush only this time
        self.io.flush()
        self.io.say(reply)


    def next_state(self, ctx: Context) -> Optional[str]:
        return "ASK_ALT_INTRP_DEC"


# ────────────────────────────────────────────────────────────────
# Ask whether the user wants to add an alternative interpretation.
# ────────────────────────────────────────────────────────────────
class AskAltInterpDecisionState(BaseState):
    name = "ASK_ALT_INTRP_DEC"

    def on_enter(self, ctx: Context) -> None:
        answer = self.io.ask(
            "Would you like to provide your own alternative interpretation? "
            "It will be considered version 5.  (Y/N) → ").strip().lower()
        ctx["wants_alt"] = answer.startswith("y")

    def next_state(self, ctx: Context) -> Optional[str]:
        return "COLLECT_ALT_INTRP" if ctx["wants_alt"] else "ALT_INTRP"


# ────────────────────────────────────────────────────────────────
# Collect the alternative description provided by the user (version 5).
# ────────────────────────────────────────────────────────────────
class CollectAltInterpState(BaseState):
    """Collect the alternative description provided by the user (version 5)."""
    name = "COLLECT_ALT_INTRP"
    _CODE_RE = re.compile(r"(```(?:python)?\n.*?```)", re.S)

    def on_enter(self, ctx: Context) -> None:
        ctx["user_alt_desc"] = self.io.ask(
            "Please write your alternative description → "
        ).strip()
        ctx["has_user_alt"] = True

    def next_state(self, ctx: Context) -> Optional[str]:
        return "ALT_INTRP"


# ── user chooses a primary interpretation ─────────────────────────────────────
class AltInterp(BaseState):
    name = "ALT_INTRP"
    _BACKTICK_RE = re.compile(r"`([^`]+)`", re.S)

    def on_enter(self, ctx: Context) -> None:
        max_v = "5" if ctx.get("has_user_alt") else "4"
        choice = self.io.ask(
            f"\nChoose a primary interpretation (1-{max_v}) that will be compared "
            "to all the others → "
        ).strip()
        ctx["update_rule_choice"] = choice

    def next_state(self, ctx: Context) -> Optional[str]:
        return "INTERP_TO_CODE_COMPARE"


# ── LLM creates comparison codes ─────────────────────────────────────
CODE_BLOCK_RE = re.compile(r"```(?:python)?\n(.*?)```", re.S)
class AltCodeCompareState(BaseState):
    name = "INTERP_TO_CODE_COMPARE"

    def on_enter(self, ctx: Context) -> None:
        # start with code creation
        user_interp = ""
        ignore_instructions = ""

        if "has_user_alt" in ctx:
            user_interp = "create a python code also for the following new interpretation (inserted by the user): " + ctx["user_alt_desc"] + ". It is considered as version 5."

        ignore_list = self.io.ask("If there are code versions that you wish to ignore, specify them now. \n Otherwise press 'enter'→")
        if len(ignore_list) > 3:
            ignore_instructions = f"From now on, ignore the following code versions:\n{ignore_list}"

        tmpl = self.prompts.get("create_rules_code")
        reply = self.chat.new_message(tmpl.format(ctx["update_rule_choice"], ignore_instructions, user_interp)).strip()

        tmpl_code_create = self.prompts.get("create_comp_code")
        tmpl_code_create = tmpl_code_create.format(trace_length = ctx["trace_length"])
        reply = self.chat.new_message(tmpl_code_create).strip()

        match = CODE_BLOCK_RE.search(reply)
        if not match:
            self.io.say("Could not find a Python code block in LLM reply:\n" + reply)
            sys.exit(1)
        code = match.group(1)
        ctx["compare_code"] = code
        self.io.say("\n⇢ Simulation code extracted.")

    def next_state(self, ctx: Context) -> Optional[str]:
        return "CODE_EVAL"

# ── run comparison code, collect distinguishing traces, and have LLM analysis ───────────────
class CodeEvalState(BaseState):
    """Run comparison code, show its stdout, let the LLM analyze the output, and ask for user's decision."""

    name = "CODE_EVAL"
    _JSON_RE = re.compile(r"\{[^{}]+\}", re.S)
    _TRACE_RE = re.compile(r"^Trace:\s*(.+?)=>\s*(.+)$")
    _PROP_RE = re.compile(r"^(.+?)\s*=\s*\((.+)\)$")
    _VERSION_RE = re.compile(r"Version\s+([A-Za-z0-9_-]+)\s*:\s*(True|False)", re.I)
    _COLORS = ["#f29f67", "#6cc4a1", "#6aa3d9", "#f2c44f", "#c78bd6", "#f07b7b"]
    _STYLES = {
        "chunk": "display:flex;flex-direction:column;gap:8px;margin:8px 0;",
        "vis": "display:inline-flex;align-items:flex-start;gap:8px;max-width:100%;overflow-x:auto;padding-bottom:2px;flex-wrap:nowrap;",
        "steps": "display:flex;align-items:center;gap:8px;flex-wrap:nowrap;",
        "ellipse": "min-width:120px;height:64px;padding:4px 12px;border-radius:999px;border:2px solid #2f3a41;background:#f9fbfc;display:flex;align-items:center;justify-content:center;",
        "props": "display:flex;flex-wrap:wrap;gap:4px;align-items:center;justify-content:center;",
        "pill": "display:inline-flex;align-items:center;justify-content:center;border-radius:999px;font-size:0.8rem;font-weight:600;color:#1f2a32;border:2px solid rgba(31,42,50,0.25);padding:0 12px;height:26px;min-width:48px;",
        "pill_false": "background:#c7cdd3;color:#3e4a54;",
        "acceptance": "height:64px;padding:6px 10px;border-radius:16px;background:transparent;display:flex;flex-direction:row;align-items:center;gap:10px;align-self:flex-start;",
        "status": "display:flex;align-items:center;justify-content:space-between;gap:10px;height:30px;padding:0 15px;border-radius:12px;background:rgba(31,42,50,0.08);white-space:nowrap;font-size:0.9rem;",
        "badge_accept": "padding:3px 8px;border-radius:999px;font-weight:600;color:#fff;background:#2f9d68;font-size:0.87rem;",
        "badge_reject": "padding:3px 8px;border-radius:999px;font-weight:600;color:#fff;background:#cf3d2e;font-size:0.87rem;",
        "details": "margin:4px 0 0 0;",
        "summary": "cursor:pointer;color:#e1e4e6;font-size:1rem;",
        "stack": "display:flex;flex-direction:column;gap:8px;margin-top:6px;",
        "fallback": "background:rgba(207,61,46,0.08);border:1px solid rgba(207,61,46,0.35);border-radius:10px;padding:8px 10px;",
    }
    _ARROW_SVG = (
        "<svg width='44' height='12' aria-hidden='true' style='flex:0 0 auto;margin:0 -8px;'>"
        "<line x1='0' y1='6' x2='28' y2='6' stroke='#d6dbe0' stroke-width='2.5' />"
        "<polygon points='28,0 44,6 28,12' fill='#d6dbe0' />"
        "</svg>"
    )

    @staticmethod
    def _parse_trace_line(line: str):
        m = CodeEvalState._TRACE_RE.match(line.strip())
        if not m:
            raise ValueError("Not a trace line")
        props_part, versions_part = m.group(1), m.group(2)

        props = []
        for entry in (p.strip() for p in props_part.split(";") if p.strip()):
            pm = CodeEvalState._PROP_RE.match(entry)
            if not pm:
                raise ValueError(f"Could not parse proposition segment: {entry}")
            name = pm.group(1).strip()
            values_raw = [v.strip() for v in pm.group(2).split(",") if v.strip()]
            values = []
            for v in values_raw:
                if re.fullmatch(r"true", v, re.I):
                    values.append(True)
                elif re.fullmatch(r"false", v, re.I):
                    values.append(False)
                else:
                    raise ValueError(f"Value '{v}' must be True or False.")
            props.append({"name": name, "values": values})

        length = len(props[0]["values"])
        for p in props:
            if len(p["values"]) != length:
                raise ValueError("All propositions must have the same number of steps.")

        versions = []
        for vm in CodeEvalState._VERSION_RE.finditer(versions_part):
            versions.append(
                {
                    "name": vm.group(1),
                    "accepted": re.fullmatch(r"true", vm.group(2), re.I) is not None,
                }
            )
        if not versions:
            raise ValueError("No version verdicts found.")

        return {"props": props, "length": length, "versions": versions}

    @classmethod
    def _build_trace_html(cls, parsed: dict) -> str:
        styles = cls._STYLES
        color_map = {p["name"]: cls._COLORS[idx % len(cls._COLORS)] for idx, p in enumerate(parsed["props"])}

        def render_step(t: int) -> str:
            prop_html = []
            for p in parsed["props"]:
                state = p["values"][t]
                color = color_map[p["name"]] if state else ""
                style = styles["pill"] + (f"background:{color};" if state else styles["pill_false"])
                prop_html.append(f"<div style=\"{style}\">{p['name']}</div>")
            return (
                "<div style='display:flex;flex-direction:column;align-items:center;gap:2px;'>"
                f"<div style=\"{styles['ellipse']}\">"
                f"<div style=\"{styles['props']}\">{''.join(prop_html)}</div>"
                "</div>"
                "</div>"
            )

        steps = []
        for t in range(parsed["length"]):
            if t > 0:
                steps.append(cls._ARROW_SVG)
            steps.append(render_step(t))

        verdicts = "".join(
            f"<div style=\"{styles['status']}\"><span>Formula {v['name']}</span>"
            f"<span style=\"{styles['badge_accept'] if v['accepted'] else styles['badge_reject']}\">"
            f"{'Accept' if v['accepted'] else 'Reject'}</span></div>"
            for v in parsed["versions"]
        )

        return (
            f"<div style=\"{styles['vis']}\">"
            f"<div style=\"{styles['steps']}\">{''.join(steps)}</div>"
            f"<aside style=\"{styles['acceptance']}\">{verdicts}</aside>"
            "</div>"
        )

    @classmethod
    def _collapse_traces(cls, raw: str) -> str:
        def _wrap(chunk: list[str]) -> str:
            def _render_line(line: str) -> str:
                try:
                    parsed = cls._parse_trace_line(line)
                    return cls._build_trace_html(parsed)
                except Exception:
                    return f"<div style=\"{cls._STYLES['fallback']}\">{line}</div>"

            first = _render_line(chunk[0])
            if len(chunk) == 1:
                return f"<div style=\"{cls._STYLES['chunk']}\">{first}</div>"

            rest_visuals = "".join(_render_line(line) for line in chunk[1:])
            details = (
                f"<details style=\"{cls._STYLES['details']}\">"
                f"<summary style=\"{cls._STYLES['summary']}\">"
                f"More traces ({len(chunk) - 1})"
                "</summary>"
                f"<div style=\"{cls._STYLES['stack']}\">{rest_visuals}</div>"
                "</details>"
            )
            return f"<div style=\"{cls._STYLES['chunk']}\">{first}{details}</div>"

        output_lines: list[str] = []
        trace_chunk: list[str] = []

        for line in raw.splitlines():
            if line.lstrip().startswith("Trace:"):
                trace_chunk.append(line)
            else:
                if trace_chunk:  # flush the finished bulk
                    output_lines.append(_wrap(trace_chunk))
                    trace_chunk = []
                output_lines.append(line)  # keep non-trace line as-is

        if trace_chunk:  # trailing bulk
            output_lines.append(_wrap(trace_chunk))

        return "\n".join(output_lines)

    def on_enter(self, ctx: Context) -> None:
        import io as _io, contextlib as _cl

        buf = _io.StringIO()
        ns = {}
        printed_lines = []

        def _capture_print(*args, **kwargs):
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            line = sep.join(str(a) for a in args) + end
            printed_lines.append(line)
            buf.write(line)
        try:
            ns["print"] = _capture_print
            with _cl.redirect_stdout(buf), _cl.redirect_stderr(buf):
                exec(ctx["compare_code"], ns)
        except Exception as exc:
            self.io.say(f"Execution error: {exc}")
            sys.exit(1)

        raw_output = buf.getvalue().strip()
        if not raw_output and printed_lines:
            raw_output = "".join(printed_lines).strip()
        if not raw_output:
            for key in ("output", "result", "traces", "trace_output", "sim_output", "lines"):
                if key in ns:
                    value = ns[key]
                    if isinstance(value, list):
                        raw_output = "\n".join(str(v) for v in value).strip()
                    else:
                        raw_output = str(value).strip()
                    if raw_output:
                        break
        ctx["sim_output"] = self._collapse_traces(raw_output) if raw_output else ""

        if ctx["sim_output"]:
            self.io.say("\n\nDifferentiation analysis:\n" + ctx["sim_output"])

            tmpl = self.prompts.get("analyze_comp_output")
            explain = self.chat.new_message(tmpl.format(traces=ctx["sim_output"]))
            self.io.say(explain)
        else:
            self.io.say("\n\nSimulation code produced no output. Exiting")

    def next_state(self, ctx: Context) -> Optional[str]:
        if ctx["sim_output"]:
            return "ANALYZE_TRACES"
        else:
            return None


# ── version selection, operator data export to knowledge base ────────────
class AnalyzeTracesState(BaseState):

    name = "ANALYZE_TRACES"
    _JSON_RE = re.compile(r"\{[^{}]+\}", re.S)
    _OPS_PATH = Path(__file__).with_name("operators_data.json")

    # ------------ helpers --------------------------------------------------
    @staticmethod
    def _compile_ok(code: str) -> bool:
        try:
            compile(code, "<operator>", "exec")
            return True
        except SyntaxError as e:
            return False

    def _get_operator_json(self, choice: str):
        """Ask the LLM to package the chosen interpretation and return JSON."""
        tmpl = self.prompts.get("get_op_info_json")
        reply = self.chat.new_message(tmpl.format(choice))
        try:
            return json.loads(reply)
        except json.JSONDecodeError:
            m = self._JSON_RE.search(reply)
            if m:
                return json.loads(m.group(0))
            raise ValueError("LLM did not return a parsable JSON.")

    def on_enter(self, ctx: Context) -> None:
        # 1. User chooses version or none
        self.io.say("")
        choice = self.io.ask("\nWhich version do you want to adopt? (1-5 or 'none' if you wish to start over with a new description) → ").strip().lower()
        ctx["code_eval_choice"] = choice
        if choice == "none":
            return  # handled in next_state
        if choice not in ("1", "2", "3", "4", "5"):
            self.io.say("Unrecognised option; assuming refinement required.")
            ctx["code_eval_choice"] = "none"
            return

        # 2. Loop until we have compilable code or user quits
        while True:
            try:
                op_json = self._get_operator_json(choice)
            except ValueError as err:
                self.io.say(f"❌ {err}")
                if self.io.ask("Retry? (y/n) → ").strip().lower() == "y":
                    continue
                ctx["code_eval_choice"] = "none"
                return

            code_str = op_json["class_content"]
            if self._compile_ok(code_str):
                break  # success!
            self.io.say("❌ The generated Python class has syntax errors.")
            if self.io.ask("Let the model try again? (y/n) → ").strip().lower() != "y":
                ctx["code_eval_choice"] = "none"
                return

        # 3. Append new operator to operators_data.json
        try:
            with self._OPS_PATH.open(encoding="utf-8") as f:
                ops = json.load(f)
        except FileNotFoundError:
            ops = []

        ops.append(
            {
                "op_name": op_json["op_name"],
                "op_notation": op_json["op_notation"],
                "op_description": op_json["op_description"],
                "is_unary": op_json["is_unary"],
                "class_name": op_json["class_name"],
                "class_content": op_json["class_content"],
            }
        )
        with self._OPS_PATH.open("w", encoding="utf-8") as f:
            json.dump(ops, f, indent=2, ensure_ascii=False)

        ctx["operator_json"] = op_json
        self.io.say("✅ Operator added to the catalogue!")

    def next_state(self, ctx: Context) -> Optional[str]:
        if ctx.get("code_eval_choice") == "none":
            return "ORIG_DESC"   # go refine description
        return "WELCOME"         # back to the start with updated list


# ────────────────────────────────────────────────────────────────
# ask how the user wants to supply the specification (NL or formula)
# ────────────────────────────────────────────────────────────────
class ChooseSpecInputState(BaseState):
    name = "CHOOSE_SPEC_INPUT"

    def on_enter(self, ctx: Context) -> None:
        choice = self.io.ask("Enter 1 or 2 → ").strip()
        ctx["spec_input_choice"] = choice

    def next_state(self, ctx: Context) -> Optional[str]:
        example = (
            "*Example*: “Whenever the user **writes** to a file, previously "
            "the file was **created**, and it has not been **closed** since it "
            "was opened.”\n"
        )

        if ctx["spec_input_choice"] == "1":
            self.io.say("Please write your temporal specification in plain English.\n")
            self.io.say(example)
            return "TRANSLATE_SPEC"
        else:
            return "INSERT_FORMULA"


# ────────────────────────────────────────────────────────────────
# translate a free-text specification into a formula
# ────────────────────────────────────────────────────────────────
from monitor_generator import make_monitor_code, find_distinguishing_traces   # already present earlier

class TranslateSpecState(BaseState):
    name = "TRANSLATE_SPEC"
    _FORM_ERR = "❌ The translated formula is syntactically invalid."

    # helper
    def _ops_json(self) -> str:
        return json.dumps(_OPS_DATA, indent=2, ensure_ascii=False)

    @staticmethod
    def _valid_formula(f: str) -> bool:
        try:
            make_monitor_code(f)
            return True
        except:
            return False

    @staticmethod
    def _render_trace_block(trace_line: str) -> str:
        try:
            parsed = CodeEvalState._parse_trace_line(trace_line)
            versions = parsed.get("versions", [])
            accepts = [f"Formula {v['name']}" for v in versions if v["accepted"]]
            rejects = [f"Formula {v['name']}" for v in versions if not v["accepted"]]
            label = (
                "<div style='margin:4px 0 6px;font-weight:600;'>"
                f"A trace that satisfies {', '.join(accepts) if accepts else 'none'} "
                f"and rejects {', '.join(rejects) if rejects else 'none'}:"
                "</div>"
            )
            return "<div style='margin:8px 0;'>" + label + CodeEvalState._build_trace_html(parsed) + "</div>"
        except Exception:
            return f"<div style='margin:8px 0;'>{trace_line}</div>"

    @classmethod
    def _render_pairwise_comparisons(cls, formulas: list[str]) -> str:
        blocks = []
        for i in range(len(formulas)):
            for j in range(i + 1, len(formulas)):
                title = f"Comparison: formula {i+1} vs. formula {j+1}"
                diffs = find_distinguishing_traces(formulas[i], formulas[j], i + 1, j + 1)
                if not diffs:
                    body = "<div style='margin:6px 0;'>The two formulas are equivalent.</div>"
                else:
                    traces_html = []
                    for key in ("diff1", "diff2"):
                        if key in diffs:
                            traces_html.append(cls._render_trace_block(diffs[key]))
                    body = "<div style='margin:6px 0;'>" + "".join(traces_html) + "</div>"
                blocks.append(
                    "<details style='margin:6px 0;'>"
                    f"<summary style='cursor:pointer;font-weight:600;'>{title}</summary>"
                    f"{body}"
                    "</details>"
                )
        return "".join(blocks)

    def on_enter(self, ctx: Context) -> None:
        nl_spec = self.io.ask("Your specification in natural language → ").strip()

        prompt_tpl = self.prompts.get("spec_translation")
        prompt = prompt_tpl.format(
            new_constructs=self._ops_json(),
            nl_spec=nl_spec,
        )

        self.chat.reset_history()
        ctx["translation_success"] = False       # default

        for _ in range(2):                       #  ≤ 2 attempts
            reply = self.chat.new_message(prompt)

            m = re.search(r"\{[^{}]+\}", reply, re.S)
            if not m:
                self.io.say("LLM returned no JSON. Retrying…")
                if len(self.chat.msg_context) >= 2:
                    self.chat.pop_history(2)
                continue

            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                self.io.say("JSON parsing failed. Retrying…")
                if len(self.chat.msg_context) >= 2:
                    self.chat.pop_history(2)
                continue

            raw_formulas = data.get("formulas", [])
            mapping = data.get("var_mapping", "(no mapping)")
            is_ambiguous = bool(data.get("is_ambiguous", False))

            if isinstance(raw_formulas, str):
                raw_formulas = [raw_formulas]

            formulas = [
                f.strip()
                for f in raw_formulas
                if isinstance(f, str) and f.strip()
            ]
            valid_formulas = [f for f in formulas if self._valid_formula(f)]

            if valid_formulas:
                self.io.say("\n### Variable mapping\n" + mapping)
                if len(valid_formulas) == 1:
                    formula = valid_formulas[0]
                    self.io.say("\n### Translated formula\n```text\n" + formula + "\n```")
                    ctx["formula"] = formula
                    ctx["needs_formula_selection"] = False
                    ctx["translation_success"] = True
                    break

                if is_ambiguous:
                    self.io.say("\nThe specification appears ambiguous. Possible formulas:")
                else:
                    self.io.say("\nMultiple translations were returned. Possible formulas:")

                lines = [f"{i + 1}. {f}" for i, f in enumerate(valid_formulas)]
                self.io.say("\n```text\n" + "\n".join(lines) + "\n```")

                if is_ambiguous:
                    comparisons_html = self._render_pairwise_comparisons(valid_formulas)
                    if comparisons_html:
                        self.io.say("\nTo better understand the differences between the different formulas, see the comparisons below:\n" + comparisons_html)

                if is_ambiguous:
                    ctx["ambiguous_formulas"] = valid_formulas
                    ctx["needs_formula_selection"] = True
                    ctx["translation_success"] = True
                    break

                ctx["formula"] = valid_formulas[0]
                ctx["needs_formula_selection"] = False
                ctx["translation_success"] = True
                break

            # formula received but could not be parsed
            self.io.say(self._FORM_ERR)
            if len(self.chat.msg_context) >= 2:
                self.chat.pop_history(2)

    def next_state(self, ctx: Context) -> Optional[str]:
        if ctx.get("translation_success"):
            return "FORMULA_SELECTION" if ctx.get("needs_formula_selection") else "CONFIRM_FORMULA"
        return "TRANSLATE_SPEC"

# ────────────────────────────────────────────────────────────────
# User confirmation for the formula
# ────────────────────────────────────────────────────────────────
class FormulaSelectionState(BaseState):
    name = "FORMULA_SELECTION"

    def on_enter(self, ctx: Context) -> None:
        formulas = ctx.get("ambiguous_formulas", [])
        if not formulas:
            ctx["formula"] = None
            ctx["formula_selection_ok"] = False
            return

        while True:
            choice = self.io.ask("Choose a formula number: ").strip()
            try:
                idx = int(choice) - 1
            except ValueError:
                idx = -1
            if 0 <= idx < len(formulas):
                ctx["formula"] = formulas[idx]
                ctx["formula_selection_ok"] = True
                break
            self.io.say("Please enter a valid number from the list.")

    def next_state(self, ctx: Context) -> Optional[str]:
        return "GENERATE_MONITOR" if ctx.get("formula_selection_ok") else "FORMULA_SELECTION"


class ConfirmFormulaState(BaseState):
    name = "CONFIRM_FORMULA"

    def on_enter(self, ctx: Context) -> None:
        formula = ctx["formula"]
        ans = self.io.ask("Is this formula OK? (Y/N) → ").strip().lower()
        ctx["formula_ok"] = ans.startswith("y")

    def next_state(self, ctx: Context) -> Optional[str]:
        return "GENERATE_MONITOR" if ctx["formula_ok"] else "TRANSLATE_SPEC"

# ────────────────────────────────────────────────────────────────
# Ask for a formula & validate its syntax
# ────────────────────────────────────────────────────────────────
class InsertFormulaState(BaseState):
    name = "INSERT_FORMULA"

    def _valid_formula(self, s: str) -> bool:
        try:
            make_monitor_code(s)
            return True
        except SyntaxError as e:
            self.io.say(f"❌ Syntax error: {e}")
            return False

    def on_enter(self, ctx: Context) -> None:
        while True:
            formula = self.io.ask("\nEnter a structured formula using the operators above. Use q1, q2.. for boolean variables. → ").strip()
            if self._valid_formula(formula):
                ctx["formula"] = formula
                break
            self.io.say("Please try again…")

    def next_state(self, ctx: Context) -> Optional[str]:
        return "GENERATE_MONITOR"


# ────────────────────────────────────────────────────────────────
# generate monitor.py or exit on error
# ────────────────────────────────────────────────────────────────
class GenerateMonitorState(BaseState):
    name = "GENERATE_MONITOR"
    success = False

    def on_enter(self, ctx: Context) -> None:
        formula = ctx["formula"]
        outfile = "monitor.py"
        try:
            gen_save_monitor_code(formula, outfile)
        except SyntaxError:
            self.io.say("😢 Failed to generate a monitor because of a syntax error. Please try again.")
            self.success = False

        self.io.say(f"Success🎉\n Monitor for formula `{formula}` written to **{outfile}**")
        self.success = True

    def next_state(self, ctx: Context) -> Optional[str]:
        if self.success:
            return None
        else:
            return "CHOOSE_SPEC_INPUT"


# ---------------------------------------------------------------------------
# Workflow container
# ---------------------------------------------------------------------------

class Workflow:
    def __init__(self, *states: BaseState):
        self.state_map = {s.name: s for s in states}

    def run(self, start: str, ctx: Optional[Context] = None) -> None:
        ctx = ctx or Context()
        current = start
        while current:
            state = self.state_map[current]
            state.on_enter(ctx)
            current = state.next_state(ctx)


# ---------------------------------------------------------------------------
# Init the main workflow as an object with all possible states
# ---------------------------------------------------------------------------
def build_construct_validator(chat: Chat, io: IOHandler, prompts: PromptLibrary) -> Workflow:
    return Workflow(
        WelcomeState(chat, io, prompts),
        OrigDescState(chat, io, prompts),
        AskAltInterpDecisionState(chat, io, prompts),
        CollectAltInterpState(chat, io, prompts),
        AltInterp(chat, io, prompts),
        AltCodeCompareState(chat, io, prompts),
        CodeEvalState(chat, io, prompts),
        AnalyzeTracesState(chat, io, prompts),
        ChooseSpecInputState(chat, io, prompts),
        TranslateSpecState(chat, io, prompts),
        FormulaSelectionState(chat, io, prompts),
        ConfirmFormulaState(chat, io, prompts),
        InsertFormulaState(chat, io, prompts),
        GenerateMonitorState(chat, io, prompts),
    )
