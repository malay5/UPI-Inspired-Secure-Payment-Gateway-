import grpc
import sys
import random
import threading
import time

import bank_pb2
import bank_pb2_grpc
import gateway_pb2
import gateway_pb2_grpc
import auth_pb2
import auth_pb2_grpc

class Client:
    def __init__(self, stub, shared_keys=None, keys_lock=None):
        self.stub = stub
        self.keys = shared_keys if shared_keys is not None else {}  # Use shared keys if provided
        self.keys_lock = keys_lock  # Lock for thread-safe key updates

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
        except grpc.RpcError as err:
            print(f"Error processing transaction {txn_id}: {err.details()}")

def client_thread(client_id, stub, all_accounts, shared_keys, keys_lock):
    client = Client(stub, shared_keys, keys_lock)
    username = f"user111150__{client_id}"
    password = f"pass__{client_id}"
    bank_name = random.choice(["bank_a", "bank_b", "bank_c", "bank_d", "bank_e"])
    bank_name=["bank_a", "bank_b"]
    initial_amount = random.uniform(500, 2000)

    # Register and login
    account_number = client.register(username, password, bank_name, initial_amount)
    if account_number:
        client.login(username, password, bank_name)
        with threading.Lock():  # Protect all_accounts updates
            all_accounts[account_number] = bank_name

    # Perform 10 random transactions
    for i in range(10):
        if not account_number:
            break
        # Choose a random recipient from all_accounts (excluding self)
        with threading.Lock():  # Protect all_accounts reads
            other_accounts = [acc for acc, bank in all_accounts.items() if acc != account_number]
        if not other_accounts:
            time.sleep(1)  # Wait for other clients to register
            continue
        to_acc = random.choice(other_accounts)
        with threading.Lock():
            to_bank = all_accounts[to_acc]
        amount = random.uniform(10, 100)
        txn_id = f"txn_{client_id}_{i}_{int(time.time())}"
        client.process_payment(txn_id, account_number, bank_name, to_acc, to_bank, amount)
        
        # Occasionally check balance
        if random.random() < 0.3:
            client.get_balance(account_number, bank_name)
        
        # Small delay
        time.sleep(random.uniform(0.1, 0.5))

def run(gateway_host, gateway_port):
    with grpc.insecure_channel(f'{gateway_host}:{gateway_port}') as channel:
        stub = gateway_pb2_grpc.GatewayServiceStub(channel)
        all_accounts = {}  # Shared dict: account_number -> bank_name
        shared_keys = {}  # Shared dict: bank_name_account_number -> key
        keys_lock = threading.Lock()  # Lock for thread-safe key updates
        threads = []

        # Start 20 client threads
        for client_id in range(20):
            thread = threading.Thread(target=client_thread, args=(client_id, stub, all_accounts, shared_keys, keys_lock))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Final balance check for all accounts
        client = Client(stub, shared_keys, keys_lock)
        print("\nFinal Balances:")
        for account_number, bank_name in all_accounts.items():
            client.get_balance(account_number, bank_name)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python client.py <gateway_port>")
        sys.exit(1)
    gateway_host = "localhost"
    gateway_port = sys.argv[1]  # e.g., 50050
    run(gateway_host, gateway_port)