import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import InputBar from "./components/InputBar.jsx";
import { SAMPLE_CONVERSATIONS, INITIAL_MESSAGES, getBotReply } from "./data/mockBot.js";

let idCounter = 100;
const nextId = () => `m${idCounter++}`;
const now = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export default function App() {
  const [conversations] = useState(SAMPLE_CONVERSATIONS);
  const [activeId, setActiveId] = useState(SAMPLE_CONVERSATIONS[0].id);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const activeConversation = conversations.find((c) => c.id === activeId);

  const sendMessage = (text) => {
    const userMessage = { id: nextId(), role: "user", content: text, time: now() };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    const delay = 700 + Math.random() * 700;
    setTimeout(() => {
      const reply = { id: nextId(), role: "assistant", content: getBotReply(text), time: now() };
      setMessages((prev) => [...prev, reply]);
      setIsTyping(false);
    }, delay);
  };

  const handleNewChat = () => {
    setMessages(INITIAL_MESSAGES);
    setIsTyping(false);
    setSidebarOpen(false);
  };

  const handleSelect = (id) => {
    setActiveId(id);
    setMessages(INITIAL_MESSAGES);
    setSidebarOpen(false);
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-mist-50 font-body">
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
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
        />
        <ChatWindow messages={messages} isTyping={isTyping} onSuggestion={sendMessage} />
        <InputBar onSend={sendMessage} disabled={isTyping} />
      </div>
    </div>
  );
}
