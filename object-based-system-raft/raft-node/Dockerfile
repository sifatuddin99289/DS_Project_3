FROM python:3.12-slim

WORKDIR /app

COPY raft_pb2.py raft_pb2_grpc.py ./
COPY raft_state.py server.py ./

RUN pip install grpcio grpcio-tools

EXPOSE 6000

CMD ["python", "server.py"]
