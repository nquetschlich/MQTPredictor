import signal
import json
import numpy as np
from pytket import OpType
from qiskit import QuantumCircuit
import pandas as pd


def get_width_penalty():
    """Returns the penalty value if a quantum computer has not enough qubits."""
    width_penalty = 1000000
    return width_penalty


def count_qubit_gates_tket(qc, provider: str):
    """Returns the total gate count of single and two-qubit gates."""
    single_qubit_gates = 0
    two_qubit_gates = 0
    if provider == "ibm":
        # gates: ['rz', 'sx', 'x', 'cx']
        single_qubit_gates += qc.n_gates_of_type(OpType.Rz)
        single_qubit_gates += qc.n_gates_of_type(OpType.SX)
        single_qubit_gates += qc.n_gates_of_type(OpType.X)
        two_qubit_gates += qc.n_gates_of_type(OpType.CX)

    elif provider == "rigetti":
        # gates: rigetti_native_gates = ["rx", "rz", "cz"]
        single_qubit_gates += qc.n_gates_of_type(OpType.Rx)
        single_qubit_gates += qc.n_gates_of_type(OpType.Rz)
        two_qubit_gates += qc.n_gates_of_type(OpType.CZ)

    elif provider == "ionq":
        # gates: ionq_native_gates = ["ms", "rz", "ry", "rx"] or ["rxx", "rz", "ry", "rx"]
        single_qubit_gates += qc.n_gates_of_type(OpType.Rz)
        single_qubit_gates += qc.n_gates_of_type(OpType.Ry)
        single_qubit_gates += qc.n_gates_of_type(OpType.Rx)
        two_qubit_gates += qc.n_gates_of_type(OpType.XXPhase)

    elif provider == "oqc":
        # gates: oqc_gates = ["rz", "sx", "x", "ecr"]
        single_qubit_gates += qc.n_gates_of_type(OpType.Rz)
        single_qubit_gates += qc.n_gates_of_type(OpType.SX)
        single_qubit_gates += qc.n_gates_of_type(OpType.X)
        two_qubit_gates += qc.n_gates_of_type(OpType.ECR)
    return single_qubit_gates, two_qubit_gates


def count_qubit_gates_qiskit(qc, provider: str):
    """Returns the total gate count of single and two-qubit gates."""
    count_gates = qc.count_ops()
    single_qubit_gates = 0
    two_qubit_gates = 0
    if provider == "ibm":
        # gates: ['id', 'rz', 'sx', 'x', 'cx', 'reset']
        if "id" in count_gates:
            single_qubit_gates += count_gates["id"]
        if "rz" in count_gates:
            single_qubit_gates += count_gates["rz"]
        if "sx" in count_gates:
            single_qubit_gates += count_gates["sx"]
        if "x" in count_gates:
            single_qubit_gates += count_gates["x"]
        if "cx" in count_gates:
            two_qubit_gates += count_gates["cx"]

    elif provider == "rigetti":
        # gates: rigetti_native_gates = ["rx", "rz", "cz"]
        if "rx" in count_gates:
            single_qubit_gates += count_gates["rx"]
        if "rz" in count_gates:
            single_qubit_gates += count_gates["rz"]
        if "cz" in count_gates:
            two_qubit_gates += count_gates["cz"]

    elif provider == "ionq":
        # gates: ionq_native_gates = ["ms", "rz", "ry", "rx"] or ["rxx", "rz", "ry", "rx"]
        if "rx" in count_gates:
            single_qubit_gates += count_gates["rx"]
        if "ry" in count_gates:
            single_qubit_gates += count_gates["ry"]
        if "rz" in count_gates:
            single_qubit_gates += count_gates["rz"]
        if "rxx" in count_gates:
            two_qubit_gates += count_gates["rxx"]

    elif provider == "oqc":
        # gates: oqc_gates = ["rz", "sx", "x", "ecr"]
        if "rz" in count_gates:
            single_qubit_gates += count_gates["rz"]
        if "sx" in count_gates:
            single_qubit_gates += count_gates["sx"]
        if "x" in count_gates and not "sx" in count_gates:
            single_qubit_gates += count_gates["x"]
        if "ecr" in count_gates:
            two_qubit_gates += count_gates["ecr"]
    return single_qubit_gates, two_qubit_gates


