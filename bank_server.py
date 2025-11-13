import grpc
from concurrent import futures
import sys

import bank_pb2 
import bank_pb2_grpc 

import uuid
import hashlib

import os

import json

import auth_pb2
import auth_pb2_grpc

from threading import Lock

from cryptography.fernet import Fernet

import logging

import base64

from grpc_interceptor import ServerInterceptor


class BankService(bank_pb2_grpc.BankServiceServicer):
    def __init__(self,bank_name,all_accounts,lock):
        self.bank_name=bank_name
        self.accounts=all_accounts
        self.prepared_transaction={}
        self.lock=lock

    def register_account(self, username, password, initial_amount):
        # Generate a unique account number
        account_number = str(uuid.uuid4())
        # Generate the encryption key
        key = generate_key(username, password)
        # Store account details
        self.accounts[account_number] = {
            'username': username,
            'password': password,  # Note: In a real system, store a hash
            'balance': initial_amount,
            'key': key
        }
        return account_number

    def login_account(self):
        pass
    def GetBalance(self, request, context):
        print("RAN")
        print(self.accounts)
        with self.lock:
            account = self.accounts.get(request.number)
            if not account:
                return bank_pb2.BalanceResponse(error=True, message="Account not found")
            if account['key'] != request.key:  # Compare keys as strings
                return bank_pb2.BalanceResponse(error=True, message="Unauthorized")
            return bank_pb2.BalanceResponse(balance=account['balance'], error=False)

    def Prepare(self,request,context):
        print("Prepare started")
        with self.lock:
            #sender
            if request.id in self.prepared_transaction:
                print(f"{self.bank_name}: Duplicate transaction ID {request.id} found")
                return bank_pb2.PrepareResponse(can_commit=False)  # Reject duplicate
            print(request.from_)
            print(self.accounts)
            is_sender = request.from_bank == self.bank_name and request.from_ in self.accounts
            is_recipient = request.to_bank == self.bank_name and request.to in self.accounts
            print("BANK:",request.from_bank,self.bank_name)
            print("So, is this a sender:",is_sender)
            if not is_sender and not is_recipient:
                print(f"{self.bank_name} No relevant account")
                return bank_pb2.PrepareResponse(can_commit=False)

            if is_sender:
                print("It is the sender")
                if self.accounts[request.from_]["balance"]<request.amount:
                    print("Insufficient funds")
                    return bank_pb2.PrepareResponse(can_commit=False)
                else:
                    self.accounts[request.from_]["balance"]-=request.amount
                    self.prepared_transaction[request.id]=request
                    self.prepared_transaction[request.id] = {'role': 'sender', 'amount': request.amount}
                    print(f"{self.bank_name} PREPARED as sender")
                    # return bank_pb2.PrepareResponse(can_commit=True)
            #receiver
            if is_recipient:
                print("It is the receiver")
                self.prepared_transaction[request.id] = {'role': 'recipient', 'amount': request.amount}
                print(f"{self.bank_name} PREPARED as recipient")
            return bank_pb2.PrepareResponse(can_commit=True)
            # else:
            #     print(f"{self.bank_name} No relevant account")
            #     return bank_pb2.PrepareResponse(can_commit=False)


    def Commit(self, request, context):
        with self.lock:
            if request.id in self.prepared_transaction:
                role = self.prepared_transaction[request.id]['role']
                if role == 'recipient':
                    self.accounts[request.to]["balance"] += self.prepared_transaction[request.id]['amount']
                    print(f"{self.bank_name} COMMITTED as recipient")
                # Sender already deducted funds in Prepare, so no action needed
                del self.prepared_transaction[request.id]
                return bank_pb2.OperationResponse(success=True)
            print(f"{self.bank_name} Commit failed: no prepared transaction")
            return bank_pb2.OperationResponse(success=False)

    def Abort(self, request, context):
        with self.lock:
            if request.id in self.prepared_transaction:
                role = self.prepared_transaction[request.id]['role']
                if role == 'sender':
                    self.accounts[request.from_]["balance"] += self.prepared_transaction[request.id]['amount']
                    print(f"{self.bank_name} ABORTED as sender")
                # Recipient didn’t add funds yet, so no action needed
                del self.prepared_transaction[request.id]
                return bank_pb2.OperationResponse(success=True)
            print(f"{self.bank_name} Abort failed: no prepared transaction")
            return bank_pb2.OperationResponse(success=False)


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self, accounts,bank_name,all_accounts, lock):
        self.accounts = all_accounts
        self.lock = lock
        self.bank_name=bank_name
        # self.accounts = {}
        self.usernames=set()

    def RegisterAccount(self, request, context):
        with self.lock:
            if request.username in self.usernames:
                return auth_pb2.RegisterResponse(
                    account_number="",
                    success=False,
                    message=f"Username '{request.username}' is already registered in {self.bank_name}"
                )
            # Generate a unique account number
            account_number = str(uuid.uuid4())
            # Derive encryption key from username and password
            combined = request.username + request.password
            key = hashlib.sha256(combined.encode()).digest()[:32]  # 32 bytes for Fernet
            fernet_key = base64.urlsafe_b64encode(key)  # Fernet requires base64-encoded key
            # Store account details
            
            self.accounts[account_number] = {
                'username': request.username,
                'password': request.password,  # In practice, store a hash instead
                'balance': request.initial_amount,
                'key': fernet_key.decode()  # Encryption key for future use
            }
            self.usernames.add(request.username)
            return auth_pb2.RegisterResponse(
                account_number=account_number,
                message="Account registered successfully",
                success=True
            )

    def LoginAccount(self,request,context):
        with self.lock:
            if request.bank_name != self.bank_name:
                return auth_pb2.LoginResponse(message="Invalid bank name")
            for account_number, account in self.accounts.items():
                if account['username'] == request.username and account['password'] == request.password:
                    return auth_pb2.LoginResponse(
                        account_number=account_number,
                        key=account['key'],
                        message="Login successful"
                    )
            return auth_pb2.LoginResponse(message="Invalid credentials")

