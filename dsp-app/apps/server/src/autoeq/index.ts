import type { HeadphoneSearchResult } from '@aural/shared';

const GITHUB_API = 'https://api.github.com';
const REPO = 'jaakkopasanen/AutoEq';
const MEASUREMENTS_PATH = 'measurements';

const INDEX_CACHE_PATH = '/home/kvn/workspace/.files/config/autoeq/measurement-index.json';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

interface CachedIndex {
  timestamp: number;
  entries: HeadphoneSearchResult[];
}

/**
 * Fetch the measurement index from GitHub's tree API.
 * Structure: measurements/{source}/{rig}/{model}/
 * We walk 3 levels: source → rig → model
 */
export async function fetchMeasurementIndex(): Promise<HeadphoneSearchResult[]> {
  // Check disk cache
  const cached = await readCache();
  if (cached) return cached;

  const entries: HeadphoneSearchResult[] = [];

  // Use recursive tree API to get all paths in one call
  const treeUrl = `${GITHUB_API}/repos/${REPO}/git/trees/master:${MEASUREMENTS_PATH}?recursive=1`;
  const res = await fetch(treeUrl, {
    headers: {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'Aural-DSP/1.0',
    },
  });

  if (!res.ok) {
    throw new Error(`GitHub API error: ${res.status} ${res.statusText}`);
  }

  const data = await res.json() as { tree: Array<{ path: string; type: string }> };

  // Parse paths like "source/rig/model" — we want directories at depth 3
  // that contain measurement data (indicated by having files inside)
  const modelDirs = new Set<string>();
  for (const item of data.tree) {
    const parts = item.path.split('/');
    if (parts.length >= 3) {
      const dirKey = `${parts[0]}/${parts[1]}/${parts[2]}`;
      modelDirs.add(dirKey);
    }
  }

  for (const dirKey of modelDirs) {
    const [source, rig, ...modelParts] = dirKey.split('/');
    const model = modelParts.join('/');
    if (source && rig && model) {
      entries.push({ source, rig, model });
    }
  }

  // Cache to disk
  await writeCache(entries);

  return entries;
}

/** Fuzzy search the cached measurement index */
export async function searchHeadphones(query: string): Promise<HeadphoneSearchResult[]> {
  const index = await fetchMeasurementIndex();
  const q = query.toLowerCase().trim();

  if (!q) return [];

  // Split query into tokens for multi-word matching
  const tokens = q.split(/\s+/);

  // Score each entry
  const scored = index
    .map((entry) => {
      const modelLower = entry.model.toLowerCase();
      let score = 0;

      // Exact model match
      if (modelLower === q) score += 100;
      // Model starts with query
      else if (modelLower.startsWith(q)) score += 50;
      // Model contains query as substring
      else if (modelLower.includes(q)) score += 30;

      // All tokens present in model
      const allTokensMatch = tokens.every((t) => modelLower.includes(t));
      if (allTokensMatch) score += 20;

      // Individual token matches
      for (const token of tokens) {
        if (modelLower.includes(token)) score += 5;
      }

      return { entry, score };
    })
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);

  return scored.map((s) => s.entry);
}

async function readCache(): Promise<HeadphoneSearchResult[] | null> {
  try {
    const file = Bun.file(INDEX_CACHE_PATH);
    if (await file.exists()) {
      const cached: CachedIndex = await file.json();
      if (Date.now() - cached.timestamp < CACHE_TTL_MS) {
        return cached.entries;
      }
    }
  } catch {
    // Cache miss
  }
  return null;
}

async function writeCache(entries: HeadphoneSearchResult[]): Promise<void> {
  const cached: CachedIndex = { timestamp: Date.now(), entries };
  await Bun.write(INDEX_CACHE_PATH, JSON.stringify(cached));
}
