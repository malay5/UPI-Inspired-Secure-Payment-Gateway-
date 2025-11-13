import grpc
from concurrent import futures
import sys
import logging
import uuid
import hashlib
import os
import json
import base64
from threading import Lock
from cryptography.fernet import Fernet
import bank_pb2
import bank_pb2_grpc
import auth_pb2
import auth_pb2_grpc

# Logging Interceptor
class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        method_name = handler_call_details.method
        logger.info(f"Incoming request: {method_name}")

        def logging_wrapper(behavior, request, context):
            try:
                self.log_request_details(request, method_name)
                response = behavior(request, context)
                self.log_response_details(response, method_name)
                return response
            except Exception as e:
                logger.error(f"Error in {method_name}: {str(e)}")
                raise

        return logging_wrapper

    def log_request_details(self, request, method_name):
        if method_name.endswith('GetBalance'):
            logger.info(f"GetBalance - Account: {request.number}, Key: {request.key}")
        elif method_name.endswith('Prepare'):
            logger.info(f"Prepare - Transaction ID: {request.id}, Amount: {request.amount}, From: {request.from_bank}:{request.from_}, To: {request.to_bank}:{request.to}")
        elif method_name.endswith('Commit'):
            logger.info(f"Commit - Transaction ID: {request.id}, To: {request.to}")
        elif method_name.endswith('Abort'):
            logger.info(f"Abort - Transaction ID: {request.id}, From: {request.from_}")
        elif method_name.endswith('RegisterAccount'):
            logger.info(f"RegisterAccount - Username: {request.username}, Initial Amount: {request.initial_amount}")
        elif method_name.endswith('LoginAccount'):
            logger.info(f"LoginAccount - Username: {request.username}, Bank: {request.bank_name}")

    def log_response_details(self, response, method_name):
        if isinstance(response, bank_pb2.BalanceResponse):
            logger.info(f"BalanceResponse - Error: {response.error}, Message: {response.message}, Balance: {response.balance if not response.error else 'N/A'}")
        elif isinstance(response, bank_pb2.PrepareResponse):
            logger.info(f"PrepareResponse - Can Commit: {response.can_commit}")
        elif isinstance(response, bank_pb2.OperationResponse):
            logger.info(f"OperationResponse - Success: {response.success}")
        elif isinstance(response, auth_pb2.RegisterResponse):
            logger.info(f"RegisterResponse - Success: {response.success}, Message: {response.message}, Account Number: {response.account_number}")
        elif isinstance(response, auth_pb2.LoginResponse):
            logger.info(f"LoginResponse - Message: {response.message}, Account Number: {response.account_number if response.message == 'Login successful' else 'N/A'}")

class BankService(bank_pb2_grpc.BankServiceServicer):
    def __init__(self, bank_name, all_accounts, lock):
        self.bank_name = bank_name
        self.accounts = all_accounts
        self.prepared_transaction = {}
        self.lock = lock

    def register_account(self, username, password, initial_amount):
        account_number = str(uuid.uuid4())
        key = generate_key(username, password)
        self.accounts[account_number] = {
            'username': username,
            'password': password,
            'balance': initial_amount,
            'key': key
        }
        return account_number

    def GetBalance(self, request, context):
        with self.lock:
            account = self.accounts.get(request.number)
            if not account:
                return bank_pb2.BalanceResponse(error=True, message="Account not found")
            if account['key'] != request.key:
                return bank_pb2.BalanceResponse(error=True, message="Unauthorized")
            return bank_pb2.BalanceResponse(balance=account['balance'], error=False)

    def Prepare(self, request, context):
        with self.lock:
            if request.id in self.prepared_transaction:
                logger.info(f"{self.bank_name}: Duplicate transaction ID {request.id} found")
                return bank_pb2.PrepareResponse(can_commit=False)
            is_sender = request.from_bank == self.bank_name and request.from_ in self.accounts
            is_recipient = request.to_bank == self.bank_name and request.to in self.accounts
            if not is_sender and not is_recipient:
                logger.info(f"{self.bank_name}: No relevant account for transaction {request.id}")
                return bank_pb2.PrepareResponse(can_commit=False)
            if is_sender:
                if self.accounts[request.from_]['balance'] < request.amount:
                    logger.info(f"{self.bank_name}: Insufficient funds for transaction {request.id}")
                    return bank_pb2.PrepareResponse(can_commit=False)
                else:
                    self.accounts[request.from_]['balance'] -= request.amount
                    self.prepared_transaction[request.id] = {'role': 'sender', 'amount': request.amount}
                    logger.info(f"{self.bank_name}: PREPARED as sender for transaction {request.id}")
            if is_recipient:
                self.prepared_transaction[request.id] = {'role': 'recipient', 'amount': request.amount}
                logger.info(f"{self.bank_name}: PREPARED as recipient for transaction {request.id}")
            return bank_pb2.PrepareResponse(can_commit=True)

    def Commit(self, request, context):
        with self.lock:
            if request.id in self.prepared_transaction:
                role = self.prepared_transaction[request.id]['role']
                if role == 'recipient':
                    self.accounts[request.to]['balance'] += self.prepared_transaction[request.id]['amount']
                    logger.info(f"{self.bank_name}: COMMITTED as recipient for transaction {request.id}")
                del self.prepared_transaction[request.id]
                return bank_pb2.OperationResponse(success=True)
            logger.info(f"{self.bank_name}: Commit failed for transaction {request.id}: no prepared transaction")
            return bank_pb2.OperationResponse(success=False)

    def Abort(self, request, context):
        with self.lock:
            if request.id in self.prepared_transaction:
                role = self.prepared_transaction[request.id]['role']
                if role == 'sender':
                    self.accounts[request.from_]['balance'] += self.prepared_transaction[request.id]['amount']
                    logger.info(f"{self.bank_name}: ABORTED as sender for transaction {request.id}")
                del self.prepared_transaction[request.id]
                return bank_pb2.OperationResponse(success=True)
            logger.info(f"{self.bank_name}: Abort failed for transaction {request.id}: no prepared transaction")
            return bank_pb2.OperationResponse(success=False)

