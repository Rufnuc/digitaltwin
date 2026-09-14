"use client";
import { useEffect, useRef, useState } from "react";
import { api, type AssistantResponse } from "@/lib/api";
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

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

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
      const response = await api.assistantAsk(q, ctrl.signal);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { question: q, response } : x)));
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

  return (
    <div>
      <PageHeader
        title="Benfieg"
        subtitle="Your AI business analyst. Ask in plain language — or tell it to make changes. It calls the business-data and simulation tools for every number (never invents figures) and can create/update records, refresh data, and run simulations, within your permissions."
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
