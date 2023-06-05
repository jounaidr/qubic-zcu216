"""
Script to start and run an xmlrpc server on the ZCU216
"""
import xmlrpc.server
from qubic.run import CircuitRunner
import logging
import argparse

def run_rpc_server(ip, port, xsa_commit):
    """
    Start an xmlrpc server that exposes an instance of CircuitRunner over a 
    network. Intended to be run from the RFSoC ARM core python (pynq) 
    environment. IP should only be accessible locally!

    Parameters
    ----------
        ip : str
        port : int
        xsa_commit : str
    """
    runner = CircuitRunner(commit=xsa_commit)

    server = xmlrpc.server.SimpleXMLRPCServer((ip, port), logRequests=True, allow_none=True)

    server.register_function(runner.load_circuit)
    server.register_function(runner.run_circuit)
    server.register_function(runner.run_circuit_batch)

    print('RPC server running on {}:{}'.format(ip, port))

    server.serve_forever()

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', default='192.168.1.247')
    parser.add_argument('--port', default=9095)
    parser.add_argument('--xsa-commit', default='81f773e5')
    args = parser.parse_args()

    run_rpc_server(args.ip, args.port, args.xsa_commit)