def get_backend_information(name: str):
    """Returns the backend information for all used quantum computers."""
    if name == "ibm_washington":
        return get_ibm_washington()
    elif name == "ibm_montreal":
        return get_ibm_washington()
    elif name == "ionq":
        return get_ionq()
    elif name == "rigetti_m1":
        return get_rigetti_m1()
    elif name == "oqc_lucy":
        return get_oqc_lucy()


def calc_score_from_gates_list(count_gates, backend, num_qubits):
    """This is the evaluation function of a compilation path return its corresponding evaluation score."""
    penalty_factor_1q = 500
    penalty_factor_2q = 1000

    t_1 = backend["t1_avg"]
    t_2 = backend["t2_avg"]
    avg_gate_time_1q = backend["avg_gate_time_1q"]
    avg_gate_time_2q = backend["avg_gate_time_2q"]
    max_depth_1q = t_1 / avg_gate_time_1q
    max_depth_2q = t_1 / avg_gate_time_2q

    penalty_factor_fid_1q = 1
    penalty_factor_fid_2q = 10
    score = (
        1 - (np.power(backend["fid_1q"], count_gates[0]))
    ) * penalty_factor_fid_1q + (
        1 - (np.power(backend["fid_2q"], count_gates[1]))
    ) * penalty_factor_fid_2q

    # score = (
    #     count_gates[0] / max_depth_1q / num_qubits * penalty_factor_1q
    #     + count_gates[1] / max_depth_2q / num_qubits * penalty_factor_2q
    # )
    return score


def get_cmap_oqc_lucy():
    """Returns the coupling map of the OQC Lucy quantum computer."""
    # source: https://github.com/aws/amazon-braket-examples/blob/main/examples/braket_features/Verbatim_Compilation.ipynb

    # Connections are NOT bidirectional, this is not an accident
    c_map_oqc_lucy = [[0, 1], [0, 7], [1, 2], [2, 3], [7, 6], [6, 5], [4, 3], [4, 5]]

    return c_map_oqc_lucy


def get_cmap_rigetti_m1():
    """Returns a coupling map of the circular layout scheme used by Rigetti Aspen M1.

    Keyword arguments:
    """
    c_map_rigetti = []
    for j in range(5):
        for i in range(0, 7):
            c_map_rigetti.append([i + j * 10, i + 1 + j * 10])

            if i == 6:
                c_map_rigetti.append([0 + j * 10, 7 + j * 10])

    for j in range(4):
        c_map_rigetti.append([j * 10 + 2, j * 10 + 15])
        c_map_rigetti.append([j * 10 + 1, j * 10 + 16])

    for j in range(5):
        for i in range(0, 7):
            c_map_rigetti.append([i + j * 10 + 100, i + 1 + j * 10 + 100])

            if i == 6:
                c_map_rigetti.append([0 + j * 10 + 100, 7 + j * 10 + 100])

    for j in range(4):
        c_map_rigetti.append([j * 10 + 2 + 100, j * 10 + 15 + 100])
        c_map_rigetti.append([j * 10 + 1 + 100, j * 10 + 16 + 100])

    for j in range(5):
        c_map_rigetti.append([j * 10 + 4 + 100, j * 10 + 7])
        c_map_rigetti.append([j * 10 + 3 + 100, j * 10 + 0])

    inverted = [[item[1], item[0]] for item in c_map_rigetti]
    c_map_rigetti = c_map_rigetti + inverted

    return c_map_rigetti


