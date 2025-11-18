-----

# Mini UPI: Secure Distributed Payment Gateway

   

## 📖 Overview

[cite\_start]This project is a simplified, robust payment gateway system inspired by Stripe and UPI architectures[cite: 1, 3]. [cite\_start]It interfaces clients with distributed bank servers to manage transactions securely and reliably[cite: 3]. [cite\_start]The system is designed to handle distributed consensus, offline capabilities, and idempotent processing to ensure financial accuracy[cite: 4].

-----

## 🏗 System Architecture

The system is composed of three distinct gRPC-based components[cite: 6]:

### 1\. Bank Servers

  * **Role:** Acts as the financial source of truth, managing user accounts and balances .
  * [cite\_start]**Behavior:** Each server represents a unique bank (e.g., "bank\_a", "bank\_b") and acts as a "Voter" in the Two-Phase Commit (2PC) protocol[cite: 9, 10].
  * [cite\_start]**Persistence:** Stores account data in persistent storage (JSON/Database) to survive crashes[cite: 11].

### 2\. Payment Gateway (Coordinator)

  * [cite\_start]**Role:** The central coordinator that bridges Clients and Banks[cite: 25].
  * [cite\_start]**Behavior:** Manages authentication, enforces idempotency, logs transactions, and coordinates the 2PC protocol[cite: 26, 27].
  * [cite\_start]**Security:** Validates credentials and issues session keys[cite: 27].

### 3\. Clients

  * [cite\_start]**Role:** The end-user interface for registering, checking balances, and initiating payments[cite: 18].
  * [cite\_start]**Behavior:** Maintains a local queue for offline transaction requests and handles automatic retries upon reconnection[cite: 20, 95].

-----

## 🚀 Key Features

### 🔐 Security & Authentication

  * [cite\_start]**Mutual Authentication:** Uses SSL/TLS for all communication between Clients, Gateway, and Banks to prevent eavesdropping[cite: 31, 41].
  * [cite\_start]**Session Management:** Upon login, the Gateway issues a UUID Session Key, reducing the need to transmit credentials repeatedly[cite: 39, 40].
  * [cite\_start]**Role-Based Access Control (RBAC):** gRPC Interceptors validate session keys to restrict operations (e.g., only the account owner can view their balance)[cite: 44, 50].

### 🔄 Idempotency (Safe Retries)

  * **Unique Transaction IDs:** Every request is assigned a unique UUID. [cite\_start]Simple timestamps are avoided to prevent clock synchronization issues[cite: 66, 69].
  * [cite\_start]**State Tracking:** The Gateway tracks transaction states (`INITIATED`, `COMMITTED`, `ABORTED`)[cite: 71].
  * [cite\_start]**Deduplication:** If a duplicate request is received, the system returns the stored result rather than re-processing the payment[cite: 75].

### 📶 Offline Capabilities

  * [cite\_start]**Local Queuing:** If the Gateway is unreachable, clients queue payments locally[cite: 95, 97].
  * [cite\_start]**Exponential Backoff:** The client retries connections periodically (e.g., 5s, 10s, 20s) to avoid overwhelming the server[cite: 99].
  * [cite\_start]**Synchronization:** Upon reconnection, queued payments are processed automatically using the idempotency mechanism to ensure exactly-once execution[cite: 100].

### 🤝 Distributed Consistency (2PC)

  * [cite\_start]**Two-Phase Commit:** The Gateway acts as the coordinator to ensure atomicity across different banks[cite: 110].
      * [cite\_start]**Phase 1 (Prepare):** Banks check for sufficient funds and vote YES or NO[cite: 112, 114].
      * [cite\_start]**Phase 2 (Commit):** If all banks vote YES, the transaction is committed; otherwise, it is aborted[cite: 116, 117].
  * [cite\_start]**Timeouts:** Configurable timeouts (e.g., 10 seconds) prevent system stalls if a node becomes unresponsive[cite: 118].

-----

## 🛠️ Technology Stack

  * [cite\_start]**Communication Framework:** gRPC (Google Remote Procedure Call)[cite: 8].
  * [cite\_start]**Security:** SSL/TLS certificates via a trusted Certificate Authority (CA)[cite: 36].
  * [cite\_start]**Storage:** Persistent JSON/File-based storage for bank ledgers and transaction logs[cite: 11].
  * [cite\_start]**Logging:** gRPC Interceptors for centralized verbose logging (Client ID, Amount, Errors)[cite: 54, 56].

-----

## ⚙️ Implementation Details

### 1\. Setup & Registration

Clients register with a username, password, and initial balance. [cite\_start]The bank servers load this data from a setup file at startup to ensure state recovery[cite: 11, 19].

### 2\. Transaction Flow

1.  **Login:** Client sends credentials; [cite\_start]Gateway validates and returns a Session Key[cite: 37, 39].
2.  [cite\_start]**Initiate:** Client sends payment request with Session Key and unique Transaction ID[cite: 69].
3.  **Idempotency Check:** Gateway checks if ID exists. If `COMMITTED`, return result. [cite\_start]If `NEW`, start 2PC[cite: 75, 76].
4.  [cite\_start]**2PC Process:** Gateway coordinates with Sender Bank and Receiver Bank[cite: 113].
5.  **Completion:** Result is returned to Client; [cite\_start]Banks update persistent storage[cite: 116, 121].

### 3\. Logging

The system implements verbose logging to monitor system health. [cite\_start]Logs include transaction amounts, client IDs (from session keys), and error codes (e.g., "Insufficient funds")[cite: 58, 59, 61].

-----

## 🧪 Usage

*Note: Ensure you have Python and `grpcio-tools` installed.*

**1. Start Bank Servers**

```bash
# Starts a bank server instance (e.g., bank_a)
python bank_server.py --name bank_a --port 50051
```

**2. Start Payment Gateway**

```bash
# Starts the central coordinator
python gateway_server.py --port 50050
```

**3. Run Client**

```bash
# interactive client CLI
python client.py
```

-----

## 📄 License

This project is designed for educational purposes to demonstrate distributed systems concepts including 2PC, Idempotency, and gRPC microservices.
