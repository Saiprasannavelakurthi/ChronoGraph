// Builds a small "subgraph" for each conversation turn: a timeline node
// (the turn itself) plus a handful of entity nodes pulled from the
// user/assistant text, connected by radial edges. Turn nodes are chained
// together by the caller to form the running timeline spine.

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
  "to", "of", "in", "on", "for", "with", "this", "that", "it", "its",
  "i", "you", "your", "my", "me", "we", "our", "as", "at", "by", "if",
  "so", "do", "does", "did", "not", "have", "has", "had", "can", "could",
  "would", "should", "will", "just", "about", "how", "what", "when",
  "where", "which", "who", "there", "here", "right", "want", "need",
]);

export function extractKeywords(text, max = 3) {
  const words = (text || "")
    .replace(/[^a-zA-Z0-9\s]/g, "")
    .split(/\s+/)
    .filter(Boolean);

  const seen = new Set();
  const keywords = [];

  for (const raw of words) {
    const lower = raw.toLowerCase();
    if (raw.length < 4 || STOPWORDS.has(lower) || seen.has(lower)) continue;
    seen.add(lower);
    keywords.push(raw.length > 14 ? `${raw.slice(0, 14)}…` : raw);
    if (keywords.length >= max) break;
  }

  return keywords;
}

const TURN_SPACING_X = 260;
const ENTITY_SPACING_X = 92;
const TURN_Y = 160;
const ENTITY_Y = 300;

/**
 * @param {number} turnIndex 1-based turn number
 * @param {{ userText: string, botText: string, time: string }} turn
 */
export function buildTurnSubgraph(turnIndex, { userText, botText, time }) {
  const turnId = `turn-${turnIndex}`;
  const keywords = Array.from(
    new Set([...extractKeywords(userText, 2), ...extractKeywords(botText, 3)])
  ).slice(0, 4);

  const turnNode = {
    id: turnId,
    type: "turnNode",
    position: { x: turnIndex * TURN_SPACING_X, y: TURN_Y },
    data: { label: `Turn ${turnIndex}`, time },
  };

  const entityNodes = keywords.map((label, i) => ({
    id: `${turnId}-e${i}`,
    type: "entityNode",
    position: {
      x: turnIndex * TURN_SPACING_X + (i - (keywords.length - 1) / 2) * ENTITY_SPACING_X,
      y: ENTITY_Y + (i % 2 === 0 ? 0 : 46),
    },
    data: { label },
  }));

  const edges = entityNodes.map((n) => ({
    id: `radial-${n.id}`,
    source: turnId,
    sourceHandle: "entity-out",
    target: n.id,
    targetHandle: "entity-in",
    type: "straight",
    style: { stroke: "#CBD0DD", strokeWidth: 1.5, strokeDasharray: "3 3" },
  }));

  return { turnNode, entityNodes, edges };
}

export function buildSpineEdge(prevTurnId, nextTurnId) {
  return {
    id: `spine-${prevTurnId}-${nextTurnId}`,
    source: prevTurnId,
    sourceHandle: "spine-out",
    target: nextTurnId,
    targetHandle: "spine-in",
    type: "smoothstep",
    animated: true,
    style: { stroke: "#7C6FF0", strokeWidth: 2 },
  };
}
