import { covariance } from "./analytics.mjs?v=0.5.0";
export function ewmaCovariance(columns, lambda = 0.94) {
  if (!columns.length || columns[0].length < 20 || !(lambda > 0 && lambda < 1))
    throw new Error("Historia insuficiente para EWMA.");
  const n = columns.length,
    initial = Math.min(60, columns[0].length);
  let c = columns.map((a) =>
    columns.map(
      (b) => covariance(a.slice(0, initial), b.slice(0, initial)) || 0,
    ),
  );
  for (let t = initial; t < columns[0].length; t++) {
    c = c.map((row, i) =>
      row.map(
        (v, j) => lambda * v + (1 - lambda) * columns[i][t] * columns[j][t],
      ),
    );
  }
  // Shrink off-diagonal covariances by 5%, preserving variances and PSD.
  return c.map((row, i) => row.map((v, j) => v * 252 * (i === j ? 1 : 0.95)));
}
export function cholesky(matrix) {
  const n = matrix.length,
    l = Array.from({ length: n }, () => Array(n).fill(0));
  for (let i = 0; i < n; i++)
    for (let j = 0; j <= i; j++) {
      let value = matrix[i][j];
      for (let k = 0; k < j; k++) value -= l[i][k] * l[j][k];
      if (i === j) {
        if (value < -1e-9)
          throw new Error("La matriz no es semidefinida positiva.");
        l[i][j] = Math.sqrt(Math.max(0, value));
      } else l[i][j] = l[j][j] > 1e-12 ? value / l[j][j] : 0;
    }
  return l;
}
