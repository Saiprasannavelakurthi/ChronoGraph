// Mock "historical record" the assistant draws on when answering.
// Each source is either a Slack message or a Git PR, with enough metadata
// to render a real-looking citation card. Swap this file for a live
// Slack/GitHub index in production — nothing else needs to change, since
// components only ever read from getSource(id).

export const SOURCES = {
  "slack-auth-1": {
    id: "slack-auth-1",
    type: "slack",
    channel: "#eng-platform",
    author: "Priya Nandan",
    time: "Mar 3, 10:42 AM",
    excerpt:
      "Proposing we move session validation into shared middleware so every route gets the same auth checks instead of copy-pasted guards in each controller.",
  },
  "pr-214": {
    id: "pr-214",
    type: "github",
    repo: "acme/platform-api",
    number: 214,
    title: "Refactor session auth into shared middleware",
    author: "jordan-lee",
    time: "Merged Mar 5",
    excerpt:
      "Extracts the duplicated session-check logic from 6 controllers into src/middleware/auth.ts, with unit tests covering expired and malformed tokens.",
  },
  "slack-onboarding-1": {
    id: "slack-onboarding-1",
    type: "slack",
    channel: "#product-copy",
    author: "Marcus Webb",
    time: "Feb 18, 3:05 PM",
    excerpt:
      "Feedback from the last round: the onboarding emails read too formal. Let's warm up the tone and cut the third email entirely, it's redundant with the in-app tour.",
  },
  "pr-231": {
    id: "pr-231",
    type: "github",
    repo: "acme/marketing-site",
    number: 231,
    title: "Rewrite onboarding email templates, drop email #3",
    author: "aiko-tanaka",
    time: "Merged Feb 21",
    excerpt:
      "Updates templates/onboarding-1.mjml and onboarding-2.mjml with a warmer tone per copy team feedback, and removes onboarding-3.mjml from the send sequence.",
  },
  "slack-cypress-1": {
    id: "slack-cypress-1",
    type: "slack",
    channel: "#qa-automation",
    author: "Sam Okafor",
    time: "Apr 9, 9:18 AM",
    excerpt:
      "Found it — the checkout test is flaky because it depends on Date.now() for a countdown timer. Passes locally, fails in CI depending on when the run starts.",
  },
  "pr-247": {
    id: "pr-247",
    type: "github",
    repo: "acme/platform-web",
    number: 247,
    title: "Fix flaky checkout test by mocking the clock",
    author: "sam-okafor",
    time: "Merged Apr 10",
    excerpt:
      "Uses cy.clock() to freeze time at the start of the checkout spec so the countdown timer assertion no longer depends on wall-clock timing.",
  },
  "slack-deploy-1": {
    id: "slack-deploy-1",
    type: "slack",
    channel: "#launch-checklist",
    author: "Dana Whitfield",
    time: "May 6, 4:52 PM",
    excerpt:
      "Our deploys keep going out during peak traffic and causing brief error spikes. Proposing we gate production deploys to a fixed low-traffic window and require a green canary run first.",
  },
  "pr-268": {
    id: "pr-268",
    type: "github",
    repo: "acme/deploy-tooling",
    number: 268,
    title: "Add canary stage and deploy-window guard to release pipeline",
    author: "dana-whitfield",
    time: "Merged May 9",
    excerpt:
      "Adds a 10-minute canary stage before full rollout and blocks `deploy prod` outside the 2-4am UTC window unless --force is passed with a documented reason.",
  },
  "slack-ratelimit-1": {
    id: "slack-ratelimit-1",
    type: "slack",
    channel: "#eng-platform",
    author: "Yusuf Demir",
    time: "Jun 14, 11:20 AM",
    excerpt:
      "We're seeing a handful of API keys hammering the /search endpoint at 200+ req/s. We should add per-key rate limiting before this takes down shared infra for everyone else.",
  },
  "pr-279": {
    id: "pr-279",
    type: "github",
    repo: "acme/platform-api",
    number: 279,
    title: "Add per-API-key rate limiting to public endpoints",
    author: "yusuf-demir",
    time: "Merged Jun 16",
    excerpt:
      "Introduces a token-bucket limiter keyed by API key, defaulting to 20 req/s with a burst of 40, returning 429 with a Retry-After header once exceeded.",
  },
};

export function getSource(id) {
  return SOURCES[id] ?? null;
}
