// Topic-aware canned-response engine so the demo can hold a real follow-up
// conversation instead of treating every message as independent. Each
// topic has an `initial` answer and a `followUp` answer; when a message
// doesn't match any topic but reads like a follow-up ("why?", "tell me
// more", "what about that"), the previously active topic answers again
// with the deeper follow-up response instead of falling back to "I don't
// know". Swap `getBotReply` for a real API call (see README.md) — have it
// return the same shape, with your backend owning the actual context
// tracking (e.g. conversation history sent with each request).

export const TOPICS = {
  auth: {
    label: "Auth middleware",
    match: /auth|middleware|session|login|token|permission|access.control/i,
    entities: ["Middleware", "Session", "Tokens"],
    citedSourceIds: ["slack-auth-1", "pr-214"],
    initial:
      "The team moved session validation into shared middleware rather than repeating it per-controller [1]. That change shipped as a refactor extracting the duplicated checks into a single module with test coverage for expired and malformed tokens [2].",
    followUp:
      "To add more detail: the middleware also handles token refresh transparently, so routes don't need to special-case an expired-but-refreshable session [1]. The PR's test suite specifically covers that refresh path alongside the expired and malformed token cases [2].",
  },
  onboarding: {
    label: "Onboarding emails",
    match: /onboard|welcome.email|email.copy|email.template|drip/i,
    entities: ["Onboarding", "Email copy", "Templates"],
    citedSourceIds: ["slack-onboarding-1", "pr-231"],
    initial:
      "Onboarding copy was reworked after feedback that it read too formal — the plan was to warm up the tone and cut the third email entirely [1]. That landed as an update to the first two templates plus removal of the third email from the send sequence [2].",
    followUp:
      "One more detail: the second email's subject line was A/B tested after the tone change, and the warmer version outperformed the original by a wide margin [1]. That result is referenced in the PR description alongside the template diff itself [2].",
  },
  cypress: {
    label: "Flaky Cypress test",
    match: /cypress|flaky|e2e|end.to.end|test.suite|ci.fail/i,
    entities: ["Cypress", "Checkout test", "Clock mock"],
    citedSourceIds: ["slack-cypress-1", "pr-247"],
    initial:
      "The flaky checkout test came down to a timing dependency — it used Date.now() for a countdown, so results depended on when CI happened to start the run [1]. The fix freezes the clock at the start of the spec so the timer assertion is deterministic [2].",
    followUp:
      "Worth noting — the same timing issue could hit other specs using countdowns, so the pattern of freezing the clock with cy.clock() was documented in the testing guide for future use [1]. The fix PR itself only touched the one flaky spec, to keep the change small and easy to review [2].",
  },
  deploy: {
    label: "Deploy pipeline",
    match: /deploy|release|rollout|canary|launch|ship(ping)?/i,
    entities: ["Deploy window", "Canary", "Rollback"],
    citedSourceIds: ["slack-deploy-1", "pr-268"],
    initial:
      "Deploys were causing brief error spikes during peak traffic, so the team proposed gating production releases to a fixed low-traffic window with a required green canary run first [1]. That shipped as a canary stage plus a deploy-window guard in the release pipeline [2].",
    followUp:
      "The canary stage also auto-rolls-back if error rates exceed a threshold within the first 10 minutes, so a bad deploy gets caught before the full rollout window opens [1]. That auto-rollback logic is part of the same pipeline change [2].",
  },
  ratelimit: {
    label: "API rate limiting",
    match: /rate.limit|throttl|api.key|abuse|429|quota/i,
    entities: ["Rate limit", "API keys", "Token bucket"],
    citedSourceIds: ["slack-ratelimit-1", "pr-279"],
    initial:
      "A handful of API keys were hammering the /search endpoint at 200+ req/s, which risked taking down shared infrastructure for everyone else [1]. The fix added a token-bucket limiter per API key — 20 req/s with a burst of 40, returning 429 with Retry-After once exceeded [2].",
    followUp:
      "Keys that exceed the limit get a 429 with a Retry-After header rather than being silently dropped, so well-behaved clients can back off automatically [1]. The limiter's thresholds are also configurable per key tier, which the PR sets up for a future paid-tier increase [2].",
  },
};

