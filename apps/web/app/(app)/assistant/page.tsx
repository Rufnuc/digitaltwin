"use client";
import { useEffect, useRef, useState } from "react";
import { api, type AssistantResponse } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";

interface Turn {
  question: string;
  response?: AssistantResponse;
  error?: string;
  pending?: boolean;
}

const SUGGESTIONS = [
  "How is my business doing?",
  "What happens if I raise prices by 10%?",
  "What are my biggest risks?",
  "Which customers are at risk of churning?",
  "Run a monte carlo on raising prices 10%",
  "Compare price strategies",
  // Action commands — the assistant can make changes, not just answer:
  "Add customer Acme Motors in Lagos",
  "Refresh market data",
  "Run an impact scan",
  "Save a simulation raising prices 10%",
];

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setTurns((t) => [...t, { question: q, pending: true }]);
    try {
      const response = await api.assistantAsk(q);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { question: q, response } : x)));
    } catch (e) {
      const error = e instanceof Error ? e.message : "Request failed";
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { question: q, error } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="AI Assistant"
        subtitle="Ask in plain language — or tell it to make changes. It calls the business-data and simulation tools for every number (never invents figures) and can create/update records, refresh data, and run simulations, within your permissions."
      />

      {turns.length === 0 && (
        <Card className="mb-4 p-4">
          <div className="mb-2 text-sm font-medium">Try asking</div>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-line px-3 py-1.5 text-sm hover:bg-wash"
              >
                {s}
              </button>
            ))}
          </div>
        </Card>
      )}

      <div className="space-y-4">
        {turns.map((t, i) => (
          <div key={i}>
            <div className="mb-2 flex justify-end">
              <div className="max-w-[80%] rounded-lg bg-ink px-3 py-2 text-sm text-paper">
                {t.question}
              </div>
            </div>
            {t.pending && <div className="text-sm text-muted">Thinking…</div>}
            {t.error && <div className="text-sm text-red-700">Error: {t.error}</div>}
            {t.response && <AnswerCard r={t.response} />}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="sticky bottom-0 mt-4 flex gap-2 bg-wash py-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your business, or a what-if scenario…"
          className="flex-1 rounded border border-line px-3 py-2 text-sm outline-none focus:border-ink"
        />
        <button
          disabled={busy || !input.trim()}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function AnswerCard({ r }: { r: AssistantResponse }) {
  const [showTools, setShowTools] = useState(false);
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center gap-2">
        <ProvenanceBadge origin={r.provenance} />
        <span className="text-[11px] text-muted">
          via {r.provider}
          {r.model ? ` · ${r.model}` : ""}
        </span>
      </div>
      <div className="whitespace-pre-wrap text-sm">{r.answer}</div>

      {r.actions_taken.length > 0 && (
        <div className="mt-2 rounded border border-green-200 bg-green-50 px-2 py-1 text-xs text-green-800">
          ✓ Change applied: {r.actions_taken.join(", ")}
        </div>
      )}

      {r.tool_calls.length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setShowTools((v) => !v)}
            className="text-xs text-muted underline decoration-dotted"
          >
            {showTools ? "Hide" : "Show"} data sources ({r.tool_calls.length} tool
            {r.tool_calls.length === 1 ? "" : "s"})
          </button>
          {showTools && (
            <div className="mt-2 space-y-2">
              {r.tool_calls.map((c, i) => (
                <div key={i} className="rounded border border-line bg-wash p-2">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-xs">{c.name}</span>
                    <ProvenanceBadge origin={c.provenance} />
                  </div>
                  <pre className="max-h-40 overflow-auto text-[10px] leading-relaxed text-muted">
                    {JSON.stringify(c.result, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 border-t border-line pt-2 text-[11px] text-muted">{r.disclaimer}</div>
    </Card>
  );
}
