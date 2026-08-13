import { useRef, useState } from "react";
import { ArrowUp, Paperclip } from "lucide-react";

export default function InputBar({ onSend, disabled }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef(null);

  const handleChange = (e) => {
    setValue(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  };

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-mist-200 bg-white px-4 py-4 md:px-8">
      <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-mist-200 bg-mist-50 px-3 py-2 shadow-bubble focus-within:border-signal-500/50">
        <button
          type="button"
          className="mb-1 shrink-0 rounded-lg p-1.5 text-ink-600 transition-colors hover:bg-mist-100 hover:text-ink-800"
          aria-label="Attach a file"
        >
          <Paperclip size={17} />
        </button>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Message Nimbus..."
          className="scroll-thin max-h-40 flex-1 resize-none bg-transparent py-1.5 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-600/60 focus:outline-none"
        />

        <button
          onClick={submit}
          disabled={!value.trim() || disabled}
          aria-label="Send message"
          className="mb-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-950 text-white transition-all enabled:hover:bg-signal-600 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <ArrowUp size={16} strokeWidth={2.5} />
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-center text-[11px] text-ink-600/70">
        Nimbus can make mistakes. This is a UI scaffold — replies are simulated.
      </p>
    </div>
  );
}
