from concurrent import futures
import os
import grpc

from common.config import AUTH_ADDR, ROOM_ADDR, PRESENCE_ADDR, MESSAGE_ADDR, GATEWAY_BIND

# Flat stubs
import gateway_pb2 as gp
import gateway_pb2_grpc as gpg

import auth_pb2 as ap
import auth_pb2_grpc as apg
import room_pb2 as rp
import room_pb2_grpc as rpg
import presence_pb2 as pp
import presence_pb2_grpc as ppg
import message_pb2 as mp
import message_pb2_grpc as mpg

# Node ID for coordinator logs
NODE_ID = os.getenv("NODE_ID", "gateway-coordinator")


class Gateway(gpg.GatewayServiceServicer):
    def __init__(self):
        # Stubs to other services
        self.auth = apg.AuthServiceStub(grpc.insecure_channel(AUTH_ADDR))
        self.room = rpg.RoomServiceStub(grpc.insecure_channel(ROOM_ADDR))
        self.pres = ppg.PresenceServiceStub(grpc.insecure_channel(PRESENCE_ADDR))
        self.msg = mpg.MessageServiceStub(grpc.insecure_channel(MESSAGE_ADDR))

    # =============================================================
    # AUTH
    # =============================================================
    def Register(self, req, ctx):
        return self.auth.Register(req)

    def Login(self, req, ctx):
        return self.auth.Login(req)

    def Logout(self, tok, ctx):
        return self.auth.Logout(tok)

    def GetUser(self, req, ctx):
        return self.auth.GetUser(req)

    # =============================================================
    # ROOMS
    # =============================================================
    def CreateRoom(self, req, ctx):
        return self.room.CreateRoom(req)

    def JoinRoom(self, req, ctx):
        return self.room.JoinRoom(req)

    def LeaveRoom(self, req, ctx):
        return self.room.LeaveRoom(req)

    def ListRooms(self, _req, ctx):
        for r in self.room.ListRooms(rp.Empty()):
            yield r

    def ListMembers(self, rid, ctx):
        for m in self.room.ListMembers(rid):
            yield m

    # =============================================================
    # PRESENCE
    # =============================================================
    def Heartbeat(self, hb, ctx):
        return self.pres.Heartbeat(hb)

    def SubscribePresence(self, rid, ctx):
        for ev in self.pres.Subscribe(rid):
            yield ev

    def Roster(self, rid, ctx):
        return self.pres.Roster(rid)

    # =============================================================
    # NORMAL MESSAGING
    # =============================================================
    def Append(self, req, ctx):
        return self.msg.Append(req)

    def List(self, req, ctx):
        for m in self.msg.List(req):
            yield m

    # =============================================================
    # -------------- 2PC IMPLEMENTATION (Coordinator) --------------
    # =============================================================

    def PrepareAppend(self, req, ctx):
        # --- SERVER-SIDE Log: Gateway receiving RPC from UI ---
        print(
            f"Phase Voting of Node {NODE_ID} runs RPC PrepareAppend "
            f"called by Phase Coordinator of Node ui-coordinator"
        )

        # --- CLIENT-SIDE Log: Gateway calling message-service ---
        print(
            f"Phase Voting of Node {NODE_ID} sends RPC PrepareAppend "
            f"to Phase Voting of Node message-service"
        )

        return self.msg.PrepareAppend(req)

    def CommitAppend(self, req, ctx):
        # --- SERVER-SIDE Log ---
        print(
            f"Phase Decision of Node {NODE_ID} runs RPC CommitAppend "
            f"called by Phase Coordinator of Node ui-coordinator"
        )

        # --- CLIENT-SIDE Log ---
        print(
            f"Phase Decision of Node {NODE_ID} sends RPC CommitAppend "
            f"to Phase Decision of Node message-service"
        )

        return self.msg.CommitAppend(req)

    def AbortAppend(self, req, ctx):
        # --- SERVER-SIDE Log ---
        print(
            f"Phase Decision of Node {NODE_ID} runs RPC AbortAppend "
            f"called by Phase Coordinator of Node ui-coordinator"
        )

        # --- CLIENT-SIDE Log ---
        print(
            f"Phase Decision of Node {NODE_ID} sends RPC AbortAppend "
            f"to Phase Decision of Node message-service"
        )

        return self.msg.AbortAppend(req)

    # =============================================================
    # Replay Helper
    # =============================================================
    def ReplayAndSubscribe(self, req, ctx):
        start = req.last_seen_offset + 1 if req.last_seen_offset > 0 else 0
        for m in self.msg.List(
            mp.ListReq(room_id=req.room_id, from_offset=start, limit=0)
        ):
            yield m

        for m in self.msg.Subscribe(mp.RoomId(room_id=req.room_id)):
            yield m


def serve():
    srv = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    gpg.add_GatewayServiceServicer_to_server(Gateway(), srv)
    srv.add_insecure_port(GATEWAY_BIND)
    print(f"gateway-svc on {GATEWAY_BIND}")
    srv.start()
    srv.wait_for_termination()

