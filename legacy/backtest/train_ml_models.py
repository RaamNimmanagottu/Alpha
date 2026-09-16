"""Train several classification models to predict next-candle direction (UP/DOWN),
compare their accuracy, inspect which input features actually correlate with
direction, and generate an ML-based BUY/SELL signal from the best model.

Framing: "UP" means next_close > close (bullish -> this project's BUY/CE signal),
"DOWN" otherwise (bearish -> SELL/PE). Mirrors the vocabulary alpha/local_signals.py
uses, but here the direction call comes from a trained model instead of the
RSI/Stochastic/CCI/ADX/AO/Momentum vote.

Methodology: the train/test split is CHRONOLOGICAL (earliest ~80% train, most recent
~20% test), never randomly shuffled. Adjacent 5-minute candles have highly
correlated indicator values, so a random split would leak near-duplicate rows across
train/test and inflate accuracy in a way that would not hold up on genuinely unseen
future data.

Requires scikit-learn (backtest-only dependency, see backtest/requirements.txt):
    .venv\\Scripts\\pip.exe install -r backtest\\requirements.txt

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\train_ml_models.py

Reads backtest/data/NIFTY_five_minute_1000days_features.xlsx and writes:
    backtest/data/model_comparison.csv
    backtest/data/feature_correlation.csv
    backtest/data/best_model.joblib
    backtest/data/NIFTY_five_minute_1000days_ml_signals.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

DATA_DIR = Path(__file__).resolve().parent / "data"
SOURCE_FILE = DATA_DIR / "NIFTY_five_minute_1000days_features.xlsx"
COMPARISON_FILE = DATA_DIR / "model_comparison.csv"
CORRELATION_FILE = DATA_DIR / "feature_correlation.csv"
MODEL_FILE = DATA_DIR / "best_model.joblib"
SIGNAL_FILE = DATA_DIR / "NIFTY_five_minute_1000days_ml_signals.xlsx"

TARGET_COLS = ["next_open", "next_close"]
NON_FEATURE_COLS = ["date", *TARGET_COLS, "direction"]
TEST_FRACTION = 0.2


def load_dataset() -> pd.DataFrame:
    df = pd.read_excel(SOURCE_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Drop rows where indicators haven't warmed up yet, or where there's no future
    # candle yet to know the direction from (the most recent row).
    df = df.dropna().reset_index(drop=True)

    # Exact ties (next_close == close) aren't directional -- drop rather than
    # arbitrarily assigning them to UP or DOWN.
    df = df[df["next_close"] != df["close"]].reset_index(drop=True)
    df["direction"] = (df["next_close"] > df["close"]).astype(int)
    return df


def chronological_split(df: pd.DataFrame, test_fraction: float = TEST_FRACTION):
    split_idx = int(len(df) * (1 - test_fraction))
    return df.iloc[:split_idx], df.iloc[split_idx:]


def build_models() -> dict[str, Pipeline]:
    return {
        "Logistic Regression": Pipeline(
            [("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))]
        ),
        "K-Nearest Neighbors": Pipeline(
            [("scale", StandardScaler()), ("clf", KNeighborsClassifier())]
        ),
        # Kernel SVC scales roughly O(n^2)-O(n^3); with ~40k training rows that's
        # impractically slow. LinearSVC uses a much faster solver -- still an SVM,
        # just the linear-kernel variant.
        "Linear SVM": Pipeline(
            [("scale", StandardScaler()), ("clf", LinearSVC(max_iter=5000))]
        ),
        "Decision Tree": Pipeline(
            [("clf", DecisionTreeClassifier(max_depth=8, random_state=42))]
        ),
        "Random Forest": Pipeline(
            [("clf", RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1))]
        ),
        "Gradient Boosting": Pipeline(
            [("clf", GradientBoostingClassifier(random_state=42))]
        ),
    }


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No feature data found at {SOURCE_FILE}")
        print("Run backtest/build_ml_dataset.py first.")
        return 1

    df = load_dataset()
    feature_cols = [c for c in df.columns if c not in NON_FEATURE_COLS]
    print(f"{len(df)} usable rows after dropping warm-up/undefined rows and ties")
    print(f"{len(feature_cols)} input features: {feature_cols}\n")

    train_df, test_df = chronological_split(df)
    print(f"Train: {len(train_df)} rows ({train_df['date'].min()} -> {train_df['date'].max()})")
    print(f"Test:  {len(test_df)} rows ({test_df['date'].min()} -> {test_df['date'].max()})\n")

    X_train, y_train = train_df[feature_cols], train_df["direction"]
    X_test, y_test = test_df[feature_cols], test_df["direction"]

    baseline_accuracy = max(y_test.mean(), 1 - y_test.mean())
    print(f"Baseline (always predict the majority class): {baseline_accuracy:.4f}\n")

    results = []
    fitted_models = {}
    for name, model in build_models().items():
        print(f"Training {name}...")
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        results.append({"model": name, "accuracy": acc})
        fitted_models[name] = model
        print(f"  {name:22s} accuracy = {acc:.4f}")

    results_df = pd.DataFrame(results).sort_values("accuracy", ascending=False).reset_index(drop=True)
    results_df.to_csv(COMPARISON_FILE, index=False)
    print(f"\nModel comparison:\n{results_df.to_string(index=False)}")
    print(f"Written to {COMPARISON_FILE}")

    best_name = results_df.iloc[0]["model"]
    best_model = fitted_models[best_name]
    print(f"\nBest model: {best_name} (accuracy={results_df.iloc[0]['accuracy']:.4f}, "
          f"baseline={baseline_accuracy:.4f})")
    print(classification_report(y_test, best_model.predict(X_test), target_names=["DOWN", "UP"]))

    joblib.dump(best_model, MODEL_FILE)
    print(f"Best model saved to {MODEL_FILE}")

    # Correlation of each input feature with the direction label, over the full
    # cleaned dataset (not just the test split).
    correlations = df[feature_cols].apply(lambda col: col.corr(df["direction"]))
    correlations = correlations.reindex(correlations.abs().sort_values(ascending=False).index)
    correlations.to_frame("correlation_with_direction").to_csv(CORRELATION_FILE)
    print(f"\nTop 10 features by |correlation| with direction:\n{correlations.head(10).to_string()}")
    print(f"Full table written to {CORRELATION_FILE}")

    clf = best_model.named_steps["clf"]
    if hasattr(clf, "feature_importances_"):
        importances = pd.Series(clf.feature_importances_, index=feature_cols).sort_values(ascending=False)
        print(f"\nTop 10 features by importance in {best_name}:\n{importances.head(10).to_string()}")

    # Apply the best model to every usable row and translate its predicted direction
    # into this project's BUY(CE)/SELL(PE) vocabulary.
    df["ml_predicted_direction"] = best_model.predict(df[feature_cols])
    df["ml_signal"] = df["ml_predicted_direction"].map({1: "BUY", 0: "SELL"})
    df["dataset_split"] = ["train"] * len(train_df) + ["test"] * len(test_df)

    df.sort_values("date", ascending=False).to_excel(SIGNAL_FILE, index=False)
    print(f"\nFull dataset with ml_signal written to {SIGNAL_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
