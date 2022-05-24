from predictor.src import qiskit_plugin, pytket_plugin, utils

from qiskit import QuantumCircuit
from pytket.extensions.qiskit import qiskit_to_tk

from joblib import dump, load
import numpy as np
from numpy import asarray, save
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Times New Roman"
import os
import glob
import argparse

from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import precision_recall_fscore_support
from sklearn.tree import plot_tree
from sklearn import tree

from natsort import natsorted


class Predictor:
    _clf = None

    def save_all_compilation_path_results(
        folder_path: str = "./qasm_files",
        timeout: int = 10,
    ):
        """Method to create pre-processed data to accelerate the training data generation afterwards. All .qasm files from
        the folder path are considered."""

        dictionary = {}
        for subdir, dirs, files in os.walk(folder_path):
            for file in natsorted(files):
                if "qasm" in file:
                    key = file.split("_")[
                        0
                    ]  # The key is the first 16 characters of the file name
                    group = dictionary.get(key, [])
                    group.append(file)
                    dictionary[key] = group

        print(dictionary.keys())
        for alg_class in dictionary:
            for benchmark in dictionary[alg_class]:
                filename = os.path.join(folder_path, benchmark)
                qc = QuantumCircuit.from_qasm_file(filename)

                print(benchmark)
                if not qc:
                    continue
                actual_num_qubits = qc.num_qubits
                if actual_num_qubits > 127:
                    break
                try:
                    qiskit_opt2 = qiskit_plugin.save_qiskit_compiled_circuits(
                        qc, 2, timeout=timeout, benchmark_name=benchmark
                    )

                    qiskit_opt3 = qiskit_plugin.save_qiskit_compiled_circuits(
                        qc, 3, timeout=timeout, benchmark_name=benchmark
                    )

                    qc_tket = qiskit_to_tk(qc)

                    tket_line_True = pytket_plugin.save_tket_compiled_circuits(
                        qc_tket, True, timeout=timeout, benchmark_name=benchmark
                    )

                    tket_line_False = pytket_plugin.save_tket_compiled_circuits(
                        qc_tket, False, timeout=timeout, benchmark_name=benchmark
                    )
                    all_results = (
                        qiskit_opt2 + qiskit_opt3 + tket_line_False + tket_line_True
                    )
                    if all(x is None for x in all_results):
                        break

                except Exception as e:
                    print("fail: ", e)

        return

    def generate_trainingdata_from_qasm_files(
        folder_path: str = "./qasm_files", compiled_path: str = "qasm_compiled/"
    ):
        """Method to create training data from pre-process data. All .qasm files from
        the folder_path used to find suitable pre-processed data in compiled_path."""

        if utils.init_all_config_files():
            print("Calibration files successfully initiated")
        else:
            print("Calibration files Initiation failed")
            return None

        # init resulting list (feature vector, name, scores)
        training_data = []
        name_list = []
        scores_list = []

        dictionary = {}
        # for each circuit in qasm_files
        for subdir, dirs, files in os.walk(folder_path):
            for file in natsorted(files):
                if "qasm" in file:
                    key = file.split("_")[
                        0
                    ]  # The key is the first 16 characters of the file name
                    group = dictionary.get(key, [])
                    group.append(file)
                    dictionary[key] = group

        print(dictionary.keys())
        for alg_class in dictionary:
            for benchmark in dictionary[alg_class]:
                print("Find: ", benchmark)
                scores = []
                for _ in range(19):
                    scores.append([])
                # iterate over all respective circuits in
                all_relevant_files = glob.glob(
                    compiled_path + benchmark.split(".")[0] + "*"
                )

                for filename in all_relevant_files:
                    if (
                        benchmark.split(".")[0] + "_"
                    ) in filename and filename.endswith(".qasm"):
                        # print("Found: ", filename)
                        # execute function call calc_eval_score_for_qc_and_backend
                        score = utils.calc_eval_score_for_qc(filename)
                        comp_path_index = int(filename.split("_")[-1].split(".")[0])
                        # print("Comp path index: ", comp_path_index, "\n")
                        scores[comp_path_index] = score

                num_not_empty_entries = 0
                for i in range(19):
                    if not scores[i]:
                        scores[i] = utils.get_width_penalty()
                    else:
                        num_not_empty_entries += 1

                if num_not_empty_entries == 0:
                    break

                feature_vec = utils.create_feature_vector(
                    os.path.join(folder_path, benchmark)
                )

                training_data.append((list(feature_vec.values()), np.argmax(scores)))
                name_list.append(benchmark.split(".")[0])
                scores_list.append(scores)

        return (training_data, name_list, scores_list)

    def train_decision_tree_classifier(X, y, name_list=None, actual_scores_list=None):
        """Method to for the actual training of the decision tree classifier."""

        X, y, indices = np.array(X), np.array(y), np.array(range(len(y)))

        non_zero_indices = []
        for i in range(len(X[0])):
            if sum(X[:, i]) > 0:
                non_zero_indices.append(i)
        X = X[:, non_zero_indices]
        data = asarray(non_zero_indices)
        save("non_zero_indices.npy", data)

        print("Number of used and non-zero features: ", len(non_zero_indices))

        (
            X_train,
            X_test,
            y_train,
            y_test,
            indices_train,
            indices_test,
        ) = train_test_split(X, y, indices, test_size=0.3, random_state=5)

        tree_param = [
            {
                "criterion": ["entropy", "gini"],
                "max_depth": [i for i in range(1, 15, 1)],
                "min_samples_split": [i for i in range(2, 20, 4)],
                "min_samples_leaf": [i for i in range(2, 20, 4)],
                "max_leaf_nodes": [i for i in range(2, 200, 40)],
                "max_features": [i for i in range(1, len(non_zero_indices), 10)],
            },
        ]
        Predictor._clf = GridSearchCV(
            tree.DecisionTreeClassifier(random_state=5), tree_param, cv=5, n_jobs=8
        )
        Predictor._clf = Predictor._clf.fit(X_train, y_train)
        print("Best GridSearch Estimator: ", Predictor._clf.best_estimator_)
        print("Best GridSearch Params: ", Predictor._clf.best_params_)
        print("Num Training Circuits: ", len(X_train))
        print("Num Test Circuits: ", len(X_test))
        print("Best Training accuracy: ", Predictor._clf.best_score_)
        dump(Predictor._clf, "decision_tree_classifier.joblib")

        y_pred = np.array(list(Predictor._clf.predict(X_test)))
        print("Test accuracy: ", np.mean(y_pred == y_test))
        print("Compilation paths from Train Data: ", set(y_train))
        print("Compilation paths from Test Data: ", set(y_test))
        print("Compilation paths from Predictions: ", set(y_pred))

        openqasm_qc_list = utils.get_openqasm_gates()
        res = [openqasm_qc_list[i] for i in range(0, len(openqasm_qc_list))]
        res.append("num_qubits")
        res.append("depth")
        for i in range(1, 6):
            res.append(str(i) + "_max_interactions")

        res = [res[i] for i in non_zero_indices]
        machines = utils.get_machines()
        fig = plt.figure(figsize=(17, 6))
        plot_tree(
            Predictor._clf.best_estimator_,
            feature_names=res,
            class_names=[machines[i] for i in list(Predictor._clf.classes_)],
            filled=True,
            impurity=True,
            rounded=True,
        )
        plt.savefig("decisiontree.pdf")

        names_list_filtered = [name_list[i] for i in indices_test]
        scores_filtered = [actual_scores_list[i] for i in indices_test]

        Predictor.plot_eval_all_detailed_compact_normed(
            names_list_filtered, scores_filtered, y_pred, y_test
        )
        Predictor.plot_eval_histogram(scores_filtered, y_pred, y_test)

        res = precision_recall_fscore_support(y_test, y_pred)

        with open("precision_recall_fscore.csv", "w") as csvfile:
            np.savetxt(
                csvfile,
                np.array([list(set(list(y_test) + list(y_pred)))]),
                delimiter=",",
                fmt="%s",
            )
            np.savetxt(csvfile, np.round(np.array(res), 3), delimiter=",", fmt="%s")

        return np.mean(y_pred == y_test)

    def plot_eval_histogram(scores_filtered, y_pred, y_test):
        res = []
        for i in range(len(y_pred)):
            assert np.argmax(scores_filtered[i]) == y_test[i]
            predicted_score = scores_filtered[i][y_pred[i]]
            score = list(np.sort(scores_filtered[i])[::-1]).index(predicted_score)
            res.append(score + 1)

        assert len(res) == len(y_pred)

        plt.figure(figsize=(10, 5))

        num_of_comp_paths = len(utils.get_machines())
        bars = plt.bar(
            [i for i in range(1, num_of_comp_paths + 1, 1)],
            height=[
                res.count(i) / len(res) for i in range(1, num_of_comp_paths + 1, 1)
            ],
            width=1,
        )
        plt.xticks(
            [i for i in range(1, num_of_comp_paths + 1, 1)],
            [i for i in range(1, num_of_comp_paths + 1, 1)],
        )

        sum = 0
        for bar in bars:
            yval = bar.get_height()
            rounded_val = str(np.round(yval * 100, 1)) + "%"
            if np.round(yval * 100, 1) > 0.0:
                sum += np.round(yval * 100, 1)
                plt.text(bar.get_x(), yval + 0.005, rounded_val)

        plt.tick_params(left=False, labelleft=False)
        plt.box(False)

        plt.xlabel(
            "Best prediction                                                        Worst prediction",
            fontsize=18,
        )
        plt.ylabel("Relative frequency", fontsize=18)
        plt.savefig("hist_predictions.pdf")
        plt.show()
        print("sum: ", sum)

    def plot_eval_all_detailed_compact_normed(
        names_list, scores_filtered, y_pred, y_test
    ):

        # Create list of all qubit numbers and sort them
        names_list_num_qubits = []
        for i in range(len(names_list)):
            assert np.argmax(scores_filtered[i]) == y_test[i]
            names_list_num_qubits.append(
                int(names_list[i].split("_")[-1].split(".")[0])
            )

        # Sort all other list (num_qubits, scores and y_pred) accordingly

        (
            qubit_list_sorted,
            scores_filtered_sorted_accordingly,
            y_pred_sorted_accordingly,
        ) = zip(*sorted(zip(names_list_num_qubits, scores_filtered, y_pred)))
        plt.figure(figsize=(17, 8))
        print("# Entries Graph: ", len(names_list_num_qubits))
        for i in range(len(names_list_num_qubits)):
            tmp_res = scores_filtered_sorted_accordingly[i]
            max_score = max(tmp_res)
            for j in range(len(tmp_res)):
                plt.plot(i, tmp_res[j] / max_score, "b.", alpha=1.0, markersize=1.7)

            plt.plot(
                i,
                tmp_res[y_pred_sorted_accordingly[i]] / max_score,
                "#ff8600",
                marker=".",
                linestyle="None",
            )

        plt.xticks(
            [i for i in range(0, len(scores_filtered), 10)],
            [qubit_list_sorted[i] for i in range(0, len(scores_filtered), 10)],
        )

        plt.xlabel(
            "Unseen test circuits (sorted along the number of qubits)", fontsize=18
        )
        plt.ylabel(
            "Evaluation scores of combinations of options \n (normalized per test circuit)",
            fontsize=18,
        )
        plt.tight_layout()

        plt.ylim(0, 1.05)
        plt.xlim(0, len(scores_filtered))

        plt.savefig("y_pred_eval_normed.pdf")

        return

    def predict(qasm_path: str):
        """Compilation path prediction for a given qasm file file."""
        if not (".qasm" in qasm_path):
            print("Input is not a .qasm file.")
            return

        if Predictor._clf is None:
            if os.path.isfile("decision_tree_classifier.joblib"):
                Predictor._clf = load("decision_tree_classifier.joblib")
            else:
                print("Fail: Decision Tree Classifier is neither trained nor saved!")
                return None

        feature_vector = list(utils.create_feature_vector(qasm_path).values())

        non_zero_indices = np.load("non_zero_indices.npy", allow_pickle=True)
        feature_vector = [feature_vector[i] for i in non_zero_indices]

        return Predictor._clf.predict([feature_vector])[0]

    def compile_predicted_compilation_path(qasm_str_or_path: str, prediction: int):
        """Returns the compiled quantum circuit as a qasm string when the original qasm circuit is provided as either
        a string or a file path and the prediction index is given."""

        if prediction < 0 or prediction > len(utils.get_machines()):
            print("Provided prection is faulty.")
            return None
        compilation_path = utils.get_machines()[prediction]

        if ".qasm" in qasm_str_or_path:
            print("Reading from .qasm path: ", qasm_str_or_path)
            qc = QuantumCircuit.from_qasm_file(qasm_str_or_path)
        elif QuantumCircuit.from_qasm_str(qasm_str_or_path):
            print("Reading from .qasm str")
            qc = QuantumCircuit.from_qasm_str(qasm_str_or_path)
        qc_tket = qiskit_to_tk(qc)

        if compilation_path == "qiskit_ionq_opt2":
            compiled_qc = qiskit_plugin.get_ionq_qc(qc, 2)
        elif compilation_path == "qiskit_ibm_washington_opt2":
            compiled_qc = qiskit_plugin.get_ibm_washington_qc(qc, 2)
        elif compilation_path == "qiskit_ibm_montreal_opt2":
            compiled_qc = qiskit_plugin.get_ibm_montreal_qc(qc, 2)
        elif compilation_path == "qiskit_rigetti_opt2":
            compiled_qc = qiskit_plugin.get_rigetti_qc(qc, 2)
        elif compilation_path == "qiskit_oqc_opt2":
            compiled_qc = qiskit_plugin.get_oqc_qc(qc, 2)
        elif compilation_path == "qiskit_ionq_opt3":
            compiled_qc = qiskit_plugin.get_ionq_qc(qc, 3)
        elif compilation_path == "qiskit_ibm_washington_opt3":
            compiled_qc = qiskit_plugin.get_ibm_washington_qc(qc, 3)
        elif compilation_path == "qiskit_ibm_montreal_opt3":
            compiled_qc = qiskit_plugin.get_ibm_montreal_qc(qc, 3)
        elif compilation_path == "qiskit_rigetti_opt3":
            compiled_qc = qiskit_plugin.get_rigetti_qc(qc, 3)
        elif compilation_path == "qiskit_oqc_opt3":
            compiled_qc = qiskit_plugin.get_oqc_qc(qc, 3)
        elif compilation_path == "tket_ionq":
            compiled_qc = pytket_plugin.get_ionq_qc(qc_tket)
        elif compilation_path == "tket_ibm_washington_line":
            compiled_qc = pytket_plugin.get_ibm_washington_qc(qc_tket, True)
        elif compilation_path == "tket_ibm_montreal_line":
            compiled_qc = pytket_plugin.get_ibm_montreal_qc(qc_tket, True)
        elif compilation_path == "tket_rigetti_line":
            compiled_qc = pytket_plugin.get_rigetti_qc(qc_tket, True)
        elif compilation_path == "tket_oqc_line":
            compiled_qc = pytket_plugin.get_oqc_qc(qc_tket, True)
        elif compilation_path == "tket_ibm_washington_graph":
            compiled_qc = pytket_plugin.get_ibm_washington_qc(qc_tket, False)
        elif compilation_path == "tket_ibm_montreal_graph":
            compiled_qc = pytket_plugin.get_ibm_montreal_qc(qc_tket, False)
        elif compilation_path == "tket_rigetti_graph":
            compiled_qc = pytket_plugin.get_rigetti_qc(qc_tket, False)
        elif compilation_path == "tket_oqc_graph":
            compiled_qc = pytket_plugin.get_oqc_qc(qc_tket, False)

        return compiled_qc


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Create Training Data")

    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--path", type=str, default="qasm_files")

    args = parser.parse_args()

    Predictor.save_all_compilation_path_results(
        folder_path=args.path, timeout=args.timeout
    )
    # Predictor.generate_trainingdata_from_qasm_files(folder_path="gentest/")
