"""The two deep-learning families: an LSTM sequence model and a GraphSAGE GNN.

Kept out of models.py because these two need a different *shape* of input from
the other four. Gradient boosting and friends see one feature vector per account;
these two see structure the flat vector throws away:

  LSTM        an account's transactions IN ORDER. A flat mean-and-standard-
              deviation cannot tell "salary in, rent out, groceries all month"
              from "big credit in, everything out within hours" — the numbers can
              be identical, the sequences are not.
  GraphSAGE   an account plus the accounts it transacts WITH. Its premise is that
              you are judged by the company you keep, which is precisely the mule
              network argument: the accounts around you are more incriminating
              than anything in your own history.

Both are implemented directly in PyTorch rather than pulling in torch-geometric.
GraphSAGE's core is one idea — aggregate your neighbours' features, concatenate
with your own, transform — and writing those ~15 lines is more transparent, more
robust on this Python version, and avoids a large fragile dependency for one
layer. CPU-only torch is used throughout: these models are tiny and a GPU build
would be a ~2.5GB download for no gain.

BOUNDARY: labels are used only for fitting on the training split, exactly as in
models.py. Nothing here reads `scheme_labels` directly.
"""

from __future__ import annotations

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn

from launderlab.ml.models import RANDOM_STATE, Model

# Transactions per account fed to the LSTM. Long enough to contain a laundering
# episode, short enough that padding does not dominate the batch.
SEQUENCE_LENGTH = 32
SEQUENCE_FEATURES = 5  # amount, direction, gap-hours, balance, channel-is-cash


def _seed() -> None:
    torch.manual_seed(RANDOM_STATE)


class SequenceLSTM(Model):
    """Reads each account's transaction history as an ordered story."""

    def __init__(self, hidden: int = 32, epochs: int = 12, lr: float = 1e-2):
        super().__init__(name="lstm", paradigm="supervised", needs_labels=True)
        self.hidden, self.epochs, self.lr = hidden, epochs, lr
        self._net: nn.Module | None = None
        self._scaler = StandardScaler()

    def _build(self) -> nn.Module:
        _seed()
        hidden = self.hidden

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(SEQUENCE_FEATURES, hidden, batch_first=True)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :]).squeeze(-1)

        return Net()

    def fit(self, X, y):
        # X here is the 3-D sequence tensor, not the flat feature matrix
        flat = X.reshape(-1, SEQUENCE_FEATURES)
        self._scaler.fit(flat)
        scaled = self._scaler.transform(flat).reshape(X.shape)

        self._net = self._build()
        optimiser = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        # laundering is rare; without this the net learns to answer "no" always
        positive_weight = torch.tensor(
            max((len(y) - y.sum()) / max(y.sum(), 1), 1.0), dtype=torch.float32)
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=positive_weight)

        xb = torch.tensor(scaled, dtype=torch.float32)
        yb = torch.tensor(y, dtype=torch.float32)
        self._net.train()
        for _ in range(self.epochs):
            optimiser.zero_grad()
            loss = loss_fn(self._net(xb), yb)
            loss.backward()
            optimiser.step()
        return self

    def score(self, X):
        scaled = self._scaler.transform(
            X.reshape(-1, SEQUENCE_FEATURES)).reshape(X.shape)
        self._net.eval()
        with torch.no_grad():
            return torch.sigmoid(
                self._net(torch.tensor(scaled, dtype=torch.float32))).numpy()


class GraphSAGE(Model):
    """Judges an account by its own features plus its neighbours' features."""

    def __init__(self, hidden: int = 24, epochs: int = 60, lr: float = 1e-2):
        super().__init__(name="graphsage", paradigm="supervised", needs_labels=True)
        self.hidden, self.epochs, self.lr = hidden, epochs, lr
        self._net: nn.Module | None = None
        self._scaler = StandardScaler()
        self._adjacency: np.ndarray | None = None

    def set_adjacency(self, adjacency: np.ndarray) -> None:
        """Row-normalised neighbour matrix, supplied by the tournament runner."""
        self._adjacency = adjacency

    def _build(self, n_features: int) -> nn.Module:
        _seed()
        hidden = self.hidden

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                # the SAGE layer: [self features | aggregated neighbour features]
                self.sage = nn.Linear(n_features * 2, hidden)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x, adj):
                neighbours = adj @ x           # mean of each node's neighbours
                combined = torch.cat([x, neighbours], dim=1)
                return self.head(torch.relu(self.sage(combined))).squeeze(-1)

        return Net()

    def fit(self, X, y):
        scaled = self._scaler.fit_transform(X)
        self._net = self._build(scaled.shape[1])
        optimiser = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        positive_weight = torch.tensor(
            max((len(y) - y.sum()) / max(y.sum(), 1), 1.0), dtype=torch.float32)
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=positive_weight)

        xb = torch.tensor(scaled, dtype=torch.float32)
        adj = torch.tensor(self._adjacency, dtype=torch.float32)
        yb = torch.tensor(y, dtype=torch.float32)
        self._net.train()
        for _ in range(self.epochs):
            optimiser.zero_grad()
            loss = loss_fn(self._net(xb, adj), yb)
            loss.backward()
            optimiser.step()
        return self

    def score(self, X):
        scaled = self._scaler.transform(X)
        self._net.eval()
        with torch.no_grad():
            logits = self._net(torch.tensor(scaled, dtype=torch.float32),
                                torch.tensor(self._adjacency, dtype=torch.float32))
            return torch.sigmoid(logits).numpy()
