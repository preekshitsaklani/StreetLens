"""Who really trades together? Hierarchical clustering of 30 US financials on two years of weekly return correlations."""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.manifold import MDS


def run(px: pd.DataFrame, focus: list[str], k: int = 5, weeks: int = 104) -> dict:
    r = np.log(px).diff().dropna(how="all").tail(weeks).dropna(axis=1, thresh=int(weeks * 0.9)).dropna()
    corr = r.corr()
    dist = np.sqrt(0.5 * (1 - corr.clip(-1, 1)))                     # correlation distance, a proper metric
    Z = linkage(squareform(dist.to_numpy(), checks=False), method="average")
    clusters = fcluster(Z, k, criterion="maxclust")
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=0, n_init=4).fit_transform(dist.to_numpy())
    table = pd.DataFrame({"ticker": corr.index, "cluster": clusters, "x": xy[:, 0], "y": xy[:, 1],
                          "is_focus": [t in focus for t in corr.index]})
    nearest = {t: corr[t].drop(t).nlargest(3).round(2).to_dict() for t in focus if t in corr}
    return {"map": table, "nearest": nearest, "n_stocks": len(corr), "n_weeks": len(r)}
