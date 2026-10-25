import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, classification_report
import os
import warnings

warnings.filterwarnings('ignore')

# Set random seed for reproducibility
np.random.seed(42)

def generate_synthetic_data(num_samples=10000):
    print("Generating synthetic dataset...")
    
    # 1/3 for each category
    samples_per_class = num_samples // 3
    
    # Generate GOOD cells
    good_v = np.random.normal(4.1, 0.05, samples_per_class)
    good_i = np.random.normal(2.0, 0.2, samples_per_class)
    good_t = np.random.normal(25.0, 2.0, samples_per_class)
    good_r = np.random.normal(15.0, 2.0, samples_per_class)
    good_soc = np.random.normal(90.0, 5.0, samples_per_class)
    good_cycle = np.random.normal(100, 50, samples_per_class)
    good_cap = np.random.normal(3000, 100, samples_per_class)
    good_labels = ['GOOD'] * samples_per_class
    
    # Generate DEGRADING cells
    deg_v = np.random.normal(3.8, 0.1, samples_per_class)
    deg_i = np.random.normal(1.5, 0.3, samples_per_class)
    deg_t = np.random.normal(35.0, 4.0, samples_per_class)
    deg_r = np.random.normal(35.0, 5.0, samples_per_class)
    deg_soc = np.random.normal(60.0, 15.0, samples_per_class)
    deg_cycle = np.random.normal(600, 150, samples_per_class)
    deg_cap = np.random.normal(2200, 200, samples_per_class)
    deg_labels = ['DEGRADING'] * samples_per_class
    
    # Generate DEAD cells
    dead_v = np.random.normal(3.2, 0.2, samples_per_class)
    dead_i = np.random.normal(0.5, 0.2, samples_per_class)
    dead_t = np.random.normal(45.0, 6.0, samples_per_class)
    dead_r = np.random.normal(70.0, 15.0, samples_per_class)
    dead_soc = np.random.normal(20.0, 10.0, samples_per_class)
    dead_cycle = np.random.normal(1200, 250, samples_per_class)
    dead_cap = np.random.normal(1000, 300, samples_per_class)
    dead_labels = ['DEAD'] * samples_per_class
    
    # Combine
    v = np.concatenate([good_v, deg_v, dead_v])
    i = np.concatenate([good_i, deg_i, dead_i])
    t = np.concatenate([good_t, deg_t, dead_t])
    r = np.concatenate([good_r, deg_r, dead_r])
    soc = np.concatenate([good_soc, deg_soc, dead_soc])
    cycle = np.concatenate([good_cycle, deg_cycle, dead_cycle])
    cap = np.concatenate([good_cap, deg_cap, dead_cap])
    labels = good_labels + deg_labels + dead_labels
    
    df = pd.DataFrame({
        'Voltage (V)': v,
        'Current (A)': i,
        'Temperature (°C)': t,
        'Internal Resistance (mOhm)': r,
        'SOC (%)': soc,
        'Cycle Count': cycle,
        'Capacity (mAh)': cap,
        'Health Status': labels
    })
    
    # Clip values to realistic ranges
    df['Voltage (V)'] = df['Voltage (V)'].clip(2.5, 4.2)
    df['Current (A)'] = df['Current (A)'].clip(0, 5.0)
    df['Temperature (°C)'] = df['Temperature (°C)'].clip(-10, 80)
    df['Internal Resistance (mOhm)'] = df['Internal Resistance (mOhm)'].clip(5, 200)
    df['SOC (%)'] = df['SOC (%)'].clip(0, 100)
    df['Cycle Count'] = df['Cycle Count'].clip(0, 3000)
    df['Capacity (mAh)'] = df['Capacity (mAh)'].clip(0, 3500)
    
    # Introduce some missing values to demonstrate preprocessing
    missing_idx = np.random.choice(df.index, size=int(num_samples*0.05), replace=False)
    df.loc[missing_idx, 'Temperature (°C)'] = np.nan
    
    print(f"Dataset generated with shape: {df.shape}")
    return df

def preprocess_and_feature_engineering(df):
    print("Preprocessing and Feature Engineering...")
    
    # Handle missing values by filling with median
    df['Temperature (°C)'] = df['Temperature (°C)'].fillna(df['Temperature (°C)'].median())
    
    # Feature Engineering
    # 1. Voltage Drop Rate proxy
    df['Voltage_Drop_Rate'] = (4.2 - df['Voltage (V)']) / (df['Cycle Count'] + 1)
    
    # 2. Resistance Increase Trend proxy
    df['Resistance_Trend'] = df['Internal Resistance (mOhm)'] / (df['Cycle Count'] + 1)
    
    # 3. Power output proxy
    df['Power (W)'] = df['Voltage (V)'] * df['Current (A)']
    
    # Encode labels
    le = LabelEncoder()
    df['Target'] = le.fit_transform(df['Health Status'])
    
    # Features and Target
    X = df.drop(['Health Status', 'Target'], axis=1)
    y = df['Target']
    
    # Scale numerical features
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)
    
    return X_scaled, y, le, scaler

