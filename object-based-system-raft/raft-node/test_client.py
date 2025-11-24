import grpc
import raft_pb2
import raft_pb2_grpc

channel = grpc.insecure_channel("localhost:6001")
stub = raft_pb2_grpc.RaftServiceStub(channel)

resp = stub.ClientRequest(raft_pb2.ClientCommand(operation="SEND|room=general|msg=hello"))
print(resp)
