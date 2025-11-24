# DS_Project_3
This is the repository for the project 3 of the distributed systems. 



## Running the Raft Cluster
Inside `object-based-system/`:

```bash
docker compose up --build

```

# Two-Phase Commit (2PC) Microservice System
This project implements Two-Phase Commit (2PC) using a distributed microservice architecture with Docker, gRPC, and Python.
The system contains the following services:

1. auth-service

2. room-service

3. presence-service

4. message-service (2PC participant)

5. gateway-service (2PC coordinator)

6. ui-service (simulates client → coordinator)

Follow the steps to execute the architecture:
## Clone the Repository

```
cd ~/Desktop
git clone https://github.com/sifatuddin99289/DS_Project_3.git
cd DS_Project_3/2PC-Microservice
```
## Install Python Dependencies (Only for compiling proto)
```
pip install grpcio grpcio-tools
```
## Generate All gRPC Python Files
```
python3 -m grpc_tools.protoc -I proto \
  --python_out=proto \
  --grpc_python_out=proto \
  proto/auth.proto \
  proto/room.proto \
  proto/presence.proto \
  proto/message.proto \
  proto/gateway.proto

```
## Move Into deploy Folder
```
cd deploy

```
## Build and Run All Microservices
```
docker compose down -v
docker compose up -d --build

```
check with

```
docker ps --format "table {{.Names}}\t{{.Status}}"

```
## Install grpcurl Inside the Gateway Container
Enter gateway:

```
docker exec -it deploy-gateway-1 bash

```
Inside the container:
```
apt update
apt install -y curl
curl -L -o grpcurl.tar.gz https://github.com/fullstorydev/grpcurl/releases/download/v1.8.9/grpcurl_1.8.9_linux_x86_64.tar.gz
tar -xzf grpcurl.tar.gz
chmod +x grpcurl
mv grpcurl /usr/local/bin/grpcurl
grpcurl -version

```
## TEST 2PC — Prepare Phase
Inside gateway container:
```
grpcurl -plaintext \
  -import-path /app/proto \
  -proto gateway.proto \
  -d '{
    "transaction_id":"tx123",
    "room_id":"room1",
    "user_id":"u1",
    "text":"hello 2pc",
    "idempotency_key":"idem001"
  }' \
  localhost:50055 gateway.v1.GatewayService/PrepareAppend

```
Expected response:
```
{ "success": true }

```
## TEST 2PC — Commit Phase
```
grpcurl -plaintext \
  -import-path /app/proto \
  -proto gateway.proto \
  -d '{"transaction_id":"tx123"}' \
  localhost:50055 gateway.v1.GatewayService/CommitAppend

```
## Viewing All 2PC LOGS
Gateway logs (Coordinator)

```
docker logs -f deploy-gateway-1

```
Expected:
```
Phase Voting of Node gateway runs RPC PrepareAppend called by Phase Coordinator of Node ui-coordinator
Phase Voting of Node gateway sends RPC PrepareAppend to Phase Voting of Node message-service
Phase Decision of Node gateway runs RPC CommitAppend called by Phase Coordinator of Node ui-coordinator
Phase Decision of Node gateway sends RPC CommitAppend to Phase Decision of Node message-service

```
Message logs (Participant)
```
docker logs -f deploy-message-1

```
Expected:
```
[2PC-MSG] Phase Voting of Node message-service runs RPC PrepareAppend called by Node coordinator
[2PC-MSG] Phase Decision of Node message-service runs RPC CommitAppend called by Node coordinator

```

## Raft Consensus (Object-Based System)

This part of the project implements a simplified **Raft consensus algorithm** on top of the Object-Based Distributed Chat System using **Python, gRPC, and Docker**. The system consists of **five Raft nodes**, each running inside its own container, performing leader election, heartbeat management, and log replication.

## Components
- raft-node-1  
- raft-node-2  
- raft-node-3  
- raft-node-4  
- raft-node-5  

Each node includes:
- Follower → Candidate → Leader state transitions  
- Random election timeout (1.5–3s)  
- Heartbeats every 1s  
- Full log replication from the leader  
- Client request handling (`ClientRequest` RPC)

run the follwing command to clone the git repository

```
git clone https://github.com/sifatuddin99289/DS_Project_3.git

``` 