def get_rigetti_m1():
    """Returns the backend information of the Rigetti M1 Aspen Quantum Computer."""
    rigetti_m1 = {
        "provider": "rigetti",
        "name": "m1",
        "num_qubits": 80,
        "t1_avg": 33.845,
        "t2_avg": 28.230,
        "avg_gate_time_1q": 60e-3,  # source: https://qcs.rigetti.com/qpus -> ASPEN-M-1
        "avg_gate_time_2q": 160e-3,  # source: https://qcs.rigetti.com/qpus -> ASPEN-M-1
        "fid_1q": get_rigetti_m1_fid1(),  # calculated by myself based on data sheet from aws
        "fid_2q": get_rigetti_m1_fid2(),  # calculated by myself based on data sheet from aws
    }
    return rigetti_m1


def get_ibm_washington():
    """Returns the backend information of the IBM Washington Quantum Computer."""
    ibm_washington = {
        "provider": "ibm",
        "name": "washington",
        "num_qubits": 127,
        "t1_avg": 103.39,
        "t2_avg": 97.75,
        "avg_gate_time_1q": 159.8e-3,  # estimated, based on the rigetti relation between 1q and 2q and given avg 2q time
        "avg_gate_time_2q": 550.41e-3,  # source: https://quantum-computing.ibm.com/services?services=systems&system=ibm_washington
        "fid_1q": 0.998401,  # from IBMQ website
        "fid_2q": 0.95439,  # from IBMQ website
    }
    return ibm_washington


def get_ibm_montreal():
    """Returns the backend information of the IBM Montreal Quantum Computer."""
    ibm_montreal = {
        "provider": "ibm",
        "name": "Montreal",
        "num_qubits": 27,
        "t1_avg": 120.55,
        "t2_avg": 74.16,
        "avg_gate_time_1q": 206e-3,  # estimated, based on the rigetti relation between 1q and 2q and given avg 2q time
        "avg_gate_time_2q": 426.159e-3,  # source: https://quantum-computing.ibm.com/services?services=systems&system=ibm_montreal
        "fid_1q": 0.9994951,  # from IBMQ website
        "fid_2q": 0.98129,  # from IBMQ website
    }
    return ibm_montreal


def get_ionq():
    """Returns the backend information of the 11-qubit IonQ Quantum Computer."""
    ionq = {
        "provider": "ionq",
        "name": "IonQ",
        "num_qubits": 11,
        "t1_avg": 10000,
        "t2_avg": 0.2,
        "avg_gate_time_1q": 0.00001,
        "avg_gate_time_2q": 0.0002,
        "fid_1q": 0.9963,  # from AWS
        "fid_2q": 0.9581,  # from AWS
    }
    return ionq


def get_oqc_lucy():
    """Returns the backend information of the OQC Lucy Quantum Computer."""
    oqc_lucy = {
        "provider": "oqc",
        "name": "Lucy",
        "num_qubits": 8,
        "t1_avg": 34.2375,
        "t2_avg": 49.2875,
        "avg_gate_time_1q": 60e-3,  # copied from Rigetti Aspen, number is NOT official from OQC itself
        "avg_gate_time_2q": 160e-3,  # copied from Rigetti Aspen, number is NOT official from OQC itself
        "fid_1q": 0.99905,  # from AWS averaged by myself
        "fid_2q": 0.9375,  # from AWS averaged by myself
    }
    return oqc_lucy


def get_openqasm_gates():
    """Returns a list of all quantum gates within the openQASM 2.0 standard header."""
    # according to https://github.com/Qiskit/qiskit-terra/blob/main/qiskit/qasm/libs/qelib1.inc
    gate_list = [
        "u3",
        "u2",
        "u1",
        "cx",
        "id",
        "u0",
        "u",
        "p",
        "x",
        "y",
        "z",
        "h",
        "s",
        "sdg",
        "t",
        "tdg",
        "rx",
        "ry",
        "rz",
        "sx",
        "sxdg",
        "cz",
        "cy",
        "swap",
        "ch",
        "ccx",
        "cswap",
        "crx",
        "cry",
        "crz",
        "cu1",
        "cp",
        "cu3",
        "csx",
        "cu",
        "rxx",
        "rzz",
        "rccx",
        "rc3x",
        "c3x",
        "c3sqrtx",
        "c4x",
    ]
    return gate_list


