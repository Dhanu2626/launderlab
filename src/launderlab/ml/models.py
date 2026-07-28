"""The model zoo: different learning paradigms behind one interface.

Every model answers the same question — "how suspicious is this account?" — and
returns a score where higher means more suspicious. That uniformity is what makes
the leaderboard a fair comparison rather than four incomparable numbers.

The families differ in what they need to learn from, which is the point of running
them against each other:

  GradientBoosting  SUPERVISED. Needs labelled history. The industry workhorse and
                    the bench everything else is measured against.
  IsolationForest   UNSUPERVISED. Isolates points with random splits; outliers fall
                    out in fewer splits. Needs no labels at all.
  OneClassSVM       UNSUPERVISED. Learns a boundary around "normal" and flags what
                    sits outside it.
  Autoencoder       UNSUPERVISED. Learns to compress and rebuild normal accounts;
                    scores by how badly an account reconstructs. Built on sklearn's
                    MLPRegressor rather than a deep-learning framework — a
                    bottleneck network trained to reproduce its own input IS an
                    autoencoder, and it does not justify a 3GB dependency.

All four are wrapped so that `fit(X, y)` has a consistent signature, but the
unsupervised three ignore `y` completely — they are fitted on the raw training
features, laundering included. That is deliberate and more honest than handing
them a pre-cleaned negatives-only set: a real bank does not know which of its
accounts are dirty, which is the whole reason unsupervised detection is
attractive. They rely instead on laundering being *rare* (a few percent here),
so it sits in the tail of whatever "normal" they learn.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

RANDOM_STATE = 0


@dataclass
class Model:
    name: str
    paradigm: str  # 'supervised' | 'unsupervised'
    needs_labels: bool

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Model":  # pragma: no cover
        raise NotImplementedError

    def score(self, X: np.ndarray) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class _Scaled(Model):
    """Base for models that need standardised inputs.

    Scaling is fitted on training data only and reused at scoring time — fitting a
    scaler on the test set is a subtle form of leakage that quietly flatters
    results.
    """

    def __init__(self, name: str, paradigm: str, needs_labels: bool):
        super().__init__(name=name, paradigm=paradigm, needs_labels=needs_labels)
        self._scaler = StandardScaler()

    def _fit_scale(self, X: np.ndarray) -> np.ndarray:
        return self._scaler.fit_transform(X)

    def _scale(self, X: np.ndarray) -> np.ndarray:
        return self._scaler.transform(X)


class GradientBoosting(_Scaled):
    def __init__(self):
        super().__init__("gradient_boosting", "supervised", needs_labels=True)
        self._model = GradientBoostingClassifier(random_state=RANDOM_STATE)

    def fit(self, X, y):
        self._model.fit(self._fit_scale(X), y)
        return self

    def score(self, X):
        return self._model.predict_proba(self._scale(X))[:, 1]


class Isolation(_Scaled):
    def __init__(self, contamination: float = 0.05):
        super().__init__("isolation_forest", "unsupervised", needs_labels=False)
        self._model = IsolationForest(contamination=contamination,
                                      random_state=RANDOM_STATE, n_estimators=200)

    def fit(self, X, y=None):
        self._model.fit(self._fit_scale(X))
        return self

    def score(self, X):
        # decision_function: higher = more normal, so negate for "suspicious"
        return -self._model.decision_function(self._scale(X))


class OneClass(_Scaled):
    def __init__(self, nu: float = 0.05):
        super().__init__("one_class_svm", "unsupervised", needs_labels=False)
        self._model = OneClassSVM(nu=nu, kernel="rbf", gamma="scale")

    def fit(self, X, y=None):
        self._model.fit(self._fit_scale(X))
        return self

    def score(self, X):
        return -self._model.decision_function(self._scale(X))


class Autoencoder(_Scaled):
    """Bottleneck MLP trained to reconstruct its own input.

    Score is reconstruction error: an account whose behaviour the network never
    learned to compress is, by construction, unlike the accounts it trained on.
    """

    def __init__(self, bottleneck: int = 6, max_iter: int = 400):
        super().__init__("autoencoder", "unsupervised", needs_labels=False)
        self._model = MLPRegressor(
            hidden_layer_sizes=(24, bottleneck, 24),
            activation="relu", solver="adam", max_iter=max_iter,
            random_state=RANDOM_STATE, early_stopping=False,
        )

    def fit(self, X, y=None):
        scaled = self._fit_scale(X)
        self._model.fit(scaled, scaled)  # target IS the input
        return self

    def score(self, X):
        scaled = self._scale(X)
        rebuilt = self._model.predict(scaled)
        return np.mean((scaled - rebuilt) ** 2, axis=1)


def default_zoo() -> list[Model]:
    """The four families slice 6.1 covers. LSTM and GraphSAGE join in 6.2."""
    return [GradientBoosting(), Isolation(), OneClass(), Autoencoder()]
