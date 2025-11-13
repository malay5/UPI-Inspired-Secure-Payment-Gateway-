import grpc
import sys
import random
import time
import queue
import os

import bank_pb2
import bank_pb2_grpc
import gateway_pb2
import gateway_pb2_grpc
import auth_pb2
import auth_pb2_grpc

class Client:
    def __init__(self, stub):
        self.stub = stub
        self.keys = {}
        self.offline_processing = queue.Queue()
        self.last_success_time = 0

    def register(self, username, password, bank_name, initial_amount):
        request = auth_pb2.RegisterRequest(
            username=username,
            password=password,
            bank_name=bank_name,
            initial_amount=initial_amount
        )
        try:
            response = self.stub.RegisterAccount(request)
            if not response.success:
                print(response.message)
                return ""
            print(f"Registered {username} at {bank_name} with account {response.account_number}")
            return response.account_number
        except grpc.RpcError as e:
            print(f"Error registering: {e.details()}")
            return None

    def login(self, username, password, bank_name):
        request = auth_pb2.LoginRequest(username=username, password=password, bank_name=bank_name)
        try:
            response = self.stub.Login(request)
            if response.message == "Login successful":
                self.keys[f"{bank_name}_{response.account_number}"] = response.key
                print(f"Logged in to {bank_name} with account {response.account_number}")
                return response.account_number
            else:
                print(response.message)
                return None
        except grpc.RpcError as e:
            print(f"Error logging in: {e.details()}")
            return None

    def get_balance(self, account_number, bank_name):
        key = self.keys.get(f"{bank_name}_{account_number}")
        if not key:
            print("Not logged in to this account")
            return
        request = bank_pb2.Account(number=account_number, bank_name=bank_name, key=key)
        try:
            response = self.stub.GetBalance(request)
            if response.error:
                print(f"Error: {response.message}")
            else:
                print(f"Balance for {bank_name} {account_number}: {response.balance}")
        except grpc.RpcError as err:
            print(f"Error getting balance: {err.details()}")

    def process_payment(self, txn_id, from_acc, from_bank, to_acc, to_bank, amount):
        from_key = self.keys.get(f"{from_bank}_{from_acc}")
        if not from_key:
            print("Not logged in to the sender's account")
            return
        request = bank_pb2.Transaction(
            id=txn_id,
            from_=from_acc,
            from_bank=from_bank,
            to=to_acc,
            to_bank=to_bank,
            amount=amount,
            timestamp=int(time.time()),  # Use current time instead of hardcoded 5000
            key=from_key
        )
        if self.offline_processing.empty():
            # Try immediate processing if queue is empty
            try:
                response = self.stub.ProcessBank(request)
                if response.success:
                    print(f"Payment result: {response.success} - {response.message}")
                    self.last_success_time = time.time()
                else:
                    print(f"Payment failed: {response.message}")
                    # self.offline_processing.put(request)
                    # print(f"Queued transaction {txn_id} for retry")
            except grpc.RpcError as err:
                print(f"Error processing payment: {err.details()}")
                self.offline_processing.put(request)
                print(f"Queued transaction {txn_id} for retry")
        else:
            # Queue is not empty, add to queue and process if enough time has passed
            current_time = time.time()
            if current_time - self.last_success_time < 5:
                print(f"Less than 5 seconds since last success, queuing {txn_id}")
                self.offline_processing.put(request)
            else:
                # Try processing the head of the queue
                head_request = self.offline_processing.queue[0]  # Peek at head
                print(f"Retrying queued transaction {head_request.id}")
                try:
                    response = self.stub.ProcessBank(head_request)
                    if response.success:
                        self.offline_processing.get()  # Remove head on success
                        self.last_success_time = time.time()
                        print(f"Payment result: {response.success} - {response.message}")
                        # Process all queued transactions if head succeeds
                        while not self.offline_processing.empty():
                            next_request = self.offline_processing.queue[0]
                            print(f"Processing queued transaction {next_request.id}")
                            response = self.stub.ProcessBank(next_request)
                            if response.success:
                                self.offline_processing.get()
                                self.last_success_time = time.time()
                                print(f"Payment result: {response.success} - {response.message}")
                            else:
                                print(f"Payment failed: {response.message}")
                                break
                    else:
                        print(f"Payment failed: {response.message}")
                        self.offline_processing.put(request)  # Add new request to queue
                except grpc.RpcError as err:
                    print(f"Error processing queued payment: {err.details()}")
                    self.offline_processing.put(request)  # Add new request to queue

    def process_offline_queue(self, timeout=300):
        """Process the offline queue until empty or timeout is reached."""
        start_time = time.time()
        while not self.offline_processing.empty():
            if time.time() - start_time > timeout:
                print(f"Timeout reached with {self.offline_processing.qsize()} pending transactions")
                return False
            request = self.offline_processing.queue[0]  # Peek at head
            print(f"Retrying queued transaction {request.id}")
            try:
                response = self.stub.ProcessBank(request)
                if response.success:
                    self.offline_processing.get()  # Remove head on success
                    self.last_success_time = time.time()
                    print(f"Payment result: {response.success} - {response.message}")
                else:
                    print(f"Payment failed: {response.message}")
                    time.sleep(5)  # Wait before retrying
            except grpc.RpcError as err:
                print(f"Error processing queued payment: {err.details()}")
                time.sleep(5)  # Wait before retrying
        print("All queued transactions processed")
        return True

def run(gateway_host, gateway_port):
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

    with grpc.secure_channel(f'{gateway_host}:{gateway_port}',channel_credentials) as channel:
        stub = gateway_pb2_grpc.GatewayServiceStub(channel)
        client = Client(stub)
        all_accounts = {}

        # Register and login 20 users sequentially
        for client_id in range(20):
            username = f"user_{client_id}"
            password = f"pass_{client_id}"
            bank_name = random.choice(["bank_b"])  # Fixed to one bank for simplicity
            initial_amount = random.uniform(500, 2000)
            account_number = client.register(username, password, bank_name, initial_amount)
            if account_number:
                client.login(username, password, bank_name)
                all_accounts[account_number] = bank_name

        # Perform transactions sequentially
        for client_id in range(20):
            username = f"user_{client_id}"
            account_number = [acc for acc, bank in all_accounts.items() if f"{bank}_{acc}" in client.keys][0]
            bank_name = all_accounts[account_number]
            for i in range(10):
                other_accounts = [acc for acc in all_accounts if acc != account_number]
                if not other_accounts:
                    time.sleep(1)  # Wait if no other accounts yet
                    continue
                to_acc = random.choice(other_accounts)
                to_bank = all_accounts[to_acc]
                amount = random.uniform(10, 100)
                txn_id = f"txn_{client_id}_{i}_{int(time.time())}"
                client.process_payment(txn_id, account_number, bank_name, to_acc, to_bank, amount)
                
                if random.random() < 0.3:
                    client.get_balance(account_number, bank_name)
                
                time.sleep(random.uniform(0.1, 0.5))

        # Process any remaining offline transactions
        client.process_offline_queue(timeout=300)

        # Final balance check
        print("\nFinal Balances:")
        for account_number, bank_name in all_accounts.items():
            client.get_balance(account_number, bank_name)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python client.py <gateway_port>")
        sys.exit(1)
    gateway_host = "localhost"
    gateway_port = sys.argv[1]
    run(gateway_host, gateway_port)