import sqlite3, os, time, threading
from concurrent import futures
import grpc

import message_pb2 as mp
import message_pb2_grpc as mpg

DB_PATH = os.getenv("MESSAGE_DB", "/data/messages.db")
NODE_ID = os.getenv("NODE_ID", "message-service")


class MessageService(mpg.MessageServiceServicer):
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
            self.db.executescript(f.read())
        self.db.commit()

        self.lock = threading.Lock()
        self.subs = {}

    # ============================================================
    # 2PC PHASE 1 — PREPARE
    # ============================================================
    def PrepareAppend(self, request, context):
        print(
            f"Phase Voting of Node {NODE_ID} runs RPC PrepareAppend "
            f"called by Phase Coordinator of Node gateway-coordinator"
        )

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            ts = int(time.time() * 1000)

            cur.execute(
                """
                INSERT INTO messages (room_id, user_id, text, ts_ms, transaction_id, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    request.room_id,
                    request.user_id,
                    request.text,
                    ts,
                    request.transaction_id,
                ),
            )
            conn.commit()

            return mp.PrepareAppendResp(success=True)
        except Exception as e:
            return mp.PrepareAppendResp(success=False, error=str(e))
        finally:
            conn.close()

    # ============================================================
    # 2PC PHASE 2 — COMMIT
    # ============================================================
    def CommitAppend(self, request, context):
        print(
            f"Phase Decision of Node {NODE_ID} runs RPC CommitAppend "
            f"called by Phase Coordinator of Node gateway-coordinator"
        )

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            cur.execute("SELECT COALESCE(MAX(offset), -1) FROM messages")
            next_offset = cur.fetchone()[0] + 1

            cur.execute(
                """
                UPDATE messages
                SET offset=?, status='COMMITTED'
                WHERE transaction_id=?
                """,
                (next_offset, request.transaction_id),
            )
            conn.commit()

            return mp.CommitAppendResp(success=True, committed_offset=next_offset)
        except Exception as e:
            return mp.CommitAppendResp(success=False, committed_offset=-1, error=str(e))
        finally:
            conn.close()

    # ============================================================
    # 2PC PHASE 2 — ABORT
    # ============================================================
    def AbortAppend(self, request, context):
        print(
            f"Phase Decision of Node {NODE_ID} runs RPC AbortAppend "
            f"called by Phase Coordinator of Node gateway-coordinator"
        )

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            cur.execute(
                "DELETE FROM messages WHERE transaction_id=?",
                (request.transaction_id,),
            )
            conn.commit()

            return mp.AbortAppendResp(success=True)
        except Exception as e:
            return mp.AbortAppendResp(success=False, error=str(e))
        finally:
            conn.close()

    # ============================================================
    # List committed messages
    # ============================================================
    def List(self, req, ctx):
        lim = req.limit if req.limit > 0 else 100
        for row in self.db.execute(
            """
            SELECT room_id, user_id, text, offset, ts_ms
            FROM messages
            WHERE room_id=? AND offset>=? AND status='COMMITTED'
            ORDER BY offset ASC LIMIT ?
            """,
            (req.room_id, req.from_offset, lim),
        ):
            yield mp.Msg(
                room_id=row[0],
                user_id=row[1],
                text=row[2],
                offset=row[3],
                ts_ms=row[4],
            )

    def Subscribe(self, rid, ctx):
        q = []
        with self.lock:
            self.subs.setdefault(rid.room_id, []).append(q)
        try:
            while True:
                time.sleep(0.1)
                while q:
                    yield q.pop(0)
        finally:
            with self.lock:
                if q in self.subs.get(rid.room_id, []):
                    self.subs[rid.room_id].remove(q)


def serve():
    srv = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    mpg.add_MessageServiceServicer_to_server(MessageService(), srv)
    srv.add_insecure_port("[::]:50054")
    print("message-svc on :50054")
    srv.start()
    srv.wait_for_termination()

