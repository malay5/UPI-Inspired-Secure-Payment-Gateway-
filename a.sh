for cert in certs/*.crt; do
    echo "Checking $cert:"
    openssl x509 -in "$cert" -text -noout | grep Subject
    echo ""
done