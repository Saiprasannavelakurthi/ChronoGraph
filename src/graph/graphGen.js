// Builds a small "subgraph" for each conversation turn: a timeline node
// (the turn itself) plus a handful of entity nodes, connected by radial
// edges. Turn nodes are chained together to form the running timeline
// spine (buildSpineEdge). To keep the graph honest about conversational
// context, entity nodes are *reused* across turns on the same topic
// (via `registry`) instead of duplicated — so a follow-up question draws
// new edges back to the same "Middleware" or "Cypress" node instead of
// spawning a lookalike copy. If a topic is picked back up after the
// conversation moved elsewhere, a faint "thread" edge links back to that
// topic's first turn so the resumed context is visible at a glance.

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

const slugify = (label) => label.toLowerCase().replace(/[^a-z0-9]+/g, "-");

/** Creates a fresh, empty registry — one per conversation. Reset this
 * (e.g. via a new `useRef`) whenever the chat itself resets. */
export function createGraphRegistry() {
  return {
    entityIndex: new Map(), // "topicKey:label" -> nodeId
    topicAnchor: new Map(), // topicKey -> the turnId that first introduced it
    lastTopicKey: null,
  };
}

/**
 * @param {number} turnIndex 1-based turn number
 * @param {{ time: string, topicKey: string|null, entities: string[], isFollowUp: boolean, userText: string, botText: string }} turn
 * @param {ReturnType<typeof createGraphRegistry>} registry
 */
export function buildTurnSubgraph(turnIndex, turn, registry) {
  const { time, topicKey, entities, isFollowUp, userText, botText } = turn;
  const turnId = `turn-${turnIndex}`;

  const turnNode = {
    id: turnId,
    type: "turnNode",
    position: { x: turnIndex * TURN_SPACING_X, y: TURN_Y },
    data: { label: isFollowUp ? `Turn ${turnIndex} · follow-up` : `Turn ${turnIndex}`, time },
  };

  // Topic turns use the topic's canonical entity labels (so they can be
  // recognized and reused across turns); untracked turns (greetings,
  // fallbacks) fall back to free-text keyword extraction and don't
  // participate in cross-turn reuse.
  const labels = topicKey && entities?.length
    ? entities
    : extractKeywords(`${userText ?? ""} ${botText ?? ""}`, 0);

  const newEntityNodes = [];
  const edges = [];

  labels.forEach((label, i) => {
    const regKey = `${topicKey ?? "general"}:${label.toLowerCase()}`;
    let nodeId = registry.entityIndex.get(regKey);
    const isRecalled = Boolean(nodeId);

    if (!nodeId) {
      nodeId = `entity-${slugify(topicKey ?? "general")}-${slugify(label)}`;
      registry.entityIndex.set(regKey, nodeId);
      newEntityNodes.push({
        id: nodeId,
        type: "entityNode",
        position: {
          x: turnIndex * TURN_SPACING_X + (i - (labels.length - 1) / 2) * ENTITY_SPACING_X,
          y: ENTITY_Y + (i % 2 === 0 ? 0 : 46),
        },
        data: { label },
      });
    }

    edges.push({
      id: `radial-${turnId}-${nodeId}`,
      source: turnId,
      sourceHandle: "entity-out",
      target: nodeId,
      targetHandle: "entity-in",
      type: "straight",
      style: isRecalled
        ? { stroke: "#22D3B8", strokeWidth: 1.75 }
        : { stroke: "#CBD0DD", strokeWidth: 1.5, strokeDasharray: "3 3" },
    });
  });

  // Faint "thread" edge back to a topic's first turn, only when the
  // conversation drifted away and came back (adjacent same-topic turns
  // already look connected via the spine, so this would be redundant).
  let contextEdge = null;
  if (topicKey) {
    if (registry.topicAnchor.has(topicKey)) {
      const anchorId = registry.topicAnchor.get(topicKey);
      if (registry.lastTopicKey !== topicKey && anchorId !== turnId) {
        contextEdge = {
          id: `thread-${anchorId}-${turnId}`,
          source: anchorId,
          sourceHandle: "spine-out",
          target: turnId,
          targetHandle: "spine-in",
          type: "default",
          style: { stroke: "#7C6FF0", strokeWidth: 1.5, strokeDasharray: "2 5", opacity: 0.55 },
        };
      }
    } else {
      registry.topicAnchor.set(topicKey, turnId);
    }
    registry.lastTopicKey = topicKey;
  } else {
    registry.lastTopicKey = null;
  }

  if (contextEdge) edges.push(contextEdge);

  return { turnNode, newEntityNodes, edges };
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
