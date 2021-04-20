import json
import os
import random

import boto3
import grpc
from google.protobuf import empty_pb2
import numpy as np
import scipy.stats as stats
import zmq

from aft_pb2 import *
from aft_pb2_grpc import *

lmbd = boto3.client('lambda')

N = 99999
x = np.arange(1, N)
a = 1.5
weights = x ** (-a)
weights /= weights.sum()
bounded_zipf = stats.rv_discrete(name='bounded_zipf', values=(x, weights))

sys_random = random.SystemRandom()

def handler(event, context):
    is_first = bool(int(event['count']) == 1)
    address = event['address']
    num_reads = int(event['reads'])
    if not is_first:
        txn = TransactionTag()
        txn.ParseFromString(bytes(event['txn'], 'utf-8'))

    num_keys = 10
    num_writes = num_keys - num_reads

    with grpc.insecure_channel(address + ':7654') as channel:
        client = AftStub(channel)
        if is_first:
            txn = client.StartTransaction(empty_pb2.Empty())
            address = txn.address

        keys = []
        for _ in range(num_keys):
            key = str(bounded_zipf.rvs(size=1)[0])
            keys.append(str(key))

        # Do the writes.
        for i in range(num_writes):
            update = KeyRequest(tid=txn.id)
            pair = update.pairs.add()
            pair.key = keys[0]
            pair.value = os.urandom(4096)
            client.Write(update)

        # Do the reads.
        for i in range(num_reads):
            update = KeyRequest(tid=txn.id)
            pair = update.pairs.add()
            pair.key = keys[i]
            client.Read(update)

        if not is_first:
            client.CommitTransaction(txn)

    if is_first:
        response = lmbd.invoke(FunctionName='aft-test',
                               Payload=json.dumps({
                                   'count': 2,
                                   'txn': str(txn.SerializeToString(),
                                              'utf-8'),
                                   'address': address
                               }),
                               InvocationType='RequestResponse')

        return response['Payload'].read()

    return "Success"

