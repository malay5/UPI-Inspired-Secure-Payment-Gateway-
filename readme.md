-----

# Mini UPI: Secure Distributed Payment Gateway

   

## 📖 Overview

This project is a simplified, robust payment gateway system inspired by Stripe and UPI architectures. It interfaces clients with distributed bank servers to manage transactions securely and reliably. The system is designed to handle distributed consensus, offline capabilities, and idempotent processing to ensure financial accuracy.

-----

## 🏗 System Architecture

The system is composed of three distinct gRPC-based components:

### 1\. Bank Servers

  * **Role:** Acts as the financial source of truth, managing user accounts and balances .
  * **Behavior:** Each server represents a unique bank (e.g., "bank\_a", "bank\_b") and acts as a "Voter" in the Two-Phase Commit (2PC) protocol.
  * **Persistence:** Stores account data in persistent storage (JSON/Database) to survive crashes.

### 2\. Payment Gateway (Coordinator)

  * **Role:** The central coordinator that bridges Clients and Banks.
  * **Behavior:** Manages authentication, enforces idempotency, logs transactions, and coordinates the 2PC protocol.
  * **Security:** Validates credentials and issues session keys.

### 3\. Clients

  * **Role:** The end-user interface for registering, checking balances, and initiating payments.
  * **Behavior:** Maintains a local queue for offline transaction requests and handles automatic retries upon reconnection.

-----

## 🚀 Key Features

### 🔐 Security & Authentication

  * **Mutual Authentication:** Uses SSL/TLS for all communication between Clients, Gateway, and Banks to prevent eavesdropping.
  * **Session Management:** Upon login, the Gateway issues a UUID Session Key, reducing the need to transmit credentials repeatedly.
  * **Role-Based Access Control (RBAC):** gRPC Interceptors validate session keys to restrict operations (e.g., only the account owner can view their balance).

### 🔄 Idempotency (Safe Retries)

  * **Unique Transaction IDs:** Every request is assigned a unique UUID. Simple timestamps are avoided to prevent clock synchronization issues.
  * **State Tracking:** The Gateway tracks transaction states (`INITIATED`, `COMMITTED`, `ABORTED`).
  * **Deduplication:** If a duplicate request is received, the system returns the stored result rather than re-processing the payment.

### 📶 Offline Capabilities

  * **Local Queuing:** If the Gateway is unreachable, clients queue payments locally.
  * **Exponential Backoff:** The client retries connections periodically (e.g., 5s, 10s, 20s) to avoid overwhelming the server.
  * **Synchronization:** Upon reconnection, queued payments are processed automatically using the idempotency mechanism to ensure exactly-once execution.

### 🤝 Distributed Consistency (2PC)

  * **Two-Phase Commit:** The Gateway acts as the coordinator to ensure atomicity across different banks.
      * **Phase 1 (Prepare):** Banks check for sufficient funds and vote YES or NO.
      * **Phase 2 (Commit):** If all banks vote YES, the transaction is committed; otherwise, it is aborted.
  * **Timeouts:** Configurable timeouts (e.g., 10 seconds) prevent system stalls if a node becomes unresponsive.

-----

## 🛠️ Technology Stack

  * **Communication Framework:** gRPC (Google Remote Procedure Call).
  * **Security:** SSL/TLS certificates via a trusted Certificate Authority (CA).
  * **Storage:** Persistent JSON/File-based storage for bank ledgers and transaction logs.
  * **Logging:** gRPC Interceptors for centralized verbose logging (Client ID, Amount, Errors).

-----

## ⚙️ Implementation Details

### 1\. Setup & Registration

Clients register with a username, password, and initial balance. The bank servers load this data from a setup file at startup to ensure state recovery.

### 2\. Transaction Flow

1.  **Login:** Client sends credentials; Gateway validates and returns a Session Key.
2.  **Initiate:** Client sends payment request with Session Key and unique Transaction ID.
3.  **Idempotency Check:** Gateway checks if ID exists. If `COMMITTED`, return result. If `NEW`, start 2PC.
4.  **2PC Process:** Gateway coordinates with Sender Bank and Receiver Bank.
5.  **Completion:** Result is returned to Client; Banks update persistent storage.

### 3\. Logging

The system implements verbose logging to monitor system health. Logs include transaction amounts, client IDs (from session keys), and error codes (e.g., "Insufficient funds").

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
