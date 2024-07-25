import asyncio
from io import BytesIO
import secrets
from pydantic import BaseModel, Field
from aiohttp import ClientSession, FormData, MultipartWriter, BytesIOPayload
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from imageio.v3 import imwrite
import numpy as np
import re

DEFAULT_SIZE = 20

class DSU: 
    def __init__(self): 
        self.parent = {}

    def leader(self, x): 
        p = self.parent.get(x, x)
        if p == x:
            return x
        self.parent[x] = self.leader(p)
        return self.parent[x]

    def join(self, i, j):
        i = self.leader(i) 
        j = self.leader(j) 
        if i == j:
            return
        self.parent[i] = self.parent.get(j, j)

def image(size=20) -> BytesIO:
    im = np.zeros((2*size+1, 2*size+1), np.bool)
    im[1::2, 1::2] = 1
    edges = []
    for i in range(size):
        for j in range(size):
            if j != size-1: edges.append((i, j, i, j+1))
            if i != size-1: edges.append((i, j, i+1, j))
    direction_start = round(np.random.random())
    edges.remove((0, 0, direction_start, 1-direction_start))
    edges.remove((size-2+direction_start, size-1-direction_start, size-1, size-1))
    np.random.shuffle(edges)
    d = DSU()
    while edges:
        x1, y1, x2, y2 = edges.pop()
        if d.leader((x1, y1)) != d.leader((x2, y2)):
            d.join((x1, y1), (x2, y2))
            im[x1+x2+1, y1+y2+1] = 1
    b = BytesIO()
    imwrite(b, im.repeat(10, 0).repeat(10, 1), format_hint=".png")
    return BytesIO(b.getvalue())


class Settings(BaseSettings):
    token: str
    model_config = SettingsConfigDict(env_file=".env")

class Chat(BaseModel):
    id: int

class Message(BaseModel):
    chat: Chat
    text: str = Field(default="")

class Update(BaseModel):
    update_id: int
    message: None|Message

@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore

cmd = re.compile(r"(?:/start\s+|/maze\s+|\s+)(\d\d\d?)\s*$")

def suggest_size(text: str) -> int:
    if m := cmd.match(text):
        n = int(m.group(1))
        if n <= 300:
            return n
    return DEFAULT_SIZE

async def main():
    async with ClientSession("https://api.telegram.org") as s:
        offset=0
        while True:
            async with s.get("/bot" + get_settings().token + "/getUpdates", data={"timeout": 30, "offset": offset}) as r:
                for upd in (await r.json())["result"]:
                    upd = Update.model_validate(upd)
                    offset = max(offset, upd.update_id+1)
                    if not upd.message: continue
                    if upd.message.text.startswith("/start"):
                        async with s.post("/bot" + get_settings().token + "/sendMessage", data={
                            "chat_id": upd.message.chat.id,
                            "text": """\
Welcome to maze generator! Type /maze to start.
Or use /maze <size> to generate a maze with given size (from 10 to 300)."""
                        }) as r:
                            assert r.status == 200, await r.text()
                        continue
                    fd = FormData(quote_fields=False)
                    size = suggest_size(upd.message.text)
                    if size >= 200: # THANK YOU VERY MUCH, TELEGRAM LIMITATIONS
                        fd.add_field("document", image(size), filename=f"{secrets.token_hex(10)}.png")
                        method = "/sendDocument"
                    else:
                        fd.add_field("photo", image(size), filename=f"{secrets.token_hex(10)}.png")
                        method = "/sendPhoto"
                    fd.add_field("chat_id", str(upd.message.chat.id))
                    async with s.post("/bot" + get_settings().token + method, data=fd) as r:
                        assert r.status == 200, await r.text()
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())