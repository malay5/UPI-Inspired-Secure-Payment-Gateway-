import grpc
from concurrent import futures

import bank_pb2 
import bank_pb2_grpc

import gateway_pb2 
import gateway_pb2_grpc 

import logging

import time

from grpc_interceptor import ServerInterceptor

import auth_pb2_grpc
import auth_pb2
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='gateway.log'
)
logger = logging.getLogger('GatewayServer')

class LoggingInterceptor(ServerInterceptor):
    def __init__(self):
        self.retry_attempts = {}

    def intercept(self, method, request, context, method_name):
        # Extract client info from context
        client_info = context.peer()  # Gets client IP and port
        method_name_str = str(method_name).split('/')[-1]
        
        # Log request details
        request_info = {
            "method": method_name_str,
            "client": client_info,
            "timestamp": time.time()
        }
        
        # Add transaction-specific info for ProcessBank method
        if method_name_str == "ProcessBank":
            request_info.update({
                "amount": request.amount,
                "from_bank": request.from_bank,
                "to_bank": request.to_bank
            })
        
        logger.info(f"Request received: {request_info}")
        
        try:
            # Execute the RPC method
            start_time = time.time()
            response = method(request, context)
            duration = time.time() - start_time
            
            # Log successful response
            response_info = {
                "method": method_name_str,
                "client": client_info,
                "duration": f"{duration:.3f}s",
                "status": grpc.StatusCode.OK.name
            }
            
            if method_name_str == "ProcessBank":
                response_info["success"] = response.success
                response_info["message"] = response.message
                
            logger.info(f"Response sent: {response_info}")
            return response
            
        except grpc.RpcError as e:
            # Log error details
            error_info = {
                "method": method_name_str,
                "client": client_info,
                "error_code": e.code().name,
                "error_message": e.details()
            }
            logger.error(f"RPC failed: {error_info}")
            raise
            
        except Exception as e:
            # Log unexpected errors
            error_info = {
                "method": method_name_str,
                "client": client_info,
                "error_message": str(e)
            }
            logger.error(f"Unexpected error: {error_info}")
            raise
            
    def handle_retry(self, request, context, method_name):
        # Simple retry tracking (could be expanded for idempotency)
        request_id = f"{context.peer()}-{method_name}"
        self.retry_attempts[request_id] = self.retry_attempts.get(request_id, 0) + 1
        
        if self.retry_attempts[request_id] > 1:
            logger.warning(f"Retry attempt {self.retry_attempts[request_id]} for {request_id}")