def serve(port,bank_name):
    server=grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    cert_dir = os.path.join(os.getcwd(), "certs")
    with open(os.path.join(cert_dir, f"{bank_name}.key"), 'rb') as f:
        private_key = f.read()
    with open(os.path.join(cert_dir, f"{bank_name}.crt"), 'rb') as f:
        certificate_chain = f.read()
    with open(os.path.join(cert_dir, "ca.crt"), 'rb') as f:
        root_certificates = f.read()

    # server_credentials = grpc.ssl_server  # type: ignore
    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(private_key, certificate_chain)],
        root_certificates=root_certificates,
        require_client_auth=True
    )
    
    lock=Lock()
    all_accounts = {
        # "bank_a": {"acc-123": 1000.0, "acc-456": 500.0},
        # "bank_b": {"acc-123": 2000.0, "acc-456": 1500.0}
    }
    bank_pb2_grpc.add_BankServiceServicer_to_server(BankService(bank_name,all_accounts,lock),server)
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(all_accounts,bank_name,all_accounts, lock), server)
    # server.add_secure_port(f'[::]:{port}',server_credentials)
    # print(f"Bank server {bank_name} working on port {port} with SSL/TLS")
    
    server.add_insecure_port(f'[::]:{port}')
    print(f"Bank server working on port {port}")
    server.start()
    server.wait_for_termination()


if __name__=="__main__":
    if len(sys.argv) != 3:
        print("Usage: python bank_server.py <port> <bank_name>")
        sys.exit(1)
    port = sys.argv[1]
    bank_name=sys.argv[2]

    logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=f'{bank_name}.log'
)

    logger = logging.getLogger('GatewayServer')
    
    serve(port,bank_name)