def train_and_evaluate_models(X_train, X_test, y_train, y_test, le):
    print("Training models...")
    
    models = {
        'Random Forest': RandomForestClassifier(n_estimators=100, random_state=42),
        'XGBoost': XGBClassifier(use_label_encoder=False, eval_metric='mlogloss', random_state=42),
        'Neural Network': MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=300, random_state=42)
    }
    
    results = []
    trained_models = {}
    
    for name, model in models.items():
        print(f"Training {name}...")
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, average='weighted')
        rec = recall_score(y_test, y_pred, average='weighted')
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        results.append({
            'Model': name,
            'Accuracy': acc,
            'Precision': prec,
            'Recall': rec,
            'F1 Score': f1
        })
        
        trained_models[name] = model
        
        print(f"\n--- {name} Classification Report ---")
        print(classification_report(y_test, y_pred, target_names=le.classes_))
        
    results_df = pd.DataFrame(results)
    return results_df, trained_models

def visualize_results(results_df, trained_models, X_test, y_test, le, feature_names):
    print("Generating visualizations...")
    os.makedirs('plots', exist_ok=True)
    
    # 1. Model Comparison Bar Chart
    plt.figure(figsize=(10, 6))
    results_melted = pd.melt(results_df, id_vars="Model", var_name="Metric", value_name="Score")
    sns.barplot(x="Model", y="Score", hue="Metric", data=results_melted)
    plt.title('Model Performance Comparison')
    plt.ylim(0.8, 1.0) # Adjust based on expected high performance
    plt.savefig('plots/model_comparison.png')
    plt.close()
    
    # 2. Confusion Matrices
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle('Confusion Matrices for Battery Health Classification')
    
    for ax, (name, model) in zip(axes, trained_models.items()):
        y_pred = model.predict(X_test)
        cm = confusion_matrix(y_test, y_pred)
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
                    xticklabels=le.classes_, yticklabels=le.classes_)
        ax.set_title(name)
        ax.set_xlabel('Predicted')
        ax.set_ylabel('Actual')
        
    plt.tight_layout()
    plt.savefig('plots/confusion_matrices.png')
    plt.close()
    
    # 3. Feature Importance (Random Forest)
    rf_model = trained_models['Random Forest']
    importances = rf_model.feature_importances_
    indices = np.argsort(importances)[::-1]
    
    plt.figure(figsize=(10, 6))
    plt.title("Feature Importances (Random Forest)")
    plt.bar(range(X_test.shape[1]), importances[indices], align="center")
    plt.xticks(range(X_test.shape[1]), [feature_names[i] for i in indices], rotation=45, ha='right')
    plt.xlim([-1, X_test.shape[1]])
    plt.tight_layout()
    plt.savefig('plots/feature_importances.png')
    plt.close()
    
    print("Visualizations saved to the 'plots' directory.")

def real_time_prediction_demo(model, scaler, le):
    print("\n--- Real-Time Prediction Demo ---")
    
    # Example raw sensor readings for a slightly degrading cell
    sample_data = {
        'Voltage (V)': [3.9],
        'Current (A)': [1.8],
        'Temperature (°C)': [30.5],
        'Internal Resistance (mOhm)': [25.0],
        'SOC (%)': [75.0],
        'Cycle Count': [400],
        'Capacity (mAh)': [2600]
    }
    
    df_new = pd.DataFrame(sample_data)
    
    # Feature Engineering for the new sample
    df_new['Voltage_Drop_Rate'] = (4.2 - df_new['Voltage (V)']) / (df_new['Cycle Count'] + 1)
    df_new['Resistance_Trend'] = df_new['Internal Resistance (mOhm)'] / (df_new['Cycle Count'] + 1)
    df_new['Power (W)'] = df_new['Voltage (V)'] * df_new['Current (A)']
    
    # Scale features
    X_new_scaled = scaler.transform(df_new)
    
    # Predict
    pred_idx = model.predict(X_new_scaled)[0]
    probabilities = model.predict_proba(X_new_scaled)[0]
    
    pred_class = le.inverse_transform([pred_idx])[0]
    
    print("Input Sensor Data:")
    print(df_new.iloc[0, :7])
    print(f"\nPredicted Health Status: **{pred_class}**")
    print("Class Probabilities:")
    for cls, prob in zip(le.classes_, probabilities):
        print(f"  {cls}: {prob:.4f}")


def main():
    # 1. Generate Data
    df = generate_synthetic_data(10000)
    
    # 2. Preprocess & Feature Engineer
    X, y, le, scaler = preprocess_and_feature_engineering(df)
    
    # 3. Train-Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 4. Train and Evaluate
    results_df, trained_models = train_and_evaluate_models(X_train, X_test, y_train, y_test, le)
    
    print("\n--- Final Model Performance Comparison ---")
    print(results_df.to_string(index=False))
    
    # 5. Visualize
    visualize_results(results_df, trained_models, X_test, y_test, le, X.columns)
    
    # 6. Demo Real-time Prediction with the best model (e.g., XGBoost)
    best_model = trained_models['XGBoost']
    real_time_prediction_demo(best_model, scaler, le)

if __name__ == "__main__":
    main()
