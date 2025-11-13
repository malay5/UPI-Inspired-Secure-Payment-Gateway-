import grpc
import sys
import os
import time
import queue
import threading

import bank_pb2
import bank_pb2_grpc
import gateway_pb2
import gateway_pb2_grpc
import auth_pb2
import auth_pb2_grpc

class Client:
    def __init__(self, gateway_host, gateway_port):
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.channel = self.create_channel()
        self.stub = gateway_pb2_grpc.GatewayServiceStub(self.channel)
        self.keys = {}  # Store keys for authenticated accounts
        self.offline_queue = queue.Queue()  # Queue for offline payment transactions
        self.retry_counts = {}  # Track retry attempts
        self.lock = threading.Lock()  # Thread-safe queue operations
        self.retry_thread = None  # Retry thread

    def create_channel(self):
        """Create a secure gRPC channel."""
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
        return grpc.secure_channel(f'{self.gateway_host}:{self.gateway_port}', channel_credentials)

    def start_retry_thread(self):
        """Start a thread to retry offline payments."""
        self.retry_thread = threading.Thread(target=self.retry_offline_transactions, daemon=True)
        self.retry_thread.start()

    def retry_offline_transactions(self):
        """Retry queued payment transactions when the channel is ready."""
        while True:
            if not self.offline_queue.empty():
                with self.lock:
                    try:
                        request = self.offline_queue.queue[0]  # Peek at the head
                        txn_id = request.id
                        retry_count = self.retry_counts.get(txn_id, 0)

                        # Check channel state (Note: gRPC Python doesn’t have a direct `ready()` method; this is illustrative)
                        try:
                            grpc.channel_ready_future(self.channel).result(timeout=5)  # Wait up to 5 seconds
                            response = self.stub.ProcessBank(request)
                            print(f"Offline payment {txn_id} processed: {response.success} - {response.message}")
                            self.offline_queue.get()  # Remove from queue
                            del self.retry_counts[txn_id]
                        except grpc.FutureTimeoutError:
                            print(f"\n\nChannel not ready for {txn_id}. Waiting...\nCommand:")
                        except grpc.RpcError as err:
                            retry_count += 1
                            self.retry_counts[txn_id] = retry_count
                            if retry_count >= 5:
                                print(f"Payment {txn_id} failed after 5 retries: {err.details()}")
                                self.offline_queue.get()
                                del self.retry_counts[txn_id]
                            else:
                                print(f"Retry {retry_count}/5 for {txn_id} failed: {err.details()}")
                    except queue.Empty:
                        pass
            time.sleep(10)  # Retry every 10 seconds

    def register(self, username, password, bank_name, initial_amount):
        request = auth_pb2.RegisterRequest(
            username=username, password=password, bank_name=bank_name, initial_amount=initial_amount
        )
        try:
            response = self.stub.RegisterAccount(request)
            if response.success:
                print(f"Registered {username} at {bank_name} with account {response.account_number}")
                return response.account_number
            else:
                print(f"Registration failed: {response.message}")
                return None
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
                print(f"Login failed: {response.message}")
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
            id=txn_id, from_=from_acc, from_bank=from_bank, to=to_acc, to_bank=to_bank,
            amount=amount, timestamp=5000, key=from_key
        )
        try:
            response = self.stub.ProcessBank(request)
            print(f"Payment {txn_id} processed: {response.success} - {response.message}")
        except grpc.RpcError as err:
            print(f"Error processing payment {txn_id}: {err.details()}. Queuing for retry.")
            with self.lock:
                self.offline_queue.put(request)
                self.retry_counts[txn_id] = 0

def get_float_input(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Please enter a valid number.")

def main(gateway_host, gateway_port):
    client = Client(gateway_host, gateway_port)
    client.start_retry_thread()

    print("Available commands: register, login, balance, payment, exit")
    while True:
        command = input("\nEnter command: ").strip().lower()
        if command == "exit":
            print("Exiting...")
            break
        elif command == "register":
            username = input("Enter username: ")
            password = input("Enter password: ")
            bank_name = input("Enter bank name (e.g., bank_a): ")
            initial_amount = get_float_input("Enter initial amount: ")
            client.register(username, password, bank_name, initial_amount)
        elif command == "login":
            username = input("Enter username: ")
            password = input("Enter password: ")
            bank_name = input("Enter bank name (e.g., bank_a): ")
            client.login(username, password, bank_name)
        elif command == "balance":
            account_number = input("Enter account number: ")
            bank_name = input("Enter bank name (e.g., bank_a): ")
            client.get_balance(account_number, bank_name)
        elif command == "payment":
            txn_id = input("Enter transaction ID: ")
            from_acc = input("Enter sender account number: ")
            from_bank = input("Enter sender bank name (e.g., bank_a): ")
            to_acc = input("Enter recipient account number: ")
            to_bank = input("Enter recipient bank name (e.g., bank_a): ")
            amount = get_float_input("Enter amount: ")
            client.process_payment(txn_id, from_acc, from_bank, to_acc, to_bank, amount)
        else:
            print("Invalid command.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python client.py <gateway_port>")
        sys.exit(1)
    gateway_host = "localhost"
    gateway_port = sys.argv[1]
    main(gateway_host, gateway_port)