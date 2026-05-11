import { useState } from "react";
import { Sparkles, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * ClarificationModal
 *
 * Shown when the backend /api/clarify returns needs_clarification=true.
 * Lets users answer up to 5 focused questions or skip with defaults.
 *
 * Props:
 *   questions    – array of { id, question, options, required }
 *   assumptions  – array of strings (what defaults will be used)
 *   onConfirm    – fn(answers: Record<string,string>) – called with answers or {}
 *   onSkip       – fn() – use recommended defaults
 */
export default function ClarificationModal({ questions, assumptions, onConfirm, onSkip }) {
  const [answers, setAnswers] = useState({});

  const set = (id, value) => setAnswers((prev) => ({ ...prev, [id]: value }));

  const allRequired = questions.filter((q) => q.required);
  const requiredFilled = allRequired.every((q) => answers[q.id]);

  const handleConfirm = () => {
    onConfirm(answers);
  };

  return (
    <div
      data-testid="clarification-modal"
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 overflow-y-auto"
    >
      <div className="bg-amk-panel border border-amk-line max-w-lg w-full rounded-sm shadow-2xl">
        <div className="px-5 pt-5 pb-3 border-b border-amk-line">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-accent mb-1">
            [ clarification needed ]
          </div>
          <p className="text-sm text-amk-fg2 leading-relaxed">
            A few quick questions will help the agents build exactly what you need.
          </p>
        </div>

        <div className="p-5 space-y-5 max-h-[60vh] overflow-y-auto">
          {questions.map((q) => (
            <QuestionField
              key={q.id}
              question={q}
              value={answers[q.id] || ""}
              onChange={(v) => set(q.id, v)}
            />
          ))}

          {assumptions.length > 0 && (
            <div className="border border-amk-line bg-amk-base/40 p-3 rounded-sm">
              <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-2">
                Smart defaults (if you skip)
              </div>
              <ul className="space-y-1">
                {assumptions.map((a, i) => (
                  <li key={i} className="font-mono text-[11px] text-amk-fg2 flex items-start gap-1.5">
                    <ChevronRight className="w-3 h-3 mt-0.5 text-amk-accent shrink-0" strokeWidth={2} />
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="px-5 pb-5 pt-3 border-t border-amk-line flex gap-2">
          <Button
            data-testid="clarification-skip-btn"
            variant="outline"
            onClick={onSkip}
            className="flex-1 font-mono text-xs h-9 border-amk-line hover:bg-amk-surface"
          >
            Use recommended defaults
          </Button>
          <Button
            data-testid="clarification-confirm-btn"
            onClick={handleConfirm}
            disabled={!requiredFilled}
            className="flex-1 bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-9"
          >
            <Sparkles className="w-3 h-3 mr-1.5" strokeWidth={2} />
            Continue with my answers
          </Button>
        </div>
      </div>
    </div>
  );
}

function QuestionField({ question, value, onChange }) {
  const { id, question: label, options, required } = question;
  return (
    <div>
      <label className="block font-mono text-xs text-amk-fg mb-2">
        {label}
        {required && <span className="text-agent-scout ml-1">*</span>}
      </label>
      {options ? (
        <div className="grid grid-cols-1 gap-1.5">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              data-testid={`clarify-option-${id}-${opt.replace(/\s+/g, "-").toLowerCase().slice(0, 20)}`}
              onClick={() => onChange(opt)}
              className={`text-left px-3 py-2 border font-mono text-xs transition-colors duration-100 ${
                value === opt
                  ? "border-amk-accent bg-amk-surface text-white"
                  : "border-amk-line bg-amk-panel text-amk-fg2 hover:bg-amk-surface"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-amk-panel border border-amk-line h-9 px-3 font-mono text-xs focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
        />
      )}
    </div>
  );
}