def get_machines():
    machines = [
        "qiskit_ionq_opt2",
        "qiskit_ibm_washington_opt2",
        "qiskit_ibm_montreal_opt2",
        "qiskit_rigetti_opt2",
        "qiskit_oqc_opt2",
        "qiskit_ionq_opt3",
        "qiskit_ibm_washington_opt3",
        "qiskit_ibm_montreal_opt3",
        "qiskit_rigetti_opt3",
        "qiskit_oqc_opt3",
        "tket_ionq",
        "tket_ibm_washington_line",
        "tket_ibm_montreal_line",
        "tket_rigetti_line",
        "tket_oqc_line",
        "tket_ibm_washington_graph",
        "tket_ibm_montreal_graph",
        "tket_rigetti_graph",
        "tket_oqc_graph",
    ]
    return machines


def get_rigetti_m1_fid1():
    """Calculates and returns the single gate fidelity for the Rigetti M1."""
    f = open("rigetti_m1_calibration.json")
    rigetti_json = json.load(f)

    fid1 = []
    for elem in rigetti_json["specs"]["1Q"]:
        # for elem2 in (rigetti_json["specs"]["1Q"][elem]):
        fid1.append(rigetti_json["specs"]["1Q"][elem]["f1QRB"])
    avg_fid1 = sum(fid1) / len(fid1)

    return avg_fid1


def get_rigetti_m1_fid2():
    """Calculates and returns the two gate fidelity for the Rigetti M1."""
    f = open("rigetti_m1_calibration.json")
    rigetti_json = json.load(f)
    fid2 = []
    for elem in rigetti_json["specs"]["2Q"]:
        val = rigetti_json["specs"]["2Q"][elem].get("fCZ")
        if val:
            fid2.append(val)
    avg_fid2 = sum(fid2) / len(fid2)
    return avg_fid2


def dict_to_featurevector(gate_dict, num_qubits):
    """Calculates and returns the feature vector of a given quantum circuit gate dictionary."""
    openqasm_gates_list = get_openqasm_gates()
    res_dct = {openqasm_gates_list[i] for i in range(0, len(openqasm_gates_list))}
    res_dct = dict.fromkeys(res_dct, 0)
    for key, val in dict(gate_dict).items():
        if key in res_dct:
            res_dct[key] = val

    res_dct["num_qubits"] = num_qubits
    return res_dct


def timeout_watcher(func, args, timeout):
    """Method that stops a function call after a given timeout limit."""

    class TimeoutException(Exception):  # Custom exception class
        pass

    def timeout_handler(signum, frame):  # Custom signal handler
        raise TimeoutException

    # Change the behavior of SIGALRM
    signal.signal(signal.SIGALRM, timeout_handler)

    signal.alarm(timeout)
    try:
        res = func(*args)
    except TimeoutException:
        print("Calculation/Generation exceeded timeout limit for ", func, args[1:])
        return None
    except Exception as e:
        print("Something else went wrong: ", e)
        return None
    else:
        # Reset the alarm
        signal.alarm(0)

    return res


def get_compiled_output_folder():
    return "qasm_compiled/"


