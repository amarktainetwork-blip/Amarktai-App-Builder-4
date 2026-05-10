import { useEffect, useRef, useState } from "react";
import { Send, ArrowUp } from "lucide-react";
import { AGENTS } from "@/lib/agents";

export default function ChatPanel({ messages, onSend, disabled, busy }) {
  const [text, setText] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  const submit = (e) => {
    e?.preventDefault();
    const v = text.trim();
    if (!v || disabled) return;
    onSend(v);
    setText("");
  };

  return (
    <div data-testid="chat-panel" className="flex flex-col flex-1 min-h-0">
      <div className="px-4 pt-3 pb-2 border-b border-amk-line">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-amk-fg3">
          Conversation
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-thin px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="grid-bg h-full grid place-items-center text-center py-10">
            <div className="max-w-xs">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3 mb-2">
                [ standby ]
              </div>
              <p className="text-sm text-amk-fg2 leading-relaxed">
                Describe an app and watch four agents collaborate to build it in front of you.
              </p>
            </div>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} msg={m} />
        ))}
        {busy && (
          <div className="font-mono text-[11px] text-amk-fg3 px-1">
            <span className="ascii-loader"><span className="ascii-dots" /></span>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-amk-line p-3">
        <div className="flex gap-2 items-end">
          <textarea
            data-testid="chat-input-textarea"
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            placeholder={disabled ? "Agents are busy..." : "Iterate: 'change logo to a horse', 'make it dark mode'..."}
            disabled={disabled}
            className="flex-1 bg-amk-panel border border-amk-line text-sm px-3 py-2 resize-none focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3 font-sans disabled:opacity-50"
          />
          <button
            type="submit"
            data-testid="chat-send-btn"
            disabled={disabled || !text.trim()}
            className="h-[56px] w-11 grid place-items-center bg-white text-black hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-white"
          >
            <ArrowUp className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
        <div className="font-mono text-[10px] text-amk-fg3 mt-2 flex items-center gap-3">
          <span>↵ send</span><span>⇧↵ newline</span>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === "user";
  const isSystem = msg.role === "system";
  const agent = msg.agent && AGENTS[msg.agent];
  const color = agent?.color || (isUser ? "#FAFAFA" : "#A1A1AA");

  if (isSystem) {
    return (
      <div className="font-mono text-[11px] text-amk-fg3 italic px-1 animate-fade-up">
        {`// ${msg.content}`}
      </div>
    );
  }

  return (
    <div data-testid={`msg-${msg.id}`} className="animate-fade-up">
      <div className="flex items-baseline gap-2 mb-1">
        <span
          className="font-mono text-[11px] uppercase tracking-wider"
          style={{ color }}
        >
          {isUser ? "YOU" : (agent?.label || "AGENT")}
        </span>
        {msg.meta?.model && (
          <span className="font-mono text-[10px] text-amk-fg3">
            // {msg.meta.model}
          </span>
        )}
      </div>
      <div
        className={`text-sm leading-relaxed whitespace-pre-wrap font-sans ${
          isUser ? "text-amk-fg" : "text-amk-fg2"
        } pl-0`}
        style={isUser ? {} : { borderLeft: `2px solid ${color}33`, paddingLeft: 10 }}
      >
        {msg.content}
      </div>
      {msg.meta?.files?.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5 pl-3">
          {msg.meta.files.map((f) => (
            <span key={f} className="font-mono text-[10px] px-1.5 py-0.5 border border-amk-line text-amk-fg2">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