class GatewayService(gateway_pb2_grpc.GatewayServiceServicer):
    def __init__(self):
        self.bank_to_ip = {
            "bank_a": "localhost:50055",  # BankA
            "bank_b": "localhost:50056",  # BankA
            "bank_c": "localhost:50057",  # BankB
            "bank_d": "localhost:50058",   # BankB
            "bank_e": "localhost:50059"   # BankB
        }

    def RegisterAccount(self,request,context):
        bank_address = self.bank_to_ip[request.bank_name]  # Hardcoded for simplicity
        with grpc.insecure_channel(bank_address) as channel:
            auth_stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = auth_stub.RegisterAccount(request)
            return response
    def Login(self,request,context):
        if request.bank_name not in self.bank_to_ip:
          return auth_pb2.LoginResponse(message="Bank not found")
        bank_address = self.bank_to_ip[request.bank_name]  # Hardcoded for simplicity
        with grpc.insecure_channel(bank_address) as channel:
            auth_stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = auth_stub.LoginAccount(request)
            return response

    def HealthCheck(self,request,context):
        return gateway_pb2.HealthCheck(up=True)
    def GetBalance(self,request,context):
        if request.bank_name in self.bank_to_ip:
            bank_address=self.bank_to_ip[request.bank_name]
        else:
            return bank_pb2.BalanceResponse(balance=0,error=True,message="No bank found")
        # bank_address="localhost:50055"
        # print("Called")

        with grpc.insecure_channel(bank_address) as channel:
            bank_stub=bank_pb2_grpc.BankServiceStub(channel)
            # bank_request=bank_pb2.Account(number=request.number)
            
            bank_request = bank_pb2.Account(
              number=request.number,
              bank_name=request.bank_name,
              key=request.key
            )
            print("Sending message 0") 
            try:
              print("Sending message 1")
              bank_response = bank_stub.GetBalance(bank_request)
              return bank_response
            except grpc.RpcError as e:
              return bank_pb2.BalanceResponse(balance=0, error=True, message=e.details())
            # bank_response=bank_stub.GetBalance(request)
            # return bank_pb2.BalanceResponse(balance=bank_response.balance,error=False)

    def ProcessBank(self,request,context):
        print("Processing payment")
        if request.from_bank not in self.bank_to_ip or request.to_bank not in self.bank_to_ip:
            return gateway_pb2.TransactionResponse(success=False,message="Bank not found")
            # bank_address=self.bank_to_ip[request.bank_name]
        # else:
        #     return gateway_pb2.PaymentResponse(success=False,message="Gateway Down")
        # bank_stub = bank_pb2_grpc.BankServiceStub(grpc.insecure_channel(bank_address))
        # with grpc.insecure_channel(bank_address) as channel:
        # bank_stub=bank_pb2_grpc.BankServiceStub(channel)
        print("Check 1 passed")
        if request.amount<=0:
            return gateway_pb2.TransactionResponse(success=False,message="Cannot send negative values")
        print("Check 2 passed")
        print(request)
        if request.from_bank==request.to_bank:
            involved_banks=[self.bank_to_ip[request.from_bank]]
            print("Check 3 passed, same bank")
        else:
            involved_banks=[self.bank_to_ip[request.from_bank],self.bank_to_ip[request.to_bank]]
            print("Check 3 passed, diff bank")
        prepared_=True
        print(involved_banks)
        try:
            for bank_ip_address in involved_banks:
                with grpc.insecure_channel(bank_ip_address) as channel:
                    print("Channel Created")
                    bank_stub=bank_pb2_grpc.BankServiceStub(channel)
                    prepare_response=bank_stub.Prepare(request)
                    if not prepare_response.can_commit:
                        prepared_=False
                        break
                    else:
                        print(f"{bank_ip_address} prepared")
        except Exception as e:
            print("ERROR:",e)
            return gateway_pb2.TransactionResponse(success=False,message="Some Issue")
        if prepared_:
            for bank_ip_address in involved_banks:
                with grpc.insecure_channel(bank_ip_address) as channel:
                    bank_stub=bank_pb2_grpc.BankServiceStub(channel)
                    commit_response=bank_stub.Commit(request)
                    if not commit_response.success:
                        return gateway_pb2.TransactionResponse(success=False,message="Commit Failed")
                        # break
            return gateway_pb2.TransactionResponse(success=True,message="Payment Successful")
        else:
            for bank_ip_address in involved_banks:
                with grpc.insecure_channel(bank_ip_address) as channel:
                    bank_stub=bank_pb2_grpc.BankServiceStub(channel)
                    bank_stub.Abort(request)
            return gateway_pb2.TransactionResponse(success=False,message="Invalid account, or insufficient funds, or both. ABORT!")
        
            
        
def serve(port):
    server=grpc.server(futures.ThreadPoolExecutor(max_workers=10),interceptors=[LoggingInterceptor()])
    cert_dir = os.path.join(os.getcwd(), "certs")
    with open(os.path.join(cert_dir, "gateway.key"), 'rb') as f:
        private_key = f.read()
    with open(os.path.join(cert_dir, "gateway.crt"), 'rb') as f:
        certificate_chain = f.read()
    with open(os.path.join(cert_dir, "ca.crt"), 'rb') as f:
        root_certificates = f.read()

    server_credentials = grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(private_key, certificate_chain)],
        root_certificates=root_certificates,
        require_client_auth=True
    )
    gateway_pb2_grpc.add_GatewayServiceServicer_to_server(GatewayService(),server)
    server.add_secure_port(f'[::]:{port}',server_credentials)
    # server.add_insecure_port(f'[::]:{port}')
    print(f"Gateway server started on port {port}")
    logger.info(f"Gateway came online on port {port}")
    server.start()
    server.wait_for_termination()

if __name__=="__main__":
    if len(sys.argv)!=2:
        print("Usage issue")
        sys.exit(1)
    port=sys.argv[1]
    serve(port)
        