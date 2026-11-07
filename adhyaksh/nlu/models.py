"""The three intent models: M1 TF-IDF + LogisticRegression, M2 TF-IDF + PyTorch MLP (CPU),
M3 TF-IDF + calibrated linear SVM (replaces the embedding variant, decision D-05)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

KINDS = {"m1_logreg": "TF-IDF + Logistic Regression", "m2_mlp": "TF-IDF + PyTorch MLP",
         "m3_svm": "TF-IDF + calibrated linear SVM"}


class SklearnIntentModel:
    suffix = ".joblib"

    def __init__(self, kind: str, seed: int = 42) -> None:
        self.kind, self.seed, self.pipe = kind, seed, None

    def fit(self, texts, labels, **_):
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.svm import LinearSVC

        from adhyaksh.nlu.features import build_vectorizer

        if self.kind == "m1_logreg":
            clf = LogisticRegression(C=20.0, max_iter=2000, random_state=self.seed)
        elif self.kind == "m3_svm":
            clf = CalibratedClassifierCV(LinearSVC(C=1.0, random_state=self.seed), cv=3, method="sigmoid")
        else:
            raise ValueError(self.kind)
        self.pipe = Pipeline([("vec", build_vectorizer()), ("clf", clf)]).fit(list(texts), list(labels))
        return self

    @property
    def classes_(self):
        return list(self.pipe.classes_)

    def predict_proba(self, texts) -> np.ndarray:
        return self.pipe.predict_proba(list(texts))

    def save(self, directory: Path) -> Path:
        import joblib

        path = Path(directory) / f"{self.kind}{self.suffix}"
        joblib.dump(self.pipe, path)
        return path

    @classmethod
    def load(cls, path: Path, kind: str) -> "SklearnIntentModel":
        import joblib

        m = cls(kind)
        m.pipe = joblib.load(path)
        return m


class TorchMLPModel:
    """UNTESTED ON TARGET in the build sandbox (PyTorch could not be installed there)."""

    suffix = ".pt"
    kind = "m2_mlp"

    def __init__(self, kind: str = "m2_mlp", seed: int = 42) -> None:
        self.seed, self.vec, self.net, self._classes = seed, None, None, []

    def fit(self, texts, labels, val_texts=None, val_labels=None, max_epochs: int = 60, patience: int = 5):
        import torch
        from torch import nn

        from adhyaksh.nlu.features import build_vectorizer

        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
        self.vec = build_vectorizer().fit(list(texts))
        self._classes = sorted(set(labels))
        idx = {c: i for i, c in enumerate(self._classes)}
        X = self.vec.transform(list(texts)).tocsr()
        y = np.array([idx[c] for c in labels])
        Xv = yv = None
        if val_texts is not None:
            Xv = torch.tensor(self.vec.transform(list(val_texts)).toarray(), dtype=torch.float32)
            yv = torch.tensor([idx[c] for c in val_labels])
        self.net = nn.Sequential(nn.Linear(X.shape[1], 256), nn.ReLU(), nn.Dropout(0.3),
                                 nn.Linear(256, len(self._classes)))
        opt = torch.optim.AdamW(self.net.parameters(), lr=1e-3, weight_decay=1e-4)
        loss_fn = nn.CrossEntropyLoss()
        rng = np.random.default_rng(self.seed)
        best, best_state, bad = float("inf"), None, 0
        for _ in range(max_epochs):
            self.net.train()
            order = rng.permutation(X.shape[0])
            for s in range(0, len(order), 64):
                b = order[s:s + 64]
                xb = torch.tensor(X[b].toarray(), dtype=torch.float32)
                opt.zero_grad()
                loss_fn(self.net(xb), torch.tensor(y[b])).backward()
                opt.step()
            if Xv is None:
                continue
            self.net.eval()
            with torch.no_grad():
                vloss = float(loss_fn(self.net(Xv), yv))
            if vloss < best - 1e-4:
                best, bad = vloss, 0
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
            else:
                bad += 1
                if bad >= patience:
                    break
        if best_state is not None:
            self.net.load_state_dict(best_state)
        self.net.eval()
        return self

    @property
    def classes_(self):
        return list(self._classes)

    def predict_proba(self, texts) -> np.ndarray:
        import torch

        x = torch.tensor(self.vec.transform(list(texts)).toarray(), dtype=torch.float32)
        self.net.eval()
        with torch.no_grad():
            return torch.softmax(self.net(x), dim=1).numpy()

    def save(self, directory: Path) -> Path:
        import torch

        path = Path(directory) / f"{self.kind}{self.suffix}"
        torch.save({"vec": self.vec, "classes": self._classes, "state": self.net.state_dict(),
                    "n_in": next(self.net.parameters()).shape[1]}, path)
        return path

    @classmethod
    def load(cls, path: Path, kind: str = "m2_mlp") -> "TorchMLPModel":
        import torch
        from torch import nn

        blob = torch.load(path, weights_only=False)  # local file written by save()
        m = cls()
        m.vec, m._classes = blob["vec"], blob["classes"]
        m.net = nn.Sequential(nn.Linear(blob["n_in"], 256), nn.ReLU(), nn.Dropout(0.3),
                              nn.Linear(256, len(m._classes)))
        m.net.load_state_dict(blob["state"])
        m.net.eval()
        return m


def make(kind: str, seed: int = 42):
    return TorchMLPModel(kind, seed) if kind == "m2_mlp" else SklearnIntentModel(kind, seed)


def load(kind: str, path: Path):
    return TorchMLPModel.load(path, kind) if kind == "m2_mlp" else SklearnIntentModel.load(path, kind)
