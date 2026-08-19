from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import ChatRequest, ChatResponse, EndRequest, Analytics
from session_store import store
from agent import get_reply
from analytics import build_analytics
from config import MOCK_MODE

app = FastAPI(title="Northstar Homes AI Sales Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/mode")
def mode():
    return {"mock_mode": MOCK_MODE}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    session = store.get_or_create(req.session_id, channel=req.channel)
    if session.ended:
        raise HTTPException(status_code=400, detail="Conversation already ended")
    session.channel = req.channel

    reply = get_reply(session, req.message)

    ended = session.state["opted_out"]  # opt-out is a hard, immediate close
    return ChatResponse(session_id=req.session_id, reply=reply, ended=ended)


@app.post("/api/end", response_model=Analytics)
def end(req: EndRequest):
    session = store.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.ended = True
    return build_analytics(session)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
