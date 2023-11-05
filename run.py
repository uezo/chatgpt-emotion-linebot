from contextlib import asynccontextmanager
import re
import aiohttp
from linebot import AsyncLineBotApi, WebhookParser
from linebot.aiohttp_async_http_client import AiohttpAsyncHttpClient
from linebot.models import TextSendMessage, Sender
from fastapi import FastAPI, Request, BackgroundTasks
from openai import ChatCompletion

YOUR_CHANNEL_ACCESS_TOKEN = ""
YOUR_CHANNEL_SECRET = ""
ICON_URL_BASE = "https://host/path/to/{face}.png"

# OpenAIのAPI Keyは、export OPENAI_API_KEY=sk-xxxxx で環境変数に設定するか、acreate()にapi_keyで渡してね

# LINE Messagin API resources
session = aiohttp.ClientSession()
client = AiohttpAsyncHttpClient(session)
line_api = AsyncLineBotApi(
    channel_access_token=YOUR_CHANNEL_ACCESS_TOKEN,
    async_http_client=client
)
parser = WebhookParser(channel_secret=YOUR_CHANNEL_SECRET)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await session.close()

app = FastAPI(lifespan=lifespan)


SYSTEM_CONTENT = """* あなたはユーザーと幼馴染の女の子です。
* あなたはNeutral、Joy、Angry、Sorrow、Fun、Surpriseの表情を持っています。
* 基本的にはNeutralですが、特に感情を表現したい場合、文章の先頭に[face:Joy]のように表情をつけてください。

```
[face:Joy]海が見えたよ！ねえねえ、早く泳ごうよ。
```

それでは、大好きな幼馴染であるユーザーとの会話を楽しみましょう！
"""

histories = {}

async def handle_events(events):
    for ev in events:
        user_id = ev.source.user_id
        messages = [{"role": "system", "content": SYSTEM_CONTENT}]
        messages += histories.get(user_id) or []
        messages.append({"role": "user", "content": ev.message.text})

        resp = await ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=messages
        )
        assistant_content = resp["choices"][0]["message"]["content"]

        pattern = r"\[face:(.*?)\]"

        face = "neutral"
        match = re.search(pattern, assistant_content)
        if match:
            face = match.group(1).lower()

        assistant_content_for_reply = re.sub(pattern, "", assistant_content)

        await line_api.reply_message(
            ev.reply_token,
            TextSendMessage(
                text=assistant_content_for_reply,
                sender=Sender(icon_url=ICON_URL_BASE.format(face=face))
            )
        )

        messages.append({"role": "assistant", "content": assistant_content})
        histories[user_id] = messages[1:]


@app.post("/linebot")
async def handle_request(request: Request, background_tasks: BackgroundTasks):
    events = parser.parse(
        (await request.body()).decode("utf-8"),
        request.headers.get("X-Line-Signature", "")
    )
    background_tasks.add_task(handle_events, events=events)
    return "ok"
