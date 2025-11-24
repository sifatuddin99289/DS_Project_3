import random
import time
import threading
from enum import Enum

class Role(Enum):
    FOLLOWER = 1
    CANDIDATE = 2
    LEADER = 3

class RaftNodeState:
    def __init__(self, node_id, peers, stub_map):
        self.node_id = node_id
        self.peers = peers
        self.stubs = stub_map

        # Persistent state
        self.current_term = 0
        self.voted_for = None
        self.log = []  # list of dict: {term, index, operation}

        # Volatile state
        self.role = Role.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0
        
        # Leader state
        self.next_index = {}
        self.match_index = {}

        # Timers
        self.last_heartbeat_time = time.time()
        self.election_timeout = self.new_election_timeout()

        # Protect shared state
        self.lock = threading.Lock()

    def new_election_timeout(self):
        return random.uniform(1.5, 3.0)

    def reset_election_timer(self):
        self.last_heartbeat_time = time.time()
        self.election_timeout = self.new_election_timeout()

    def time_for_election(self):
        return (time.time() - self.last_heartbeat_time) > self.election_timeout

    def append_log_entry(self, operation):
        index = len(self.log) + 1
        entry = {
            "term": self.current_term,
            "index": index,
            "operation": operation
        }
        self.log.append(entry)
        return entry