const GREETING = /^(hi|hello|hey)\b/i;

// Heuristic for "this message is probably continuing the last topic":
// short follow-up phrasing ("why", "what about", "tell me more") or a
// short message leaning on a pronoun that only makes sense with context
// ("is it tested?", "why did they do that").
const FOLLOW_UP_STARTERS = /^(why|how come|what about|and\b|so\b|then\b|more|elaborate|any more|any other|what else|details?|really\??)/i;
const PRONOUN_REFERENCE = /\b(it|that|this|they|those|them)\b/i;

function looksLikeFollowUp(text) {
  const trimmed = text.trim();
  const wordCount = trimmed.split(/\s+/).filter(Boolean).length;
  if (FOLLOW_UP_STARTERS.test(trimmed)) return true;
  if (wordCount <= 7 && PRONOUN_REFERENCE.test(trimmed)) return true;
  return false;
}

const FALLBACK_SUGGESTIONS = [
  "How does the auth middleware refactor work?",
  "What changed in the onboarding emails?",
  "Why was the Cypress test flaky?",
  "What changed in the deploy pipeline?",
  "How does the new API rate limiting work?",
];

/**
 * @param {string} userText
 * @param {string|null} activeTopicKey the topic the conversation was last on, if any
 */
export function getBotReply(userText, activeTopicKey = null) {
  const matchedKey = Object.keys(TOPICS).find((key) => TOPICS[key].match.test(userText));

  if (matchedKey) {
    const topic = TOPICS[matchedKey];
    return {
      content: topic.initial,
      citedSourceIds: topic.citedSourceIds,
      suggestions: [],
      topicKey: matchedKey,
      topicLabel: topic.label,
      isFollowUp: false,
      entities: topic.entities,
    };
  }

  if (GREETING.test(userText.trim())) {
    return {
      content:
        "Hey! Ask me about the auth refactor, onboarding emails, the flaky Cypress test, deploy pipeline changes, or API rate limiting — I'll cite the Slack thread and PR behind the answer, and remember the topic if you follow up.",
      citedSourceIds: [],
      suggestions: [],
      topicKey: null,
      topicLabel: null,
      isFollowUp: false,
      entities: [],
    };
  }

  if (activeTopicKey && TOPICS[activeTopicKey] && looksLikeFollowUp(userText)) {
    const topic = TOPICS[activeTopicKey];
    return {
      content: topic.followUp,
      citedSourceIds: topic.citedSourceIds,
      suggestions: [],
      topicKey: activeTopicKey,
      topicLabel: topic.label,
      isFollowUp: true,
      entities: topic.entities,
    };
  }

  return {
    content:
      "I don't have a specific Slack thread or PR indexed for that yet in this demo. Tap one of these to see cited sources in action:",
    citedSourceIds: [],
    suggestions: FALLBACK_SUGGESTIONS,
    topicKey: null,
    topicLabel: null,
    isFollowUp: false,
    entities: [],
  };
}

export const SAMPLE_CONVERSATIONS = [
  { id: "c1", title: "Launch checklist review", timestamp: "9:14 AM" },
  { id: "c2", title: "Refactor auth middleware", timestamp: "Yesterday" },
  { id: "c3", title: "Copy for onboarding emails", timestamp: "Tuesday" },
  { id: "c4", title: "Debug flaky Cypress test", timestamp: "Monday" },
];

export const INITIAL_MESSAGES = [
  {
    id: "m1",
    role: "assistant",
    content:
      "Hi, I'm ChronoGraph. Ask about the auth refactor, onboarding emails, the flaky Cypress test, the deploy pipeline, or API rate limiting — each answer cites the exact Slack message or PR it's grounded in. Follow-up questions like \"why?\" or \"tell me more\" stay on topic, and the subgraph timeline on the right keeps track of the thread.",
    time: "9:12 AM",
    citedSourceIds: [],
  },
];
