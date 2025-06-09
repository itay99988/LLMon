from openai import OpenAI
import os

client = OpenAI(
  api_key=os.environ['OPENAI_API_KEY'],
)


class Chat:
    #gpt-4o
    def __init__(self, model, temperature=0, max_tokens=2048):
        self.QUERY_LIMIT = 8
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.msg_context = []

    def reset_history(self):
        self.msg_context = []

    def pop_history(self, items_count):
        for _ in range(items_count):
            if not len(self.msg_context) == 0:
                self.msg_context.pop()

    def new_sys_message(self, sys_msg):
        self.msg_context.append({
            "role": "system",
            "content": sys_msg
        })

    def new_message(self, msg):
        self.msg_context.append({
          "role": "user",
          "content": msg
        })
        try:
            full_response = client.chat.completions.create(
              model=self.model,
              messages=self.msg_context,
              temperature=self.temperature,
              max_tokens=self.max_tokens,
              top_p=1,
              frequency_penalty=0,
              presence_penalty=0
            )
        except Exception as e:
            print(e)
            err = "Could not send the message."
            return err

        response = full_response.choices[0].message.content
        self.add_assistant_msg(response)
        return response

    def add_assistant_msg(self, ass_msg):
        self.msg_context.append({
          "role": "assistant",
          "content": ass_msg
        })
