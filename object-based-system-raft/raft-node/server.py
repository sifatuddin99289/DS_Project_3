import grpc
import time
import threading
from concurrent import futures

import raft_pb2
import raft_pb2_grpc

from raft_state import RaftNodeState, Role

class RaftService(raft_pb2_grpc.RaftServiceServicer):
    def __init__(self, state):
        self.state = state

    # ================================
    #   1. RequestVote RPC Handler
    # ================================
    def RequestVote(self, request, context):
        caller = request.candidate_id
        print(f"Node {self.state.node_id} runs RPC RequestVote called by Node {caller}")

        with self.state.lock:
            # Reject if term is old
            if request.term < self.state.current_term:
                return raft_pb2.VoteResponse(
                    term=self.state.current_term,
                    vote_granted=False
                )

            # If request term is newer, update ourselves
            if request.term > self.state.current_term:
                self.state.current_term = request.term
                self.state.voted_for = None
                self.state.role = Role.FOLLOWER

            # Check if we can vote
            can_vote = (self.state.voted_for is None or self.state.voted_for == request.candidate_id)

            if can_vote:
                self.state.voted_for = request.candidate_id
                self.state.reset_election_timer()
                return raft_pb2.VoteResponse(
                    term=self.state.current_term,
                    vote_granted=True
                )

            return raft_pb2.VoteResponse(
                term=self.state.current_term,
                vote_granted=False
            )

    # =====================================
    #   2. AppendEntries RPC (Heartbeats + Logs)
    # =====================================
    def AppendEntries(self, request, context):
        caller = request.leader_id
        print(f"Node {self.state.node_id} runs RPC AppendEntries called by Node {caller}")

        with self.state.lock:
            if request.term < self.state.current_term:
                return raft_pb2.AppendEntriesResponse(
                    term=self.state.current_term,
                    success=False,
                    match_index=0
                )

            # If leader term is higher, update term
            if request.term > self.state.current_term:
                self.state.current_term = request.term
                self.state.voted_for = None

            # Follow the leader
            self.state.role = Role.FOLLOWER
            self.state.reset_election_timer()

            # ========== Q4: Log Replication ==========
            # Replace entire log with leader's log (simplified version allowed)
            self.state.log = []
            for entry in request.entries:
                self.state.log.append({
                    "term": entry.term,
                    "index": entry.index,
                    "operation": entry.operation
                })

            # Apply commits
            self.state.commit_index = request.leader_commit

            return raft_pb2.AppendEntriesResponse(
                term=self.state.current_term,
                success=True,
                match_index=len(self.state.log)
            )

    # =====================================
    #   3. ClientRequest (Client → Raft Leader)
    # =====================================
    def ClientRequest(self, request, context):
        print(f"Node {self.state.node_id} runs RPC ClientRequest")

        with self.state.lock:
            # If I'm not the leader, redirect client
            if self.state.role != Role.LEADER:
                return raft_pb2.ClientReply(
                    success=False,
                    leader_id=self.state.node_id,  # you should store real leader
                    message="Not leader"
                )

            # Append log entry
            entry = self.state.append_log_entry(request.operation)
            print(f"Leader {self.state.node_id} appended log entry {entry}")

        return raft_pb2.ClientReply(
            success=True,
            leader_id=self.state.node_id,
            message="Operation received. Will commit after replication."
        )


# =====================================================
#   MAIN SERVER + ELECTION + HEARTBEAT THREADS
# =====================================================
def election_loop(state, stub_map):
    while True:
        time.sleep(0.1)

        with state.lock:
            if state.role == Role.LEADER:
                continue

            # If timeout → start election
            if state.time_for_election():
                print(f"Node {state.node_id} timed out. Becoming Candidate.")
                start_election(state, stub_map)


def start_election(state, stub_map):
    state.role = Role.CANDIDATE
    state.current_term += 1
    state.voted_for = state.node_id
    votes = 1
    majority = len(state.peers) // 2 + 1

    print(f"Node {state.node_id} starting election for term {state.current_term}")

    for peer_id, stub in stub_map.items():
        print(f"Node {state.node_id} sends RPC RequestVote to Node {peer_id}")
        try:
            resp = stub.RequestVote(raft_pb2.VoteRequest(
                term=state.current_term,
                candidate_id=str(state.node_id),
                last_log_index=0,
                last_log_term=0
            ))
            if resp.vote_granted:
                votes += 1
        except:
            pass

    if votes >= majority:
        become_leader(state, stub_map)
    else:
        state.role = Role.FOLLOWER


def become_leader(state, stub_map):
    print(f"Node {state.node_id} is now LEADER for term {state.current_term}")
    state.role = Role.LEADER

    # Start sending heartbeats
    threading.Thread(target=heartbeat_loop, args=(state, stub_map), daemon=True).start()


def heartbeat_loop(state, stub_map):
    while state.role == Role.LEADER:
        time.sleep(1)

        with state.lock:
            entries = []
            for e in state.log:
                entries.append(raft_pb2.LogEntry(
                    term=e["term"], index=e["index"], operation=e["operation"]
                ))

        for peer_id, stub in stub_map.items():
            print(f"Node {state.node_id} sends RPC AppendEntries to Node {peer_id}")
            try:
                stub.AppendEntries(raft_pb2.AppendEntriesRequest(
                    term=state.current_term,
                    leader_id=str(state.node_id),
                    prev_log_index=0,
                    prev_log_term=0,
                    entries=entries,
                    leader_commit=state.commit_index
                ))
            except:
                pass


def serve():
    import os
    node_id = os.getenv("NODE_ID")
    peers_raw = os.getenv("PEERS")
    peers = peers_raw.split(",") if peers_raw else []

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))

    # Create stubs for peers
    stub_map = {}
    for p in peers:
        ch = grpc.insecure_channel(p)
        stub_map[p] = raft_pb2_grpc.RaftServiceStub(ch)

    # Create state
    state = RaftNodeState(node_id, peers, stub_map)

    # Register service
    raft_pb2_grpc.add_RaftServiceServicer_to_server(
        RaftService(state),
        server
    )

    server.add_insecure_port("[::]:6000")
    server.start()
    print(f"Raft node {node_id} started.")

    # Start election timer thread
    threading.Thread(target=election_loop, args=(state, stub_map), daemon=True).start()

    server.wait_for_termination()


if __name__ == '__main__':
    serve()
