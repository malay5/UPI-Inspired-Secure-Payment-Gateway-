import grpc
import sys
import random
import time
import queue
import threading
import os

import bank_pb2
import bank_pb2_grpc
import gateway_pb2
import gateway_pb2_grpc
import auth_pb2
import auth_pb2_grpc

# Client class to handle registration, login, transactions, and balance checks
class Client:
    def __init__(self, stub, shared_keys=None, keys_lock=None):
        self.stub = stub
        self.keys = shared_keys if shared_keys is not None else {}
        self.keys_lock = keys_lock
        self.pending_transactions = queue.Queue()  # Queue for offline transactions
        self.last_failure_time = None  # Track when the last failure occurred

    ### Registration
    def register(self, username, password, bank_name, initial_amount):
        request = auth_pb2.RegisterRequest(
            username=username,
            password=password,
            bank_name=bank_name,
            initial_amount=initial_amount
        )
        try:
            response = self.stub.RegisterAccount(request)
            print(f"Registered {username} at {bank_name} with account {response.account_number} - {response.message}")
            return response.account_number if response.account_number else None
        except grpc.RpcError as e:
            print(f"Error registering {username}: {e.details()}")
            return None

    ### Login
    def login(self, username, password, bank_name):
        request = auth_pb2.LoginRequest(username=username, password=password, bank_name=bank_name)
        try:
            response = self.stub.Login(request)
            if response.message == "Login successful":
                with self.keys_lock:
                    self.keys[f"{bank_name}_{response.account_number}"] = response.key
                print(f"Logged in {username} to {bank_name} with account {response.account_number}")
                return response.account_number
            else:
                print(f"Login failed for {username}: {response.message}")
                return None
        except grpc.RpcError as e:
            print(f"Error logging in {username}: {e.details()}")
            return None

    ### Get Balance
    def get_balance(self, account_number, bank_name):
        key = self.keys.get(f"{bank_name}_{account_number}")
        if not key:
            print(f"Not logged in to {bank_name} {account_number}")
            return None
        request = bank_pb2.Account(number=account_number, bank_name=bank_name, key=key)
        try:
            response = self.stub.GetBalance(request)
            if response.error:
                print(f"Error getting balance for {bank_name} {account_number}: {response.message}")
                return None
            else:
                print(f"Balance for {bank_name} {account_number}: {response.balance}")
                return response.balance
        except grpc.RpcError as err:
            print(f"Error getting balance for {bank_name} {account_number}: {err.details()}")
            return None

    ### Process Payment
    def process_payment(self, txn_id, from_acc, from_bank, to_acc, to_bank, amount):
        from_key = self.keys.get(f"{from_bank}_{from_acc}")
        if not from_key:
            print(f"Not logged in to sender's account {from_bank} {from_acc}")
            return
        request = bank_pb2.Transaction(
            id=txn_id,
            from_=from_acc,
            from_bank=from_bank,
            to=to_acc,
            to_bank=to_bank,
            amount=amount,
            timestamp=int(time.time()),
            key=from_key
        )
        try:
            response = self.stub.ProcessBank(request)
            print(f"Transaction {txn_id}: {from_bank} {from_acc} -> {to_bank} {to_acc} ({amount:.2f}): {response.success} - {response.message}")
            self._process_queue_head()
            return
        except grpc.RpcError as err:
            print(f"Gateway unavailable for transaction {txn_id}: {err.details()} - Queuing transaction")
            current_time = time.time()
            if self.last_failure_time is None or (current_time - self.last_failure_time) >= 5:
                self.pending_transactions.put(request)
                self.last_failure_time = current_time
                time.sleep(5)
                self._process_queue_head()
            else:
                self.pending_transactions.put(request)

    ### Process Queued Transactions
    def _process_queue_head(self):
        while not self.pending_transactions.empty():
            request = self.pending_transactions.queue[0]
            try:
                response = self.stub.ProcessBank(request)
                print(f"Processed queued {request.id}: {request.from_bank} {request.from_} -> {request.to_bank} {request.to} ({request.amount:.2f}): {response.success} - {response.message}")
                self.pending_transactions.get()
                self.pending_transactions.task_done()
                self.last_failure_time = None
            except grpc.RpcError as err:
                print(f"Retry failed for {request.id}: {err.details()} - Waiting 5 seconds")
                time.sleep(5)
                break

# Function to simulate a client thread performing transactions
def client_thread(client_id, stub, all_accounts, shared_keys, keys_lock):
    client = Client(stub, shared_keys, keys_lock)
    for i in range(10):
        # Randomly select sender and receiver from pre-registered accounts
        sender_account, sender_bank = random.choice(list(all_accounts.items()))
        receiver_account, receiver_bank = random.choice([acc for acc in all_accounts.items() if acc[0] != sender_account])
        
        amount = random.uniform(10, 100)
        txn_id = f"txn_{client_id}_{i}_{int(time.time())}"
        client.process_payment(txn_id, sender_account, sender_bank, receiver_account, receiver_bank, amount)
        
        # 30% chance to check sender's balance after a transaction
        if random.random() < 0.3:
            client.get_balance(sender_account, sender_bank)
        
        time.sleep(random.uniform(0.1, 0.5))

# Main function to set up and run the client
def run(gateway_host, gateway_port):
    # Load TLS certificates
    cert_dir = os.path.join(os.getcwd(), "certs")
    with open(os.path.join(cert_dir, "client.key"), 'rb') as f:
        private_key = f.read()
    with open(os.path.join(cert_dir, "client.crt"), 'rb') as f:
        certificate_chain = f.read()
    with open(os.path.join(cert_dir, "ca.crt"), 'rb') as f:
        root_certificates = f.read()

    channel_credentials = grpc.ssl_channel_credentials(
        root_certificates=root_certificates,
        private_key=private_key,
        certificate_chain=certificate_chain
    )
    
    # Establish secure gRPC channel
    with grpc.secure_channel(f'{gateway_host}:{gateway_port}', channel_credentials) as channel:
        stub = gateway_pb2_grpc.GatewayServiceStub(channel)
        all_accounts = {}  # Store account numbers and their banks
        shared_keys = {}   # Shared dictionary for authentication keys
        keys_lock = threading.Lock()  # Lock for thread-safe key access

        # Pre-register and log in 100 users
        for i in range(100):
            username = f"user_{i}"
            password = f"pass_{i}"
            bank_name = random.choice(["bank_a", "bank_b", "bank_c", "bank_d", "bank_e"])
            bank_name="bank_b"
            initial_amount = random.uniform(500, 2000)
            client = Client(stub, shared_keys, keys_lock)
            account_number = client.register(username, password, bank_name, initial_amount)
            if account_number:
                client.login(username, password, bank_name)
                all_accounts[account_number] = bank_name

        # Start 10 client threads
        threads = []
        clients = []
        for client_id in range(10):
            client = Client(stub, shared_keys, keys_lock)
            clients.append(client)
            thread = threading.Thread(target=client_thread, args=(client_id, stub, all_accounts, shared_keys, keys_lock))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Process any remaining queued transactions
        for client in clients:
            client._process_queue_head()

        # Print final balances using a single client
        if clients:
            print("\nFinal Balances:")
            for account_number, bank_name in all_accounts.items():
                clients[0].get_balance(account_number, bank_name)

        print("All queued transactions processed or timed out.")

# Entry point
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python client.py <gateway_port>")
        sys.exit(1)
    gateway_host = "localhost"
    gateway_port = sys.argv[1]
    run(gateway_host, gateway_port)