class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self, accounts, bank_name, all_accounts, lock):
        self.accounts = all_accounts
        self.lock = lock
        self.bank_name = bank_name
        self.usernames = set()

    def RegisterAccount(self, request, context):
        with self.lock:
            if request.username in self.usernames:
                return auth_pb2.RegisterResponse(
                    account_number="",
                    success=False,
                    message=f"Username '{request.username}' is already registered in {self.bank_name}"
                )
            account_number = str(uuid.uuid4())
            combined = request.username + request.password
            key = hashlib.sha256(combined.encode()).digest()[:32]
            fernet_key = base64.urlsafe_b64encode(key)
            self.accounts[account_number] = {
                'username': request.username,
                'password': request.password,
                'balance': request.initial_amount,
                'key': fernet_key.decode()
            }
            self.usernames.add(request.username)
            return auth_pb2.RegisterResponse(
                account_number=account_number,
                message="Account registered successfully",
                success=True
            )

    def LoginAccount(self, request, context):
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

def generate_key(username, password):
    combined = username + password
    key = hashlib.sha256(combined.encode()).digest()[:32]
    return base64.urlsafe_b64encode(key).decode()

def serve(port, bank_name):
    # Configure logging with bank_name-specific file
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=f'{bank_name}.log'
    )
    global logger
    logger = logging.getLogger(f'BankServer_{bank_name}')

    # Create server with interceptor
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[LoggingInterceptor()]
    )

    cert_dir = os.path.join(os.getcwd(), "certs")
    with open(os.path.join(cert_dir, f"{bank_name}.key"), 'rb') as f:
        private_key = f.read()
    with open(os.path.join(cert_dir, f"{bank_name}.crt"), 'rb') as f:
        certificate_chain = f.read()
    with open(os.path.join(cert_dir, "ca.crt"), 'rb') as f:
        root_certificates = f.read()

    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(private_key, certificate_chain)],
        root_certificates=root_certificates,
        require_client_auth=True
    )

    lock = Lock()
    all_accounts = {}
    bank_pb2_grpc.add_BankServiceServicer_to_server(BankService(bank_name, all_accounts, lock), server)
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(all_accounts, bank_name, all_accounts, lock), server)

    # Uncomment for secure port
    server.add_secure_port(f'[::]:{port}', server_credentials)
    logger.info(f"Bank server {bank_name} started on port {port} with SSL/TLS")
    
    # Using insecure port as per your original code
    # server.add_insecure_port(f'[::]:{port}')
    logger.info(f"Bank server {bank_name} started on port {port}")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python bank_server.py <port> <bank_name>")
        sys.exit(1)
    port = sys.argv[1]
    bank_name = sys.argv[2]
    serve(port, bank_name)