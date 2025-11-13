The main files are following for client:

client.py - testing
stress.py - stress testing
offline_queue.py - for offline payment testing. The final file to be shipped would be something like offline_queue.py, but for simulation, other files are created and are present


There are two bank servers, with and without logs.

It is assumed that server is never down, and hence, the values are stored in memory. If not for this assumption, we would be storing the files in json format with bank_name.json format, and open the file to read whenever the bank is opened the first time, and than make updates directly to the file itself.

Note: Certificates, on testing seemed to misbehave a bit
