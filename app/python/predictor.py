"""Small tabular classifier: TabPFN when it is installed on the board, else logistic regression in numpy.

Used for two jobs: "will the user finish a step of this size today?" and "is this minute rain?".
"""
import numpy as np

try:
    from tabpfn import TabPFNClassifier
    BACKEND = "tabpfn"
except Exception:  # not installed: fall back, and say so on the page
    TabPFNClassifier = None
    BACKEND = "logistic"


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


def fit(X, y):
    """Returns a fitted model, or None if there is only one class so far."""
    if len(set(y)) < 2:
        return None
    if TabPFNClassifier is not None:
        m = TabPFNClassifier(device="cpu")
        m.fit(np.asarray(X, float), np.asarray(y, int))
        return m
    return _Logistic().fit(X, y)


def p_true(model, X):
    return [float(p) for p in model.predict_proba(np.asarray(X, float))[:, 1]]
