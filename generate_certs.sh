#!/bin/bash

set -e
set -x

if ! command -v openssl &> /dev/null; then
    echo "Error: OpenSSL not found in Git Bash. Please ensure Git Bash is installed correctly."
    exit 1
fi

echo "Creating certs directory..."
mkdir -p certs || { echo "Failed to create certs directory"; exit 1; }
cd certs || { echo "Failed to change to certs directory"; exit 1; }

echo "Generating CA key and certificate..."
openssl genrsa -out ca.key 2048 || { echo "Failed to generate ca.key"; exit 1; }
cat > ca_config.txt <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = MyCA
EOF
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -out ca.crt -config ca_config.txt || { echo "Failed to generate ca.crt"; exit 1; }

echo "Generating Gateway Server key and certificate..."
openssl genrsa -out gateway.key 2048 || { echo "Failed to generate gateway.key"; exit 1; }
cat > gateway_config.txt <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = localhost
EOF
openssl req -new -key gateway.key -out gateway.csr -config gateway_config.txt || { echo "Failed to generate gateway.csr"; exit 1; }
openssl x509 -req -in gateway.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out gateway.crt -days 365 -sha256 || { echo "Failed to generate gateway.crt"; exit 1; }

for bank in bank_a bank_b bank_c bank_d bank_e; do
    echo "Generating key and certificate for $bank..."
    openssl genrsa -out "$bank.key" 2048 || { echo "Failed to generate $bank.key"; exit 1; }
    cat > "${bank}_config.txt" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = localhost
EOF
    openssl req -new -key "$bank.key" -out "$bank.csr" -config "${bank}_config.txt" || { echo "Failed to generate $bank.csr"; exit 1; }
    openssl x509 -req -in "$bank.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "$bank.crt" -days 365 -sha256 || { echo "Failed to generate $bank.crt"; exit 1; }
done

echo "Generating Client key and certificate..."
openssl genrsa -out client.key 2048 || { echo "Failed to generate client.key"; exit 1; }
cat > client_config.txt <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = client
EOF
openssl req -new -key client.key -out client.csr -config client_config.txt || { echo "Failed to generate client.csr"; exit 1; }
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365 -sha256 || { echo "Failed to generate client.crt"; exit 1; }

echo "Cleaning up CSR and config files..."
rm -f *.csr *_config.txt || { echo "Failed to clean up files"; exit 1; }

echo "Certificate generation completed successfully."
ls -l
