import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import InputBar from "./components/InputBar.jsx";
import GraphPanel from "./components/GraphPanel.jsx";
import { SAMPLE_CONVERSATIONS, INITIAL_MESSAGES, getBotReply } from "./data/mockBot.js";
import { buildTurnSubgraph, buildSpineEdge } from "./graph/graphGen.js";

let idCounter = 100;
const nextId = () => `m${idCounter++}`;
const now = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export default function App() {
  const [conversations] = useState(SAMPLE_CONVERSATIONS);
  const [activeId, setActiveId] = useState(SAMPLE_CONVERSATIONS[0].id);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Real graph from /api/graph — never overwritten by chat activity
  const realGraphNodesRef = useRef([]);
  const realGraphEdgesRef = useRef([]);
  const [apiConnected, setApiConnected] = useState(false);

  // Chat conversation overlay nodes (appended on top of real graph)
  const [chatOverlayNodes, setChatOverlayNodes] = useState([]);
  const [chatOverlayEdges, setChatOverlayEdges] = useState([]);

  const [graphOpen, setGraphOpen] = useState(true);
  const turnRef = useRef(0);
  const lastTurnIdRef = useRef(null);

  // Combined nodes/edges: real graph base + chat overlay on top
  const graphNodes = [...realGraphNodesRef.current, ...chatOverlayNodes];
  const graphEdges = [...realGraphEdgesRef.current, ...chatOverlayEdges];

  const activeConversation = conversations.find((c) => c.id === activeId);

  // Load real ChronoGraph graph-ready data from integration API on mount
  useEffect(() => {
    async function loadRealGraph() {
      try {
        const res = await fetch("/api/graph?limit=12");
        if (res.ok) {
          const data = await res.json();
          if (data.nodes && data.nodes.length > 0) {
            realGraphNodesRef.current = data.nodes;
            realGraphEdgesRef.current = data.edges;
            setApiConnected(true);
            // Trigger re-render by clearing overlay (forces recalculation of combined graph)
            setChatOverlayNodes([]);
            setChatOverlayEdges([]);
          }
        }
      } catch (err) {
        console.log("Integration API offline; using interactive simulated timeline mode.");
      }
    }
    loadRealGraph();
  }, []);

  // Only reset chat overlay nodes; real graph is never cleared
  const resetChatOverlay = () => {
    setChatOverlayNodes([]);
    setChatOverlayEdges([]);
    turnRef.current = 0;
    lastTurnIdRef.current = null;
  };

  const sendMessage = (text) => {
    const userMessage = { id: nextId(), role: "user", content: text, time: now() };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    const delay = 700 + Math.random() * 700;
    setTimeout(() => {
      const replyText = getBotReply(text);
      const reply = { id: nextId(), role: "assistant", content: replyText, time: now() };
      setMessages((prev) => [...prev, reply]);
      setIsTyping(false);

      // Build this turn's subgraph and append to chat overlay only.
      // The real /api/graph data in realGraphNodesRef is never touched.
      turnRef.current += 1;
      const { turnNode, entityNodes, edges } = buildTurnSubgraph(turnRef.current, {
        userText: text,
        botText: replyText,
        time: reply.time,
      });

      setChatOverlayNodes((prev) => [...prev, turnNode, ...entityNodes]);
      setChatOverlayEdges((prev) => {
        const spine = lastTurnIdRef.current
          ? [buildSpineEdge(lastTurnIdRef.current, turnNode.id)]
          : [];
        return [...prev, ...spine, ...edges];
      });
      lastTurnIdRef.current = turnNode.id;
    }, delay);
  };

  const handleNewChat = () => {
    setMessages(INITIAL_MESSAGES);
    setIsTyping(false);
    setSidebarOpen(false);
    resetChatOverlay();
  };

  const handleSelect = (id) => {
    setActiveId(id);
    setMessages(INITIAL_MESSAGES);
    setSidebarOpen(false);
    resetChatOverlay();
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-mist-50 font-body">
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-20 bg-ink-950/40 md:hidden"
        />
      )}
      {graphOpen && (
        <div
          onClick={() => setGraphOpen(false)}
          className="fixed inset-0 z-20 bg-ink-950/40 md:hidden"
        />
      )}

      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
        isOpen={sidebarOpen}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          title={activeConversation?.title ?? "New chat"}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          onToggleGraph={() => setGraphOpen((v) => !v)}
          graphOpen={graphOpen}
        />
        <ChatWindow messages={messages} isTyping={isTyping} onSuggestion={sendMessage} />
        <InputBar onSend={sendMessage} disabled={isTyping} />
      </div>

      <GraphPanel
        nodes={graphNodes}
        edges={graphEdges}
        isOpen={graphOpen}
        onClose={() => setGraphOpen(false)}
        apiConnected={apiConnected}
      />
    </div>
  );
}
