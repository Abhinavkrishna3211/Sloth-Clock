"""Small tabular classifier: TabPFN when it is installed on the board, else logistic regression in numpy.

Used for two jobs: "will the user finish a step of this size today?" (TabPFN) and "is this minute rain?"
(always logistic: it sits in the alarm decision, and TabPFN takes ~30 s on the board).
"""
import importlib.util
import os

import numpy as np

# Weights live in the app's cache folder (kept across container rebuilds); nothing is sent anywhere.
os.environ.setdefault("TABPFN_MODEL_CACHE_DIR", "/app/.cache/tabpfn")
os.environ.setdefault("TABPFN_DISABLE_TELEMETRY", "1")
BACKEND = "tabpfn" if importlib.util.find_spec("tabpfn") else "logistic"  # imported on first use (~30 s)


class _Logistic:
    def fit(self, X, y, steps=2000, lr=0.1, l2=1e-3):
        X = np.asarray(X, float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]
        self.w = np.zeros(Z.shape[1])
        y = np.asarray(y, float)
        for _ in range(steps):
            p = 1 / (1 + np.exp(-Z @ self.w))
            self.w -= lr * (Z.T @ (p - y) / len(y) + l2 * self.w)
        return self

    def predict_proba(self, X):
        Z = np.c_[np.ones(len(X)), (np.asarray(X, float) - self.mu) / self.sd]
        p = 1 / (1 + np.exp(-Z @ self.w))
        return np.c_[1 - p, p]


def fit(X, y, quick=False):
    """Returns a fitted model, or None if there is only one class so far. quick=True: always logistic."""
    if len(set(y)) < 2:
        return None
    if BACKEND == "tabpfn" and not quick:
        from tabpfn import TabPFNClassifier
        m = TabPFNClassifier(device="cpu")
        m.fit(np.asarray(X, float), np.asarray(y, int))
        return m
    return _Logistic().fit(X, y)


def p_true(model, X):
    return [float(p) for p in model.predict_proba(np.asarray(X, float))[:, 1]]
