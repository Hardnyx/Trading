export function seededRandom(seed = 20261024) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** Independent streams: another asset or component cannot consume these draws. */
export function namedRandom(seed, name) {
  let hash = (2166136261 ^ (seed >>> 0)) >>> 0;
  for (let i = 0; i < name.length; i++) {
    hash = Math.imul(hash ^ name.charCodeAt(i), 16777619) >>> 0;
  }
  hash = Math.imul(hash ^ (hash >>> 16), 0x85ebca6b);
  hash = Math.imul(hash ^ (hash >>> 13), 0xc2b2ae35);
  return seededRandom((hash ^ (hash >>> 16)) >>> 0);
}
export function normalGenerator(random) {
  let spare = null;
  return () => {
    if (spare !== null) {
      const value = spare;
      spare = null;
      return value;
    }
    const r = Math.sqrt(-2 * Math.log(Math.max(1e-15, random()))),
      theta = 2 * Math.PI * random();
    spare = r * Math.sin(theta);
    return r * Math.cos(theta);
  };
}
export function poisson(random, lambda) {
  const limit = Math.exp(-lambda);
  let value = 1,
    count = 0;
  do {
    count++;
    value *= random();
  } while (value > limit);
  return count - 1;
}
export function normalCDF(x) {
  const a = Math.abs(x),
    t = 1 / (1 + 0.2316419 * a);
  const tail =
    (Math.exp((-a * a) / 2) / Math.sqrt(2 * Math.PI)) *
    t *
    (0.31938153 +
      t *
        (-0.356563782 +
          t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return Math.max(1e-12, Math.min(1 - 1e-12, x >= 0 ? 1 - tail : tail));
}
