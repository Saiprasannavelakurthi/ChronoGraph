import { useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import InputBar from "./components/InputBar.jsx";
import RightPanel from "./components/RightPanel.jsx";
import { SAMPLE_CONVERSATIONS, INITIAL_MESSAGES, getBotReply } from "./data/mockBot.js";
import { getSource } from "./data/sources.js";
import { buildTurnSubgraph, buildSpineEdge, createGraphRegistry } from "./graph/graphGen.js";

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
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelTab, setPanelTab] = useState("timeline");
  const turnRef = useRef(0);
  const lastTurnIdRef = useRef(null);
  const graphRegistryRef = useRef(createGraphRegistry());

  // Conversational context: which topic the discussion is currently on,
  // so a follow-up like "why?" or "tell me more" can be resolved without
  // repeating the topic name.
  const activeTopicRef = useRef(null);

  // Citations: an ordered list of unique source ids cited so far this
  // conversation, plus which one is currently highlighted.
  const [citedSourceIds, setCitedSourceIds] = useState([]);
  const [activeSourceId, setActiveSourceId] = useState(null);

  const activeConversation = conversations.find((c) => c.id === activeId);
  const citedSources = citedSourceIds.map(getSource).filter(Boolean);

  const resetGraph = () => {
    setGraphNodes([]);
    setGraphEdges([]);
    turnRef.current = 0;
    lastTurnIdRef.current = null;
    graphRegistryRef.current = createGraphRegistry();
    activeTopicRef.current = null;
    setCitedSourceIds([]);
    setActiveSourceId(null);
    setPanelTab("timeline");
  };

  const handleSelectSource = (sourceId) => {
    setActiveSourceId(sourceId);
    setPanelTab("sources");
    setPanelOpen(true);
  };

  const sendMessage = (text) => {
    const userMessage = { id: nextId(), role: "user", content: text, time: now() };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    const delay = 700 + Math.random() * 700;
    setTimeout(() => {
      const {
        content: replyText,
        citedSourceIds: newCiteIds,
        suggestions,
        topicKey,
        topicLabel,
        isFollowUp,
        entities,
      } = getBotReply(text, activeTopicRef.current);

      const reply = {
        id: nextId(),
        role: "assistant",
        content: replyText,
        time: now(),
        citedSourceIds: newCiteIds,
        suggestions,
        topicLabel,
        isFollowUp,
      };
      setMessages((prev) => [...prev, reply]);
      setIsTyping(false);

      // Only a real topic match updates the active context — a greeting
      // or a fallback doesn't overwrite what the conversation was about.
      if (topicKey) activeTopicRef.current = topicKey;

      if (newCiteIds.length > 0) {
        setCitedSourceIds((prev) => [...new Set([...prev, ...newCiteIds])]);
      }

      // Build this turn's subgraph and chain it onto the running timeline.
      // Entity nodes are reused across turns on the same topic (see
      // graphGen.js), so follow-ups visibly reconnect to existing nodes
      // instead of duplicating them.
      turnRef.current += 1;
      const { turnNode, newEntityNodes, edges } = buildTurnSubgraph(
        turnRef.current,
        { time: reply.time, topicKey, entities, isFollowUp, userText: text, botText: replyText },
        graphRegistryRef.current
      );

      setGraphNodes((prev) => [...prev, turnNode, ...newEntityNodes]);
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
      {panelOpen && (
        <div
          onClick={() => setPanelOpen(false)}
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
          onTogglePanel={() => setPanelOpen((v) => !v)}
          panelOpen={panelOpen}
        />
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSuggestion={sendMessage}
          activeSourceId={activeSourceId}
          onSelectSource={handleSelectSource}
        />
        <InputBar onSend={sendMessage} disabled={isTyping} />
      </div>

      <RightPanel
        isOpen={panelOpen}
        onClose={() => setPanelOpen(false)}
        activeTab={panelTab}
        onTabChange={setPanelTab}
        graphNodes={graphNodes}
        graphEdges={graphEdges}
        citedSources={citedSources}
        activeSourceId={activeSourceId}
        onSelectSource={handleSelectSource}
      />
    </div>
  );
}