def calc_eval_score_for_qc(qc_path):
    # read qasm to Qiskit Quantumcircuit
    qc = QuantumCircuit.from_qasm_file(qc_path)
    res = 1
    if "ibm_washington" in qc_path:
        df = pd.read_csv("ibmq_washington_calibrations.csv")
        for instruction, qargs, cargs in qc.data:
            gate_type = instruction.name
            qubit_indices = [elem.index for elem in qargs]
            first_qubit = int(qubit_indices[0])
            index = 0
            specific_error = 0
            if gate_type == "sx":
                index = 10
            elif gate_type == "x":
                index = 11
            elif gate_type == "cx":
                index = 12
            elif gate_type == "measure":
                index = 5
            if index == 12:
                tmp = str(qubit_indices[0]) + "_" + str(qubit_indices[1])
                for elem in df.loc[1][12].split(";"):
                    if tmp in elem.split(":")[0]:
                        specific_error = elem.split(":")[1]
            elif index in [5, 10, 11]:
                specific_error = df.loc[first_qubit][index]

            res *= 1 - specific_error

    elif "ibm_montreal" in qc_path:
        df = pd.read_csv("ibmq_montreal_calibrations.csv")
        for instruction, qargs, cargs in qc.data:
            gate_type = instruction.name
            qubit_indices = [elem.index for elem in qargs]
            first_qubit = int(qubit_indices[0])
            index = 0
            specific_error = 0
            if gate_type == "sx":
                index = 10
            elif gate_type == "x":
                index = 11
            elif gate_type == "cx":
                index = 12
            elif gate_type == "measure":
                index = 5
            if index == 12:
                tmp = str(qubit_indices[0]) + "_" + str(qubit_indices[1])
                for elem in df.loc[1][12].split(";"):
                    if tmp in elem.split(":")[0]:
                        specific_error = elem.split(":")[1]
            elif index in [5, 10, 11]:
                specific_error = df.loc[first_qubit][index]

            res *= 1 - specific_error
    elif "oqc" in qc_path:
        with open("oqc_lucy_calibration.json", "r") as f:
            backend = json.load(f)

        for instruction, qargs, cargs in qc.data:
            gate_type = instruction.name
            qubit_indices = [elem.index for elem in qargs]
            if len(qubit_indices) == 1 and gate_type != "measure":
                specific_fidelity = backend["oneQubitProperties"][
                    str(qubit_indices[0])
                ]["oneQubitFidelity"][0]["fidelity"]
            elif len(qubit_indices) == 1 and gate_type == "measure":
                specific_fidelity = backend["oneQubitProperties"][
                    str(qubit_indices[0])
                ]["oneQubitFidelity"][1]["fidelity"]
            elif len(qubit_indices) == 2:
                tmp = str(qubit_indices[0]) + "-" + str(qubit_indices[1])
                specific_fidelity = backend["twoQubitProperties"][tmp][
                    "twoQubitGateFidelity"
                ][0]["fidelity"]

            res *= specific_fidelity
    elif "rigetti" in qc_path:
        with open("rigetti_m1_calibration.json", "r") as f:
            backend = json.load(f)

        for instruction, qargs, cargs in qc.data:
            gate_type = instruction.name
            qubit_indices = [elem.index for elem in qargs]
            if len(qubit_indices) == 1 and gate_type != "measure":
                specific_fidelity = backend["specs"]["1Q"][str(qubit_indices[0])][
                    "f1QRB"
                ]
            elif len(qubit_indices) == 1 and gate_type == "measure":
                specific_fidelity = backend["specs"]["1Q"][str(qubit_indices[0])]["fRO"]
            elif len(qubit_indices) == 2:
                tmp = str(qubit_indices[0]) + "-" + str(qubit_indices[1])
                specific_fidelity = backend["specs"]["2Q"][tmp]["fCZ"]

            res *= specific_fidelity

    elif "ionq" in qc_path:
        with open("ionq_calibration.json", "r") as f:
            backend = json.load(f)

        for instruction, qargs, cargs in qc.data:
            gate_type = instruction.name
            qubit_indices = [elem.index for elem in qargs]
            if len(qubit_indices) == 1:
                specific_fidelity = backend["fidelity"]["1Q"]["mean"]
            elif len(qubit_indices) == 2:
                specific_fidelity = backend["fidelity"]["2Q"]["mean"]
            res *= specific_fidelity
    else:
        print("Error: No suitable backend found!")

    # add readout error
    # return res

    return res


def create_feature_vector(qc_path: str):
    qc = QuantumCircuit.from_qasm_file(qc_path)

    ops_list = qc.count_ops()
    feature_vector = dict_to_featurevector(ops_list, qc.num_qubits, qc.depth())
    return feature_vector


def read_rigetti_json():
    pass
