# Qubit Control System (QubiC) [1]

QubiC is an in-house developed FPGA based qubit control system developed at Lawrence Berkeley National Lab (LBNL) with the support of the US Department of Energy (DOE). The QubiC source code is released under a [LBNL modified BSD license](LICENSE).

This repo contains core supporting software for the QubiC 2.0 system. Currently, QubiC 2.0 is implemented on the Xilinx ZCU216 RFSoC evaluation board using a [pynq](http://www.pynq.io/) backend. The QubiC 2.0 gateware can be found [here](https://gitlab.com/LBL-QubiC/gateware/-/tree/rfsoc).

## Getting Started with QubiC on the ZCU216

1. Burn the pynq 3.0 [image](link/here) to a microSD card 
2. Boot the ZCU216 using the SD card (link/to/detailed/instructions)
3. Connect the board to a local network. The board should be assigned an IP (via your network's DHCP service), and you should be able to connect to it via ssh (username xilinx)
4. ssh into the board, and clone this repo somewhere on the local filesystem (be sure to clone using -b rfsoc to checkout the rfsoc branch)
5. Install using `sudo pip install -e /path/to/repo` where `path/to/repo` is the path to the directory containing the `setup.py`
6. Repeat steps 4 and 5 for [distproc](https://gitlab.com/LBL-QubiC/distributed_processor/-/tree/master/python) and [qubitconfig](https://gitlab.com/LBL-QubiC/experiments/qubitconfig)
7. That's it! The ZCU216 should now be configured with all the necessary software to load and run QubiC programs. See our [demo notebooks]() (coming soon) for instructive examples.

## Dependencies
- [distproc](https://gitlab.com/LBL-QubiC/distributed_processor/-/tree/master/python) (contains the low-level tools for compiling and assembling quantum programs)
- [qubitconfig](https://gitlab.com/LBL-QubiC/experiments/qubitconfig) (QubiC configuration management system, for storing and tracking gate-to-pulse calibrations)
- pynq
- numpy
- scipy
- scikit-learn
- matplotlib

## Other Relevant Repos
- [qubic gateware](https://gitlab.com/LBL-QubiC/gateware/-/tree/rfsoc) contains the complete FPGA design (written primarily in Verilog) for QubiC 2.0
- [distributed processor](https://gitlab.com/LBL-QubiC/distributed_processor) contains the HDL for the QubiC distributed processor, as well as the distproc module linked above
- [chip calibration](https://gitlab.com/LBL-QubiC/experiments/chipcalibration) contains calibration routines for superconducting qubits (in early-stage development)

1. https://arxiv.org/abs/2101.00071
