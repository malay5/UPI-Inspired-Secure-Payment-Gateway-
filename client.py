import grpc
import sys

from concurrent import  futures

import bank_pb2 as bank_pb2
import bank_pb2_grpc as bank_pb2_grpc

import gateway_pb2 as gateway_pb2
import gateway_pb2_grpc as gateway_pb2_grpc

import bank_pb2 as bank_pb2  # Added for Account

import auth_pb2

import os
import auth_pb2_grpc

import time

import threading

import random

# def get_balance(stub,acc_no,bank_name):
#     request=bank_pb2.Account(number=acc_no,bank_name=bank_name)
#     try:
#         response=stub.GetBalance(request)
#         print(f"Balance for {bank_name} {acc_no}: {response.balance}")
#     except grpc.RpcError as err:
#         print(err)

# def process_payment(stub,txn_id,from_acc,from_bank,to_acc,to_bank,amount):
#     request=bank_pb2.Transaction(id=txn_id,from_=from_acc,from_bank=from_bank,to=to_acc,to_bank=to_bank,amount=amount,timestamp=5000)
#     try:
#         response=stub.ProcessBank(request)
#         print(f"Payment result: {response.success} - {response.message}")
#     except grpc.RpcError as err:
#         print(f"Error processing payment: {err.details()}")


# def register_account(stub, username, password, initial_amount):
#     request = auth_pb2.RegisterRequest(
#         username=username,
#         password=password,
#         initial_amount=initial_amount
#     )
#     try:
#         response = stub.RegisterAccount(request)
#         print(f"Registered account: {response.account_number} - {response.message}")
#     except grpc.RpcError as e:
#         print(f"Error registering account: {e.details()}")



# def run(bank_host,bank_port):
#     channel=grpc.insecure_channel(f'{bank_host}:{bank_port}')
#     stub=gateway_pb2_grpc.GatewayServiceStub(channel)

#     get_balance(stub,"acc-123",'bank_a')
#     get_balance(stub,"acc-456",'bank_a')
#     process_payment(stub,"txn-001","acc-123","bank_a","acc-456","bank_a",50)

#     get_balance(stub,"acc-123",'bank_a')
#     get_balance(stub,"acc-456",'bank_a')

#     alice_account = register_account(stub, "alice", "pass123", 1000.0)
#     bob_account = register_account(stub, "bob", "pass456", 500.0)

#     if alice_account:
#             get_balance(stub, alice_account, "bank_a")
#     if bob_account:
#         get_balance(stub, bob_account, "bank_a")

#     process_payment(stub, "txn-002", "acc-123", "bank_a", "acc-456", "bank_a", 50.0)
#     get_balance(stub, "acc-123", "bank_a")
#     get_balance(stub, "acc-456", "bank_a")

#     # get_balance(stub,"acc-123",'bank_b')
#     # get_balance(stub,"acc-456",'bank_a')
#     # process_payment(stub,"txn-002","acc-123","bank_b","acc-456","bank_a",50)

#     # get_balance(stub,"acc-123",'bank_a')
#     # get_balance(stub,"acc-456",'bank_b')
#     # process_payment(stub,"txn-003","acc-123","bank_a","acc-456","bank_b",50)

#     # get_balance(stub,"acc-123","bank_b")
#     # get_balance(stub,"acc-456","bank_b")
#     # process_payment(stub,"txn-004","acc-123","bank_b","acc-456","bank_b",50)


#     # print("Request:\n",request)
#     print()
#     print()

#     # try:
#     #     response=stub.GetBalance(request)
#     #     print(f"Balance for acc-123: {response.balance}")

#     # except grpc.RpcError as err:
#     #     print(err)


# # def serve():


# if __name__=="__main__":
#     if len(sys.argv) != 2:
#         print("Usage: python client.py <bank_port>")
#         sys.exit(1)
#     gateway_host = "localhost"
#     gateway_port = sys.argv[1]  # e.g., 50051
#     run(gateway_host, gateway_port)


import queue






class Client:
    def __init__(self, stub):
        self.stub = stub
        self.keys = {}

        self.offline_processing=queue.Queue()
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
            if response.success==False:
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
                # print("Received key is:",response.key)
                return response.account_number
            else:
                print(response.message)
                return None
        except grpc.RpcError as e:
            print(f"Error logging in: {e.details()}")
            return None

    def get_balance(self, account_number, bank_name):
        key = self.keys.get(f"{bank_name}_{account_number}")
        # print(key,"Fond key")
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
            timestamp=5000,
            key=from_key
        )
        try:
            response = self.stub.ProcessBank(request)
            print(f"Payment result: {response.success} - {response.message}")
        except grpc.RpcError as err:
            print(f"Error processing payment: {err.details()}")
            self.offline_processing.put(request)



def client_thread(client_id, stub, all_accounts):
    client = Client(stub)
    username = f"user_{client_id}"
    password = f"pass_{client_id}"
    bank_name = random.choice(["bank_a", "bank_b", "bank_c", "bank_d", "bank_e"])
    bank_name = random.choice(["bank_b"])
    initial_amount = random.uniform(500, 2000)  # Random initial balance between 500 and 2000

    # Register and login
    account_number = client.register(username, password, bank_name, initial_amount)
    if account_number:
        client.login(username, password, bank_name)
        all_accounts[account_number] = bank_name  # Store for transaction targets

    # Perform 10 random transactions
    for i in range(10):
        if not account_number:
            break
        # Choose a random recipient from all_accounts (excluding self)
        other_accounts = [acc for acc, bank in all_accounts.items() if acc != account_number]
        if not other_accounts:
            time.sleep(1)  # Wait for other clients to register
            continue
        to_acc = random.choice(other_accounts)
        to_bank = all_accounts[to_acc]
        amount = random.uniform(10, 100)  # Random transaction amount between 10 and 100
        txn_id = f"txn_{client_id}_{i}_{int(time.time())}"
        client.process_payment(txn_id, account_number, bank_name, to_acc, to_bank, amount)
        
        # Occasionally check balance
        if random.random() < 0.3:  # 30% chance to check balance
            client.get_balance(account_number, bank_name)
        
        # Small delay to avoid overwhelming the server
        time.sleep(random.uniform(0.1, 0.5))

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
        all_accounts = {}  # Shared dict to track account_number -> bank_name mappings
        threads = []

        # Start 20 client threads
        for client_id in range(20):
            thread = threading.Thread(target=client_thread, args=(client_id, stub, all_accounts))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Final balance check for all accounts
        client = Client(stub)
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