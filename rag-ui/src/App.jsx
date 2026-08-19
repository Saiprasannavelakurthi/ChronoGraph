import { useRef, useState } from "react";
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

  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [graphOpen, setGraphOpen] = useState(true);
  const turnRef = useRef(0);
  const lastTurnIdRef = useRef(null);

  const activeConversation = conversations.find((c) => c.id === activeId);

  const resetGraph = () => {
    setGraphNodes([]);
    setGraphEdges([]);
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

      // Build this turn's subgraph and chain it onto the running timeline.
      turnRef.current += 1;
      const { turnNode, entityNodes, edges } = buildTurnSubgraph(turnRef.current, {
        userText: text,
        botText: replyText,
        time: reply.time,
      });

      setGraphNodes((prev) => [...prev, turnNode, ...entityNodes]);
      setGraphEdges((prev) => {
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
    resetGraph();
  };

  const handleSelect = (id) => {
    setActiveId(id);
    setMessages(INITIAL_MESSAGES);
    setSidebarOpen(false);
    resetGraph();
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
      />
    </div>
  );
}
