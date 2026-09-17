"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type AssistantProposal,
  type AssistantResponse,
  type ConversationDetail,
  type ConversationSummary,
} from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ProvenanceBadge } from "@/components/ui";
import { MicRecorder } from "@/lib/recorder";
import { printReport } from "@/lib/printReport";

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

// Rebuild the on-screen turns from a stored conversation. Messages alternate
// user → assistant; each user message plus its following assistant message is
// one turn, rendered exactly as it was live (answer + tool trace + provenance).
function toTurns(detail: ConversationDetail): Turn[] {
  const turns: Turn[] = [];
  const msgs = detail.messages;
  for (let i = 0; i < msgs.length; i++) {
    if (msgs[i].role !== "user") continue;
    const q = msgs[i].content;
    const a = msgs[i + 1]?.role === "assistant" ? msgs[i + 1] : null;
    if (a) {
      const m = a.meta ?? {};
      turns.push({
        question: q,
        response: {
          question: q,
          answer: a.content,
          provider: m.provider ?? "",
          model: m.model ?? null,
          provenance: m.provenance ?? "AI_INTERPRETATION",
          tool_calls: m.tool_calls ?? [],
          actions_taken: m.actions_taken ?? [],
          disclaimer: m.disclaimer ?? "",
        },
      });
      i++; // consumed the assistant message
    } else {
      turns.push({ question: q, error: "No saved answer." });
    }
  }
  return turns;
}

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      const r = await api.listConversations();
      setConversations(r.items);
    } catch {
      /* ignore — history is a convenience, not critical to asking */
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  function newChat() {
    stop();
    setTurns([]);
    setActiveId(null);
    setInput("");
    setHistoryOpen(false);
  }

  async function openChat(id: number) {
    stop();
    setHistoryOpen(false);
    try {
      const detail = await api.getConversation(id);
      setActiveId(detail.id);
      setTurns(toTurns(detail));
    } catch {
      setVoiceError("Could not open that chat.");
    }
  }

  async function removeChat(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (!window.confirm("Delete this chat? This cannot be undone.")) return;
    try {
      await api.deleteConversation(id);
      setConversations((cs) => cs.filter((c) => c.id !== id));
      if (activeId === id) newChat();
    } catch {
      /* ignore */
    }
  }

  // Stop a request in flight: abort the fetch and drop the pending turn.
  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setTurns((t) =>
      t.length && t[t.length - 1].pending
        ? t.map((x, i) => (i === t.length - 1 ? { ...x, pending: false, error: "Stopped." } : x))
        : t,
    );
  }

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setTurns((t) => [...t, { question: q, pending: true }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const response = await api.assistantAsk(q, activeId ?? undefined, ctrl.signal);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { question: q, response } : x)));
      // Adopt the conversation the server saved this turn into, then refresh
      // the list so a new chat appears (and existing ones re-sort to the top).
      if (response.conversation_id != null) setActiveId(response.conversation_id);
      loadConversations();
    } catch (e) {
      if (ctrl.signal.aborted) return; // stop() already handled the UI
      const error = e instanceof Error ? e.message : "Request failed";
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { question: q, error } : x)));
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setBusy(false);
    }
  }

  // Voice input: record the mic, then transcribe locally with Whisper and drop
  // the text into the input box for the user to review before sending.
  async function toggleMic() {
    setVoiceError(null);
    if (recording) {
      const rec = recorderRef.current;
      recorderRef.current = null;
      setRecording(false);
      if (!rec) return;
      setTranscribing(true);
      try {
        const wav = await rec.stop();
        const { text } = await api.assistantTranscribe(wav);
        if (text) setInput((prev) => (prev ? `${prev} ${text}` : text));
        else setVoiceError("Didn't catch that — try again.");
      } catch (e) {
        setVoiceError(e instanceof Error ? e.message : "Transcription failed.");
      } finally {
        setTranscribing(false);
      }
      return;
    }
    try {
      const rec = new MicRecorder();
      await rec.start();
      recorderRef.current = rec;
      setRecording(true);
    } catch {
      setVoiceError("Microphone access was blocked.");
    }
  }

  const historyPanel = (
    <div className="flex h-full flex-col">
      <button
        onClick={newChat}
        className="mb-2 w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper"
      >
        + New chat
      </button>
      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 && (
          <div className="px-1 py-2 text-xs text-muted">No past chats yet.</div>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            onClick={() => openChat(c.id)}
            className={`group mb-1 flex cursor-pointer items-center gap-1 rounded px-2 py-1.5 text-sm ${
              activeId === c.id ? "bg-ink text-paper" : "hover:bg-wash"
            }`}
          >
            <span className="min-w-0 flex-1 truncate" title={c.title}>
              {c.title}
            </span>
            <button
              onClick={(e) => removeChat(c.id, e)}
              title="Delete chat"
              aria-label="Delete chat"
              className={`shrink-0 rounded px-1 text-xs opacity-0 group-hover:opacity-100 ${
                activeId === c.id ? "text-paper hover:bg-white/20" : "text-muted hover:bg-line"
              }`}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Benfieg"
        subtitle="Your AI business analyst. Ask in plain language — or tell it to make changes. It calls the business-data and simulation tools for every number (never invents figures) and can create/update records, refresh data, and run simulations, within your permissions. Your chats are saved on the left."
      />

      <div className="flex gap-4">
        {/* History sidebar — persistent on desktop */}
        <aside className="hidden w-56 shrink-0 md:block">{historyPanel}</aside>

        {/* Chat column */}
        <div className="min-w-0 flex-1">
          {/* Mobile: history toggle */}
          <div className="mb-2 flex items-center gap-2 md:hidden">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
            >
              {historyOpen ? "Hide history" : "History"}
            </button>
            <button
              onClick={newChat}
              className="rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper"
            >
              + New chat
            </button>
          </div>
          {historyOpen && (
            <Card className="mb-3 max-h-72 p-2 md:hidden">{historyPanel}</Card>
          )}

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
            className="sticky bottom-0 mt-4 bg-wash py-2"
          >
            <div className="flex gap-2">
              <button
                type="button"
                onClick={toggleMic}
                disabled={busy || transcribing}
                title={recording ? "Stop recording" : "Speak your question"}
                aria-label={recording ? "Stop recording" : "Speak your question"}
                className={`flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded border text-base disabled:opacity-40 ${
                  recording
                    ? "animate-pulse border-red-500 bg-red-500/15 text-red-600"
                    : "border-line hover:bg-paper"
                }`}
              >
                {transcribing ? "…" : recording ? "⏹" : "🎤"}
              </button>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  recording
                    ? "Listening… tap the square to stop"
                    : transcribing
                      ? "Transcribing your voice…"
                      : "Ask about your business, or a what-if scenario…"
                }
                className="flex-1 rounded border border-line px-3 py-2 text-sm outline-none focus:border-ink"
              />
              {busy ? (
                <button
                  type="button"
                  onClick={stop}
                  className="rounded border border-red-500 bg-red-500/15 px-4 py-2 text-sm font-medium text-red-600"
                >
                  Stop
                </button>
              ) : (
                <button
                  disabled={!input.trim()}
                  className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40"
                >
                  Send
                </button>
              )}
            </div>
            {voiceError && <div className="mt-1 text-xs text-red-700">{voiceError}</div>}
          </form>
        </div>
      </div>
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
        <button
          onClick={() => printReport(r)}
          title="Export this report as PDF"
          className="ml-auto rounded border border-line px-2 py-1 text-[11px] hover:bg-wash"
        >
          Export PDF
        </button>
      </div>
      <div className="whitespace-pre-wrap text-sm">{r.answer}</div>

      {r.actions_taken.length > 0 && (
        <div className="mt-2 rounded border border-green-500/30 bg-green-500/15 px-2 py-1 text-xs text-green-700 dark:text-green-300">
          ✓ Change applied: {r.actions_taken.join(", ")}
        </div>
      )}

      {(r.proposals ?? []).map((p) => (
        <ProposalCard key={p.confirmation_token} proposal={p} />
      ))}

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

// A proposed assistant write awaiting explicit confirmation (two-step confirm-gating).
// Nothing has been written yet; the change only happens when the user presses Confirm.
function ProposalCard({ proposal }: { proposal: AssistantProposal }) {
  const [state, setState] = useState<"pending" | "confirming" | "done" | "dismissed">("pending");
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setState("confirming");
    setError(null);
    try {
      await api.assistantConfirm(proposal.confirmation_token);
      setState("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not apply the change");
      setState("pending");
    }
  }

  if (state === "done") {
    return (
      <div className="mt-2 rounded border border-green-500/30 bg-green-500/15 px-2 py-1.5 text-xs text-green-700 dark:text-green-300">
        ✓ Change applied: {proposal.action.replace(/_/g, " ")}
      </div>
    );
  }
  if (state === "dismissed") {
    return (
      <div className="mt-2 rounded border border-line px-2 py-1.5 text-xs text-muted">
        Change dismissed — nothing was applied.
      </div>
    );
  }
  return (
    <div className="mt-2 rounded border border-amber-500/40 bg-amber-500/10 px-2.5 py-2 text-xs">
      <div className="mb-1.5 font-medium text-amber-700 dark:text-amber-300">
        ⚠ Needs your confirmation — no change has been made yet
      </div>
      <div className="mb-2 text-muted">
        {proposal.message ?? `Ready to ${proposal.action.replace(/_/g, " ")}.`}
      </div>
      {error && <div className="mb-2 text-red-700">{error}</div>}
      <div className="flex gap-2">
        <button
          onClick={confirm}
          disabled={state === "confirming"}
          className="rounded bg-ink px-3 py-1 font-medium text-paper disabled:opacity-40"
        >
          {state === "confirming" ? "Applying…" : "Confirm"}
        </button>
        <button
          onClick={() => setState("dismissed")}
          disabled={state === "confirming"}
          className="rounded border border-line px-3 py-1 hover:bg-wash disabled:opacity-40"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
