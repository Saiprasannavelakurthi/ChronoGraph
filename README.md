# ChronoGraph — Chat UI with Subgraph Timeline + Citations + Follow-ups

A modern chatbot interface built with React (Vite) and Tailwind CSS, with:

- A live **subgraph timeline** (React Flow) rendered alongside the chat
- A **citation system** that highlights exactly which historical Slack
  message or Git PR each answer is grounded in
- **Follow-up awareness** — "why?", "tell me more", "what about that"
  resolve against the active topic instead of dead-ending, and the graph
  reflects that same continuity instead of duplicating nodes per turn

## Stack

- React 18 + Vite
- Tailwind CSS (custom theme in `tailwind.config.js`)
- lucide-react for icons
- **reactflow** for the subgraph/timeline visualization

## Getting started

```bash
npm install
npm run dev
```

Then open the printed local URL (usually `http://localhost:5173`).

To build for production:

```bash
npm run build
npm run preview
```

## Project structure

```
src/
  components/
    Sidebar.jsx          conversation list + new chat
    Header.jsx             top bar, active conversation title, panel toggle
    ChatWindow.jsx          scrolling message list + suggestion chips
    MessageBubble.jsx       message bubble; parses [n] into citation badges,
                              shows a "Continuing: <topic>" tag on follow-ups
    CitationBadge.jsx        inline numbered marker, e.g. the "[1]" in a reply
    SourceChip.jsx            small chip below a message, one per cited source
    TypingIndicator.jsx      animated "..." bubble
    InputBar.jsx              auto-resizing textarea + send button
    RightPanel.jsx             tabbed side panel: Timeline / Sources
    SubgraphView.jsx           React Flow canvas (the "Timeline" tab)
    SourcesView.jsx             citation detail + running source list (the "Sources" tab)
  graph/
    graphGen.js              turns each chat turn into timeline + entity nodes;
                               reuses entity nodes across turns on the same
                               topic via a per-conversation registry
    CustomNodes.jsx           custom-styled React Flow node components
  data/
    mockBot.js                topic-aware canned replies with initial +
                                follow-up answers and citedSourceIds
    sources.js                 mock Slack messages + Git PRs (the "historical record")
  App.jsx                     state management, layout composition
  index.css                   Tailwind directives + scrollbar styling
```

## How citations work

This demo recognizes five topics out of the box, each backed by a mock
Slack message + PR pair: **auth middleware**, **onboarding emails**,
**flaky Cypress tests**, **deploy pipeline changes**, and **API rate
limiting**. Anything else falls back to a message saying so — that's
expected, not a bug, since there's no source indexed for it. Add more
entries to `REPLIES` in `mockBot.js` and `SOURCES` in `sources.js` to
cover additional topics.

Each canned reply in `src/data/mockBot.js` is written with inline markers —
`[1]`, `[2]` — and a matching `citedSourceIds` array, e.g.:

```js
{
  content: "...moved into shared middleware [1]. That shipped as ... [2].",
  citedSourceIds: ["slack-auth-1", "pr-214"],
}
```

`MessageBubble.jsx` parses those markers and renders each one as a small
clickable **citation badge** exactly where the claim appears in the text —
not just a bibliography at the bottom, but a marker on the specific
sentence it supports. Every assistant message also gets a row of
**source chips** underneath (Slack channel or `repo #PR`) summarizing
everything it cited.

Clicking a citation badge or source chip opens the **Sources** tab in the
right-hand panel, which shows:

- A detail card for the exact excerpt used, with channel/author/timestamp
  (Slack) or repo/PR number/author/merge date (GitHub)
- A running list of every source cited so far in the conversation, so you
  can see the full "paper trail" behind the chat, not just the latest one

The right panel has two tabs — **Timeline** (the subgraph visualization)
and **Sources** (citations) — so both features share one consistent,
collapsible panel instead of competing for space.

## How follow-up context works

Each topic in `src/data/mockBot.js` has both an `initial` answer and a
`followUp` answer. `getBotReply(userText, activeTopicKey)` takes the
conversation's currently active topic as a second argument:

1. If the message matches a topic's keywords directly, that topic's
   `initial` answer is returned and becomes the new active topic.
2. Otherwise, if the message *looks* like a follow-up — starts with "why",
   "what about", "tell me more", or is a short pronoun-led phrase like
   "is it tested?" — the currently active topic's `followUp` answer is
   returned instead of falling back to "I don't know."
3. Otherwise, it falls back with suggestion chips, without losing the
   active topic (so a follow-up right after a fallback can still resolve).

`App.jsx` holds the active topic in a ref and passes it into every call to
`getBotReply`, so context survives across turns without re-rendering on
every keystroke.

**The graph reflects the same context.** `buildTurnSubgraph()` in
`graphGen.js` takes a per-conversation `registry` (created via
`createGraphRegistry()`) that tracks which entity node already represents
each topic's keywords. A follow-up turn reuses those existing nodes —
drawn with a solid teal edge to show they were *recalled* — instead of
creating lookalike duplicates. If the conversation leaves a topic and
later comes back to it, a faint dashed "thread" edge links the new turn
back to that topic's very first turn, so resumed context is visible on
the timeline, not just in the chat text. Assistant messages answering a
follow-up also show a small "Continuing: <topic>" tag above the bubble.

## Wiring up real data

Two integration points cover the whole system:

- Replace `getBotReply()` in `src/data/mockBot.js` with a real retrieval
  call. It should return `{ content, citedSourceIds }`, where `content`
  contains `[n]` markers in the order sources are cited.
- Replace the contents of `src/data/sources.js` with a real Slack/GitHub
  index — `getSource(id)` is the only function the UI calls, so as long as
  it returns objects shaped like the existing mock entries (`type`,
  `channel`/`repo`, `author`, `time`, `excerpt`, plus `number`/`title` for
  PRs), no component code needs to change.

## Customizing the look

Colors, fonts, and animation timings are defined as design tokens in
`tailwind.config.js` under `theme.extend`. Update the `ink`, `mist`,
`signal`, and `pulse` color scales to reskin the interface — including
citation badges, source chips, and the graph panel's node styling — without
touching layout code.
