
"""
UI for the tool's main workflow
================================================================
Launches a simple chat interface that walks the user through the
ORIG_DESC → … → CODE_EVAL states, pausing whenever the agent
asks for input.
"""

from __future__ import annotations
import gradio as gr
from formalism_translation import *
import sys, argparse
from chat import ChatGpt5

# ───────────────────────────────────────────────────────────────
#  A tiny signal that means: “the agent needs user input now”
# ───────────────────────────────────────────────────────────────

class InputNeeded(Exception):
    def __init__(self, prompt: str):
        super().__init__(prompt)
        self.prompt = prompt


# ───────────────────────────────────────────────────────────────
# IOHandler implementation for Gradio UI
# ───────────────────────────────────────────────────────────────

class GradioIOHandler(IOHandler):
    """
    • `say()` buffers every line the agent prints.
    • `ask()`  – if an input is already queued, returns it.
                – otherwise raises `InputNeeded(prompt)` to suspend
                  the FSM and hand control back to the UI.
    """

    def __init__(self):
        self._buffer: list[str] = []
        self._queued: list[str] = []

    # ------- public helpers ------------------------------------

    def feed_user_input(self, text: str) -> None:
        """Push the latest user message so that the *next* ask() can consume it."""
        self._queued.append(text)

    def flush(self) -> str:
        out = "".join(self._buffer)
        self._buffer.clear()
        return out

    def say(self, text: str = "", *, end: str = "\n") -> None:  # noqa: D401
        self._buffer.append(text + end)

    def wrap_question(self, question: str) -> str:
        return "<span class='ok'>" + question + "</span>"

    def ask(self, prompt: str = "") -> str:  # noqa: D401
        if self._queued:
            return self._queued.pop(0)
        # Show the prompt to the user and suspend execution
        self._buffer.append(self.wrap_question(prompt))
        raise InputNeeded(prompt)


# ───────────────────────────────────────────────────────────────
# A tiny step-by-step FSM runner that can be paused/resumed
# ───────────────────────────────────────────────────────────────
class AgentRunner:
    """Drives the construct-differentiation workflow one step at a time."""

    def __init__(self, ctx: Context):
        self.io = GradioIOHandler()
        prompts = PromptLibrary("prompts_code.yml")
        chat = ChatGpt5(model="gpt-5", temperature=1)
        wf = build_construct_validator(chat, self.io, prompts)

        self.ctx = ctx  # ← use the injected context
        self.state_map = wf.state_map
        self.state: str | None = "WELCOME"
        self.done: bool = False

        self._run_until_block()

    def process_user_message(self, text: str) -> str:
        """
        1. Feed the latest user reply to the IO handler.
        2. Advance the FSM until it blocks again (or finishes).
        3. Return everything the agent printed since last turn.
        """
        if self.done:
            return "[✅] Workflow already finished."

        # Provide the user’s text to the pending ask()
        self.io.feed_user_input(text)
        self._run_until_block()
        return self.io.flush()

    def _run_until_block(self) -> None:
        """Keep executing states until input is required or workflow ends."""
        while self.state:
            st = self.state_map[self.state]
            try:
                st.on_enter(self.ctx)
            except InputNeeded:
                # Agent printed a question and now waits for the user
                break

            self.state = st.next_state(self.ctx)

        if self.state is None:
            self.done = True


# ── Build the Gradio user interface ──────────────────────────────
parser = argparse.ArgumentParser(description="Gradio RV-monitor generator UI")
parser.add_argument(
    "--trace_length",
    type=int,
    default=3,
    help="Length of each synthetic trace (integer, ≥ 3, default 3)."
)
args = parser.parse_args()

if args.trace_length < 3:
    sys.exit("trace_length must be an integer ≥ 3.")

ctx = Context()
ctx["trace_length"] = args.trace_length
runner = AgentRunner(ctx)                         # global, survives across turns
first_bot_msg = runner.io.flush()
init_history  = [("", first_bot_msg)]


with gr.Blocks(css="""
.ok   { color:#46b7e3; font-weight:600; }        # ✓ / success
.warn { color:#d72638; font-weight:600; }        # ⚠ / warnings
""") as demo:
    gr.Markdown("# 🍋 LLMon - RV Monitor Generator From Natural Language 🌀")

    chatbot = gr.Chatbot(
        value=init_history,
        height=620,
        sanitize_html=False,
        allow_tags=True
    )

    txt = gr.Textbox(
        placeholder="Type your reply and press Enter …",
        show_label=False,
        container=False,
    )

    def user_submit(user_msg: str, chat_history):
        bot_reply = runner.process_user_message(user_msg)
        chat_history.append((user_msg, bot_reply))
        return chat_history, ""

    txt.submit(
        fn=user_submit,
        inputs=[txt, chatbot],
        outputs=[chatbot, txt],
    )

demo.launch(share=True)