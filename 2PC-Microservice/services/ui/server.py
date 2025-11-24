from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, time, jwt, grpc, uuid

import gateway_pb2 as gp
import gateway_pb2_grpc as gpg
import auth_pb2 as ap
import room_pb2 as rp
import presence_pb2 as pp
import message_pb2 as mp


# -----------------------------------------------------
# Config
# -----------------------------------------------------
GATEWAY_ADDR = os.getenv("GATEWAY_ADDR", "gateway:50055")
COOKIE_NAME = "sms_token"
DISPLAY_NAME_COOKIE = "sms_display_name"
COORDINATOR_ID = os.getenv("NODE_ID", "ui-coordinator")


# -----------------------------------------------------
# FastAPI setup
# -----------------------------------------------------
app = FastAPI(title="SMS UI")
app.mount("/static", StaticFiles(directory="services/ui/static"), name="static")
templates = Jinja2Templates(directory="services/ui/templates")


# -----------------------------------------------------
# Helper
# -----------------------------------------------------
def stub():
    return gpg.GatewayServiceStub(grpc.insecure_channel(GATEWAY_ADDR))


def parse_user_id(token: str):
    try:
        return jwt.decode(token, options={"verify_signature": False}).get("sub")
    except:
        return None


def get_token(request: Request):
    return request.cookies.get(COOKIE_NAME)


def require_auth(request: Request):
    tok = get_token(request)
    if not tok:
        raise HTTPException(401, "not authenticated")
    uid = parse_user_id(tok)
    if not uid:
        raise HTTPException(401, "bad token")
    return uid


# -----------------------------------------------------
# Pages
# -----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    tok = get_token(request)
    if tok and parse_user_id(tok):
        return RedirectResponse("/app", 302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
def app_page(request: Request):
    uid = require_auth(request)
    display = request.cookies.get(DISPLAY_NAME_COOKIE, "")

    try:
        u = stub().GetUser(ap.UserId(user_id=uid))
        if u.display_name:
            display = u.display_name
    except:
        pass

    return templates.TemplateResponse(
        "app.html",
        {"request": request, "user_id": uid, "display_name": display},
    )


# -----------------------------------------------------
# LOGIN + REGISTER — EXACTLY AS ORIGINAL PROJECT
# -----------------------------------------------------
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    resp = stub().Register(ap.RegisterRequest(username=username, password=password))

    if not resp.success:
        raise HTTPException(400, "registration failed")

    return RedirectResponse("/", 302)


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    resp = stub().Login(ap.LoginRequest(username=username, password=password))

    if not resp.success:
        raise HTTPException(401, "invalid credentials")

    out = RedirectResponse("/app", 302)
    out.set_cookie(COOKIE_NAME, resp.token, httponly=True)
    out.set_cookie(DISPLAY_NAME_COOKIE, resp.display_name)
    return out


# -----------------------------------------------------
# 2PC MESSAGE APPEND
# -----------------------------------------------------
@app.post("/api/message/append")
async def api_append(request: Request, payload: dict):
    uid = require_auth(request)

    rid = payload.get("room_id")
    text = payload.get("text", "")
    tx_id = str(uuid.uuid4())
    idem = f"web-{int(time.time()*1000)}"

    s = stub()

    print(f"[2PC] Coordinator → PrepareAppend (tx: {tx_id})")

    prep = s.PrepareAppend(
        mp.PrepareAppendReq(
            transaction_id=tx_id,
            room_id=rid,
            user_id=uid,
            text=text,
            idempotency_key=idem,
        )
    )
    if not prep.success:
        raise HTTPException(400, prep.error)

    print(f"[2PC] Coordinator → CommitAppend (tx: {tx_id})")

    commit = s.CommitAppend(mp.CommitAppendReq(transaction_id=tx_id))
    if not commit.success:
        print(f"[2PC] Coordinator → AbortAppend (tx: {tx_id})")
        s.AbortAppend(mp.AbortAppendReq(transaction_id=tx_id))
        raise HTTPException(400, commit.error)

    return {"ok": True, "offset": commit.committed_offset}


# -----------------------------------------------------
# LIST MESSAGES
# -----------------------------------------------------
@app.get("/api/message/list")
async def api_list(request: Request, room_id: str, from_offset: int = 0, limit: int = 100):
    require_auth(request)
    msgs = list(stub().List(mp.ListReq(room_id=room_id, from_offset=from_offset, limit=limit)))

    return {
        "messages": [
            {
                "offset": m.offset,
                "ts_ms": m.ts_ms,
                "user_id": m.user_id,
                "text": m.text,
            }
            for m in msgs
        ]
    }

