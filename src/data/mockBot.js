// Lightweight canned-response engine so the UI feels alive without a backend.
// Swap `getBotReply` for a real API call (see README.md) when you wire this
// up to an actual model.

const FALLBACKS = [
  "Got it — tell me a bit more about what you're aiming for and I'll dig in.",
  "That's a good question. Here's how I'd think about it: break it into smaller steps, then tackle the trickiest one first.",
  "I don't have live data in this scaffold, but structurally that's an easy thing to wire up — check the README for where to plug in a real API call.",
  "Makes sense. Want me to sketch a quick plan, or would a direct answer be more useful right now?",
];

const KEYWORD_REPLIES = [
  { test: /hello|hi|hey/i, reply: "Hey! What are you working on today?" },
  { test: /help/i, reply: "Happy to help. What's the problem you're stuck on?" },
  {
    test: /react|component/i,
    reply:
      "For React, I'd start by isolating state at the lowest common parent and keeping components presentational where possible. Want a concrete example?",
  },
  {
    test: /thanks|thank you/i,
    reply: "Anytime — let me know if anything else comes up.",
  },
];

export function getBotReply(userText) {
  const match = KEYWORD_REPLIES.find((entry) => entry.test.test(userText));
  if (match) return match.reply;
  return FALLBACKS[Math.floor(Math.random() * FALLBACKS.length)];
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
      "Hi, I'm Nimbus. Ask me anything, or try one of the prompts below to see the interface in action.",
    time: "9:12 AM",
  },
];
