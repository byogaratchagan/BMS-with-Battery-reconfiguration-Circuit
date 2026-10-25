import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, _tree
import os

# Re-use the generation logic or just train on the spot
def generate_synthetic_data(num_samples=15000):
    np.random.seed(42)
    samples_per_class = num_samples // 3
    
    # 0: GOOD
    # OCV (Open Circuit Voltage) for GOOD is high
    good_ocv = np.random.normal(4.0, 0.1, samples_per_class)
    good_i = np.random.uniform(0.1, 4.5, samples_per_class) # Broad range of currents
    good_r = np.random.normal(15.0, 3.0, samples_per_class)
    # Voltage Sag: V = OCV - I * R (R in mOhm, so I*R/1000)
    good_v = good_ocv - (good_i * good_r / 1000.0)
    good_t = np.random.normal(25.0, 5.0, samples_per_class)
    good_soc = np.random.normal(85.0, 10.0, samples_per_class)
    good_cycle = np.random.normal(150, 80, samples_per_class)
    good_cap = np.random.normal(2800, 150, samples_per_class)
    
    # 1: DEGRADING
    deg_ocv = np.random.normal(3.7, 0.15, samples_per_class)
    deg_i = np.random.uniform(0.1, 4.0, samples_per_class)
    deg_r = np.random.normal(45.0, 8.0, samples_per_class)
    deg_v = deg_ocv - (deg_i * deg_r / 1000.0)
    deg_t = np.random.normal(35.0, 8.0, samples_per_class)
    deg_soc = np.random.normal(55.0, 15.0, samples_per_class)
    deg_cycle = np.random.normal(800, 200, samples_per_class)
    deg_cap = np.random.normal(2000, 250, samples_per_class)
    
    # 2: DEAD
    dead_ocv = np.random.normal(3.3, 0.2, samples_per_class)
    dead_i = np.random.uniform(0.1, 2.5, samples_per_class)
    dead_r = np.random.normal(100.0, 25.0, samples_per_class)
    dead_v = dead_ocv - (dead_i * dead_r / 1000.0)
    dead_t = np.random.normal(45.0, 10.0, samples_per_class)
    dead_soc = np.random.normal(20.0, 15.0, samples_per_class)
    dead_cycle = np.random.normal(1500, 400, samples_per_class)
    dead_cap = np.random.normal(800, 300, samples_per_class)
    
    v = np.concatenate([good_v, deg_v, dead_v])
    i = np.concatenate([good_i, deg_i, dead_i])
    t = np.concatenate([good_t, deg_t, dead_t])
    r = np.concatenate([good_r, deg_r, dead_r])
    soc = np.concatenate([good_soc, deg_soc, dead_soc])
    cycle = np.concatenate([good_cycle, deg_cycle, dead_cycle])
    cap = np.concatenate([good_cap, deg_cap, dead_cap])
    labels = [0]*samples_per_class + [1]*samples_per_class + [2]*samples_per_class # 0:DEAD, 1:DEGRADING, 2:GOOD (alphabetical order usually, but let's be explicit)
    # Actually LabelEncoder usually does alphabetical: DEAD:0, DEGRADING:1, GOOD:2
    
    df = pd.DataFrame({
        'v': v, 'i': i, 't': t, 'r': r, 'soc': soc, 'cycle': cycle, 'cap': cap
    })
    
    # Feature Engineering
    df['v_drop'] = (4.2 - df['v']) / (df['cycle'] + 1)
    df['r_trend'] = df['r'] / (df['cycle'] + 1)
    df['p'] = df['v'] * df['i']
    
    return df, labels

def tree_to_code(tree, feature_names):
    tree_ = tree.tree_
    feature_name = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else "undefined!"
        for i in tree_.feature
    ]

    def recurse(node, depth):
        indent = "  " * depth
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_name[node]
            threshold = tree_.threshold[node]
            code = f"{indent}if (features[{feature_names.index(name)}] <= {threshold:.6f}f) {{\n"
            code += recurse(tree_.children_left[node], depth + 1)
            code += f"{indent}}} else {{\n"
            code += recurse(tree_.children_right[node], depth + 1)
            code += f"{indent}}}\n"
            return code
        else:
            return f"{indent}return {np.argmax(tree_.value[node][0])};\n"

    return recurse(0, 1)

def main():
    X, y = generate_synthetic_data()
    feature_names = list(X.columns)
    
    clf = DecisionTreeClassifier(max_depth=5) # Shallow tree for ESP32
    clf.fit(X, y)
    
    cpp_code = """
/*
 * Generated Battery Health Model
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

int predict_health(float* features) {
"""
    cpp_code += tree_to_code(clf, feature_names)
    cpp_code += "}\n"
    
    with open("battery_model.h", "w") as f:
        f.write(cpp_code)
    
    print("Model exported to battery_model.h")

if __name__ == "__main__":
    main()
