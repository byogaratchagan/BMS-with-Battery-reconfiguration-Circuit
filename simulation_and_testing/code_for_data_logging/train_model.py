import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.tree import _tree
import os

# 1. Generate Synthetic Dataset (NASA Aging Profile + Catastrophic Faults)
np.random.seed(42)
N = 15000

# Normal Aging Chemistry Profile (NASA RW-style)
cycles = np.random.uniform(0, 2000, N)
capacity = 2600 - (cycles * 0.6) + np.random.normal(0, 40, N)
ir = 20 + (cycles * 0.025) + np.random.normal(0, 1.5, N)
soc = np.random.uniform(0, 100, N)
# Standard Li-Ion discharge curve approx
voltage = 3.0 + (soc / 100.0) * 1.2 + np.random.normal(0, 0.02, N)
current = np.random.uniform(0, 3, N)
power = voltage * current
temp = 25 + (current * 2) + (ir * 0.1)

# Labels based on physical health (0=GOOD, 1=DEGRADING, 2=DEAD)
labels = np.zeros(N)
labels[(capacity <= 2100) | (ir >= 150)] = 1 # DEGRADING (Accommodating prototype wire resistance)
labels[(capacity <= 1500) | (ir >= 200)] = 2 # DEAD

# ---------------------------------------------------------
# INJECT CATASTROPHIC FAULTS (What the NASA dataset lacks)
# ---------------------------------------------------------

# Fault 1: Internal Cell Short (Voltage crashes below 3.0V despite normal IR and Cycles)
short_idx = np.random.choice(N, 800, replace=False)
voltage[short_idx] = np.random.uniform(1.5, 2.9, 800)
labels[short_idx] = 2 # DEAD

# Fault 2: Severe Dendrite Soft Short (Voltage sag is extremely high under load)
soft_short_idx = np.random.choice(np.setdiff1d(np.arange(N), short_idx), 500, replace=False)
voltage[soft_short_idx] = np.random.uniform(2.5, 3.2, 500)
soc[soft_short_idx] = np.random.uniform(60, 100, 500) # High SOC but low voltage!
labels[soft_short_idx] = 2 # DEAD

# Fault 3: IR Spike Anomaly (Corroded terminal / Tab failure)
tab_fail_idx = np.random.choice(np.setdiff1d(np.arange(N), np.concatenate([short_idx, soft_short_idx])), 400, replace=False)
ir[tab_fail_idx] = np.random.uniform(300, 500, 400) # Massive IR (Moved above 250 to ignore breadboard)
labels[tab_fail_idx] = 2 # DEAD

# Assemble features mapping to C++ array
X = np.column_stack([
    voltage, current, temp, ir, soc, cycles, capacity, 
    np.zeros(N), np.zeros(N), power
])
y = labels

# 2. Train the Machine Learning Model
clf = DecisionTreeClassifier(max_depth=7, random_state=42, min_samples_leaf=5)
clf.fit(X, y)

# 3. Export Model directly to raw C++ Code for ESP32
def tree_to_cpp(tree, feature_names):
    tree_ = tree.tree_
    feature_name = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else "undefined!"
        for i in tree_.feature
    ]
    
    code = "int predict_health(float* features) {\n"
    
    def recurse(node, depth):
        nonlocal code
        indent = "  " * depth
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_name[node]
            threshold = tree_.threshold[node]
            code += f"{indent}if (features[{name}] <= {threshold:.6f}f) {{\n"
            recurse(tree_.children_left[node], depth + 1)
            code += f"{indent}}} else {{\n"
            recurse(tree_.children_right[node], depth + 1)
            code += f"{indent}}}\n"
        else:
            value = tree_.value[node][0]
            class_idx = np.argmax(value)
            code += f"{indent}return {class_idx};\n"
            
    recurse(0, 1)
    code += "}\n"
    return code

feature_indices = [str(i) for i in range(10)]
cpp_code = tree_to_cpp(clf, feature_indices)

header = """/*
 * Edge-AI Battery Health Model (NASA Aging + Fault Tolerant)
 * Features order:
 * 0: Voltage (V)
 * 1: Current (A)
 * 2: Temperature (C)
 * 3: Internal Resistance (mOhm)
 * 4: SOC (%)
 * 5: Cycle Count
 * 6: Capacity (mAh)
 * 7: Voltage Drop Rate
 * 8: Resistance Trend
 * 9: Power (W)
 */

"""

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battery_model_new.h")
with open(out_path, "w") as f:
    f.write(header + cpp_code)

print(f"Successfully generated new fault-tolerant model at: {out_path}")
