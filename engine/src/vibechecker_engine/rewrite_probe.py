"""Source-origin prediction from the frozen Deep encoder representation."""

from dataclasses import dataclass

import numpy as np


@dataclass
class RewriteOriginProbe:
    general: object
    origin_projection: object
    origin_contrast: object
    origin_calibration: object
    transformation: object
    transformation_calibration: object
    downward_only: bool

    n_features_in_ = 769
    classes_ = np.array([0, 1])

    def predict_proba(self, vectors):
        x = np.asarray(vectors)
        if x.ndim != 2 or x.shape[1] != self.n_features_in_ or not np.isfinite(x).all():
            raise ValueError("Expected finite 769-feature Deep encoder vectors")
        general = self.general.predict_proba(x)[:, 1]
        contrast = self.origin_contrast.decision_function(self.origin_projection.transform(x))
        origin = self.origin_calibration.predict_proba(contrast[:, None])[:, 1]
        evidence = self.transformation.decision_function(x)
        rewrite = self.transformation_calibration.predict_proba(evidence[:, None])[:, 1]
        # The conservative candidate can protect a human readout even when
        # the transformation classifier fires on ordinary prose.
        if self.downward_only:
            origin = np.minimum(origin, general)
        result = general + rewrite * (origin - general)
        return np.column_stack((1 - result, result))
