# ChronoGraph — Chat UI with Subgraph Timeline

A modern chatbot interface built with React (Vite) and Tailwind CSS, with a
live subgraph/timeline visualization powered by **React Flow** rendered
alongside every chat response.

## Stack

- React 18 + Vite
- Tailwind CSS (custom theme in `tailwind.config.js`)
- lucide-react for icons
- **reactflow** for the subgraph/timeline visualization panel

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
    Header.jsx            top bar, active conversation title, graph toggle
    ChatWindow.jsx         scrolling message list + suggestion chips
    MessageBubble.jsx      single user/assistant message
    TypingIndicator.jsx    animated "..." bubble
    InputBar.jsx           auto-resizing textarea + send button
    GraphPanel.jsx          React Flow panel rendering the subgraph timeline
  graph/
    graphGen.js             turns each chat turn into timeline + entity nodes
    CustomNodes.jsx          custom-styled React Flow node components
  data/
    mockBot.js              canned replies + sample conversation data
  App.jsx                   state management, layout composition
  index.css                 Tailwind directives + scrollbar styling
```

## How the subgraph timeline works

Every time the assistant replies, `App.jsx` calls
`buildTurnSubgraph()` (in `src/graph/graphGen.js`), which:

1. Creates a **turn node** — a pill on the timeline spine, labeled `Turn N`
   with a timestamp.
2. Extracts up to four keyword **entity nodes** from that turn's user and
   assistant text (a lightweight stopword-filtered keyword picker — swap
   this for a real NER/entity-extraction call to produce a genuine
   knowledge graph).
3. Draws dashed radial edges from the turn node to its entity nodes, and a
   solid animated edge chaining each turn node to the previous one, so the
   whole conversation reads as a left-to-right timeline with a subgraph
   hanging off each point.

The panel toggles open/closed from the header button (`View graph` /
`Hide graph`) and is fully responsive — an overlay drawer on mobile, a
persistent right-hand column on desktop.

## Wiring up a real model

Replies are currently simulated in `src/data/mockBot.js` via
`getBotReply()`. To connect a real backend, replace the `setTimeout` block
in `App.jsx`'s `sendMessage` function with an API call, e.g.:

```js
const res = await fetch("/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: text }),
});
const { reply, subgraph } = await res.json();
```

If your backend already returns a proper subgraph (real entities and
relationships instead of keyword-extracted stand-ins), pass its nodes/edges
straight into `setGraphNodes` / `setGraphEdges` instead of calling
`buildTurnSubgraph()`.

## Customizing the look

Colors, fonts, and animation timings are defined as design tokens in
`tailwind.config.js` under `theme.extend`. Update the `ink`, `mist`,
`signal`, and `pulse` color scales to reskin the interface — including the
graph panel's node styling in `src/graph/CustomNodes.jsx` — without
touching layout code.
