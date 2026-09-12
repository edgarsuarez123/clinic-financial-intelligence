import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { ApiError, api, send } from "./api";
import { Card, Chart, Evidence, Field, Notice, Table, Select } from "./components";
import ClinicSelect from "./clinic-select";
import type { Row } from "./types";
import { newId as uuid } from "./uuid";
import "./clarity-chat.css";

type ChatContext = {
  start: string;
  end: string;
  clinic_location: string | null;
  budget_ids: string[];
};

type TurnInput = {
  turn_id: string;
  question: string;
  context: ChatContext;
};

type LocalTurn = TurnInput & {
  position: number;
  status: "running" | "failed";
  local_error?: string;
};

type ChatConfig = Row & {
  simulation_access?: boolean;
  diagnostics_enabled?: boolean;
  disclosure?: string;
  cost_report_access?: boolean;
};

type ErrorDetails = { message: string; code?: string };

const RESPONSE_LABELS: Record<string, string> = {
  invalid_request: "Request not supported",
  unsupported_request: "Request not supported",
  missing_setup: "Setup required",
  model_unavailable: "Model unavailable",
  service_unavailable: "Financial service unavailable",
  insufficient_data: "Insufficient recorded data",
  rate_limited: "Question limit reached",
};

function contextFor(
  start: string,
  end: string,
  clinic: string,
  budgetIds: string[],
): ChatContext {
  return {
    start,
    end,
    clinic_location: clinic || null,
    budget_ids: [...new Set(budgetIds)].slice(0, 3),
  };
}

function describeError(error: unknown): ErrorDetails {
  if (error instanceof ApiError) {
    if (error.status === 0) return { message: error.message, code: "network_unavailable" };
    if (error.status === 409) {
      return {
        message: "This conversation changed or a reply is already running. Reopen it before retrying.",
        code: "conversation_conflict",
      };
    }
    if (error.status === 404) {
      return {
        message: "This conversation or one of its attached saved plans is no longer available.",
        code: "missing_setup",
      };
    }
    if (error.status === 422) {
      return { message: "That request is not valid. Check the question and selected dates.", code: "invalid_request" };
    }
    if (error.status === 429) {
      return { message: "The clinic question limit has been reached. Try again later.", code: "rate_limited" };
    }
    if (error.status === 403) {
      return { message: "This feature is not configured for your account.", code: "missing_setup" };
    }
    if (error.status >= 500) {
      return { message: "The financial service could not complete this request. Try again later.", code: "service_unavailable" };
    }
    return { message: error.message, code: "request_failed" };
  }
  if (error instanceof Error && error.message) return { message: error.message, code: "request_failed" };
  return { message: "The question could not be sent. Try again.", code: "request_failed" };
}

function responseLabel(value: Row) {
  const code = value?.error_code;
  if (code && RESPONSE_LABELS[code]) return RESPONSE_LABELS[code];
  if (value?.status === "unavailable") return "Model unavailable";
  if (value?.status === "rate_limited") return "Question limit reached";
  if (value?.status === "refused") return "Request not supported";
  if (typeof value?.answer === "string" && value.answer.toLowerCase().startsWith("no recorded data was returned")) return "Insufficient recorded data";
  return "Clarity";
}

export default function Questions({
  config,
  start,
  end,
  onDraft,
}: {
  config: ChatConfig;
  start: string;
  end: string;
  onDraft?: (draft: Row) => void;
}) {
  const [threads, setThreads] = useState<Row[]>([]);
  const [thread, setThread] = useState<Row | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [plans, setPlans] = useState<Row[]>([]);
  const [budgetIds, setBudgetIds] = useState<string[]>([]);
  const [clinic, setClinic] = useState("");
  const [title, setTitle] = useState("");
  const [costs, setCosts] = useState<Row | null>(null);
  const [pending, setPending] = useState<TurnInput | null>(null);
  // Keep client-only turns until the server confirms their matching turn ID.
  // A single slot made an earlier failed question disappear when the user
  // started another question before retrying it.
  const [localTurns, setLocalTurns] = useState<LocalTurn[]>([]);
  const version = useRef(0);
  const newConversationId = useRef(uuid());
  const newConversationTitle = useRef("");
  const alive = useRef(true);
  const busyRef = useRef(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const latestTurnId = useRef<string | undefined>(undefined);

  useEffect(() => {
    alive.current = true;
    const initialVersion = version.current;
    const initialId = new URL(window.location.href).searchParams.get("chat");
    void list()
      .then(async (rows) => {
        if (!alive.current || version.current !== initialVersion) return;
        if (initialId || rows[0]) await open(initialId || rows[0].conversation_id);
      })
      .catch((e) => {
        if (alive.current) {
          const detail = describeError(e);
          setError(detail.message);
          setErrorCode(detail.code || "");
        }
      });
    if (config.simulation_access) {
      api("/simulations/budgets")
        .then((r) => alive.current && setPlans(r.budgets))
        .catch((e) => {
          if (alive.current) {
            const detail = describeError(e);
            setError(detail.message);
            setErrorCode(detail.code || "");
          }
        });
    }
    return () => {
      alive.current = false;
      version.current++;
    };
    // The workspace supplies one configuration for the lifetime of this screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const turns = displayedTurns(thread, localTurns);
    const latest = turns.at(-1)?.turn_id;
    const changed = latest !== latestTurnId.current;
    latestTurnId.current = latest;
    if (!changed && !busy) return;
    const container = messagesRef.current;
    if (!container || (!followLatest.current && !changed)) return;
    const target = container.querySelector<HTMLElement>("[data-latest-turn='true']");
    if (!target) return;
    requestAnimationFrame(() => {
      target.scrollIntoView?.({ behavior: changed ? "smooth" : "auto", block: "nearest" });
    });
  }, [thread?.revision, localTurns, busy]);

  async function list(offset = 0, requestVersion = version.current) {
    const r = await api(`/questions/conversations?offset=${offset}`);
    if (alive.current && requestVersion === version.current) {
      setThreads((current) => (offset ? [...current, ...r.conversations] : r.conversations));
      setHasMore(r.has_more);
    }
    return r.conversations as Row[];
  }

  function location(id: string | null) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("chat", id);
    else url.searchParams.delete("chat");
    window.history.replaceState(null, "", url);
  }

  async function open(id: string) {
    const openingDifferent = thread?.conversation_id !== id;
    const v = ++version.current;
    if (openingDifferent) {
      setLocalTurns([]);
      setPending(null);
      setQuestion("");
    }
    setError("");
    setErrorCode("");
    setBusy(true);
    busyRef.current = true;
    try {
      const r = await api(`/questions/conversations/${id}`);
      if (!alive.current || v !== version.current) return;
      setThread(r);
      setTitle(r.title);
      const latest = r.turns?.at(-1);
      setBudgetIds(latest?.context?.budget_ids || []);
      setClinic(latest?.context?.clinic_location || "");
      if (!openingDifferent) {
        // An interrupted request may have completed while the conversation
        // was being reopened. Remove only the local copies confirmed by this
        // response and retain unrelated failed turns for recovery.
        const savedIds = new Set((r.turns || []).map((turn: Row) => turn.turn_id));
        setLocalTurns((current) => current.filter((turn) => !savedIds.has(turn.turn_id)));
      }
      location(id);
    } catch (e) {
      if (alive.current && v === version.current) {
        const detail = describeError(e);
        setError(detail.message);
        setErrorCode(detail.code || "");
      }
    } finally {
      if (alive.current && v === version.current) {
        setBusy(false);
        busyRef.current = false;
      }
    }
  }

  function fresh() {
    version.current++;
    busyRef.current = false;
    newConversationId.current = uuid();
    newConversationTitle.current = "";
    setThread(null);
    setTitle("");
    setQuestion("");
    setError("");
    setErrorCode("");
    setPending(null);
    setLocalTurns([]);
    setBusy(false);
    setCosts(null);
    setBudgetIds([]);
    setClinic("");
    location(null);
  }

  async function ask(retry?: TurnInput, freshAttempt = false) {
    if (busyRef.current) return;
    const captured: TurnInput = retry || pending || {
      turn_id: uuid(),
      question: question.trim(),
      context: contextFor(start, end, clinic, budgetIds),
    };
    if (!captured.question.trim() || !captured.context.start || !captured.context.end) return;
    const preservingComposerDraft = Boolean(
      retry && !freshAttempt && question.trim() && pending?.turn_id !== captured.turn_id,
    );
    const v = ++version.current;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setErrorCode("");
    if (!preservingComposerDraft) setPending(captured);
    const existingLocal = localTurns.find((turn) => turn.turn_id === captured.turn_id);
    const position = existingLocal?.position || Math.max(
      0,
      ...(thread?.turns || []).map((turn: Row, index: number) => Number(turn.position) || index + 1),
      ...localTurns.map((turn) => turn.position),
    ) + 1;
    setLocalTurns((current) => {
      const existing = current.find((turn) => turn.turn_id === captured.turn_id);
      const next: LocalTurn = {
        ...captured,
        position: existing?.position || position,
        status: "running",
      };
      return existing
        ? current.map((turn) => turn.turn_id === captured.turn_id ? next : turn)
        : [...current, next];
    });
    try {
      let current = thread;
      if (!current) {
        if (!newConversationTitle.current) {
          newConversationTitle.current = captured.question.slice(0, 100) || "New conversation";
        }
        try {
          current = await send("/questions/conversations", {
            conversation_id: newConversationId.current,
            title: newConversationTitle.current,
          });
        } catch (createError) {
          // A lost create response is safe to recover by reading the same client UUID.
          // The repository's idempotent create contract prevents a second thread.
          if (createError instanceof ApiError && createError.status === 409) {
            current = await api(`/questions/conversations/${newConversationId.current}`);
          } else {
            throw createError;
          }
        }
        if (!alive.current || v !== version.current) return;
        if (!current) throw new Error("The conversation could not be opened.");
        setThread(current);
        setTitle(current.title);
        location(current.conversation_id);
      }
      if (!current) throw new Error("The conversation could not be opened.");
      const result = await send(
        `/questions/conversations/${current.conversation_id}/turns`,
        { ...captured, expected_revision: current.revision },
      );
      if (!alive.current || v !== version.current) return;
      setThread(result);
      if (!preservingComposerDraft) setQuestion("");
      setPending((current) => current?.turn_id === captured.turn_id ? null : current);
      const savedIds = new Set((result.turns || []).map((turn: Row) => turn.turn_id));
      setLocalTurns((current) => current.filter((turn) => !savedIds.has(turn.turn_id)));
      setTitle(result.title || title);
      try {
        await list();
      } catch (refreshError) {
        // The turn is already persisted and rendered above. A history refresh
        // failure must not convert a successful answer into a failed turn.
        if (alive.current && v === version.current) {
          const detail = describeError(refreshError);
          setError(detail.message);
          setErrorCode(detail.code || "");
        }
      }
    } catch (e) {
      if (alive.current && v === version.current) {
        const detail = describeError(e);
        setError(detail.message);
        setErrorCode(detail.code || "");
        setLocalTurns((current) => {
          const existing = current.find((turn) => turn.turn_id === captured.turn_id);
          if (!existing) {
            const position = Math.max(
              0,
              ...(thread?.turns || []).map((turn: Row, index: number) => Number(turn.position) || index + 1),
              ...current.map((turn) => turn.position),
            ) + 1;
            return [...current, { ...captured, position, status: "failed", local_error: detail.message }];
          }
          return current.map((turn) => turn.turn_id === captured.turn_id
            ? { ...turn, status: "failed", local_error: detail.message }
            : turn);
        });
        // Keep the exact ID/context so retry is idempotent if the server completed
        // before the network failed. The persisted unavailable state has its own
        // explicit fresh-attempt action below.
        if (!preservingComposerDraft) setPending(captured);
      }
    } finally {
      if (alive.current && v === version.current) {
        setBusy(false);
        busyRef.current = false;
      }
    }
  }

  function freshAttempt(turn: Row) {
    if (!thread || busyRef.current) return;
    const input: TurnInput = {
      turn_id: uuid(),
      question: turn.question,
      context: turn.context,
    };
    setQuestion("");
    void ask(input, true);
  }

  async function rename() {
    if (!thread || !title.trim() || busyRef.current) return;
    setError("");
    try {
      await send(
        `/questions/conversations/${thread.conversation_id}`,
        { title, expected_revision: thread.revision },
        "PATCH",
      );
      await open(thread.conversation_id);
      await list();
    } catch (e) {
      const detail = describeError(e);
      setError(detail.message);
      setErrorCode(detail.code || "");
    }
  }

  async function remove() {
    if (!thread || busyRef.current || !window.confirm("Delete this conversation from your history?")) return;
    try {
      await send(
        `/questions/conversations/${thread.conversation_id}`,
        { expected_revision: thread.revision },
        "DELETE",
      );
      fresh();
      await list();
    } catch (e) {
      const detail = describeError(e);
      setError(detail.message);
      setErrorCode(detail.code || "");
    }
  }

  const turns = useMemo(() => displayedTurns(thread, localTurns), [thread, localTurns]);
  const hasTurns = turns.length > 0;

  return (
    <div className="chat-workspace clarity-chat">
      <aside className="chat-sidebar clarity-history" aria-label="Conversation history">
        <button className="primary clarity-new" onClick={fresh} disabled={busy} type="button">
          <Plus size={16} /> New conversation
        </button>
        <details className="clarity-history-details" open>
          <summary>
            <span>Conversations</span>
            <span className="clarity-count" aria-label={`${threads.length} conversations`}>{threads.length}</span>
          </summary>
          <div className="thread-list" role="list">
            {threads.map((item) => (
              <button
                className="chat-thread"
                key={item.conversation_id}
                disabled={busy}
                aria-current={thread?.conversation_id === item.conversation_id ? "page" : undefined}
                onClick={() => void open(item.conversation_id)}
                type="button"
              >
                {item.title}
              </button>
            ))}
          </div>
          {!threads.length && <p className="fine">Your conversations will appear here.</p>}
          {hasMore && (
            <button
              type="button"
              onClick={() => void list(threads.length).catch((e) => {
                const detail = describeError(e);
                setError(detail.message);
                setErrorCode(detail.code || "");
              })}
              disabled={busy}
            >
              More conversations
            </button>
          )}
        </details>
      </aside>

      <div className="chat-main">
        {thread && (
          <details className="clarity-settings">
            <summary>Conversation settings</summary>
            <div className="clarity-settings-body">
              <Field label="Conversation name" value={title} onChange={setTitle} />
              <div className="clarity-settings-actions">
                <button type="button" disabled={busy} onClick={() => void rename()}>Rename</button>
                <button type="button" disabled={busy} onClick={() => void remove()}><Trash2 size={15} /> Delete conversation</button>
              </div>
            </div>
          </details>
        )}

        <div className="chat-context" aria-label="Question context">
          <span>{start || "Choose dates"} → {end}</span>
          <span>{clinic || "All clinics"}</span>
          {budgetIds.map((id) => (
            <span key={id}>{plans.find((p) => p.budget_id === id)?.name || "Attached saved plan"}</span>
          ))}
        </div>

        <details className="chat-attachments">
          <summary>Attach saved plans or select clinic</summary>
          <div className="clarity-attachments-body">
            <ClinicSelect value={clinic} onChange={setClinic} />
            {config.simulation_access && (
              <>
                <Select
                  label="Attach saved plan"
                  value=""
                  onChange={(id) => id && setBudgetIds((ids) => ids.includes(id) ? ids : [...ids, id].slice(0, 3))}
                  options={[["", "Choose a plan"], ...plans.map((p) => [p.budget_id, p.name] as [string, string])]}
                />
                {budgetIds.map((id) => (
                  <button key={id} type="button" onClick={() => setBudgetIds((ids) => ids.filter((x) => x !== id))}>
                    Detach {plans.find((p) => p.budget_id === id)?.name || "plan"}
                  </button>
                ))}
              </>
            )}
          </div>
        </details>

        {error && (
          <Notice error>
            <span>{errorCode && RESPONSE_LABELS[errorCode] ? `${RESPONSE_LABELS[errorCode]}: ` : ""}{error}</span>
            {thread && errorCode === "conversation_conflict" && (
              <button type="button" disabled={busy} onClick={() => void open(thread.conversation_id)}>Reopen conversation</button>
            )}
          </Notice>
        )}

        <div
          className="chat-messages clarity-messages"
          aria-label="Conversation messages"
          ref={messagesRef}
          onScroll={(event) => {
            const element = event.currentTarget;
            followLatest.current = element.scrollHeight - element.scrollTop - element.clientHeight < 160;
          }}
        >
          {!hasTurns && (
            <Card>
              <MessageSquare size={28} />
              <h2>What would you like to understand?</h2>
              <p>Explore your revenue, compare saved plans, or test a financial change.</p>
              <div className="chat-suggestions">
                {["Show monthly revenue and expenses", "Compare my attached scenarios", "What should I review in these financial results?"].map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => { setQuestion(suggestion); setPending(null); }}>{suggestion}</button>
                ))}
              </div>
            </Card>
          )}
          {turns.map((item: Row, index: number) => (
            <TurnView
              key={item.turn_id}
              turn={item}
              latest={index === turns.length - 1}
              diagnostics={!!config.diagnostics_enabled}
              local={localTurns.some((local) => local.turn_id === item.turn_id) && !thread?.turns?.some((saved: Row) => saved.turn_id === item.turn_id)}
              onRetry={() => void ask({ turn_id: item.turn_id, question: item.question, context: item.context })}
              onFreshAttempt={() => freshAttempt(item)}
              onDraft={onDraft}
              busy={busy}
            />
          ))}
          {busy && (
            <p className="clarity-processing" role="status" aria-live="polite">
              Clarity is checking your recorded data. Local models can take up to five minutes.
            </p>
          )}
        </div>

        <div className="chat-composer clarity-composer">
          <form
            aria-label="Ask Clarity"
            onSubmit={(event) => {
              event.preventDefault();
              void ask();
            }}
          >
            <label htmlFor="clarity-question">
              <span className="sr-only">Your financial question</span>
              <textarea
                id="clarity-question"
                required
                maxLength={2000}
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  setPending(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="Ask a question or follow up…"
                disabled={busy}
                aria-describedby="clarity-question-help"
              />
            </label>
            <div className="clarity-composer-actions">
              <span id="clarity-question-help" className="fine">{question.length}/2000 · Enter to send, Shift+Enter for a new line</span>
              <button className="primary" type="submit" disabled={busy || !start || !end || (!question.trim() && !pending)}>
                <Send size={17} /> {pending && !busy ? "Retry send" : "Ask Clarity"}
              </button>
            </div>
          </form>
          <details className="fine clarity-disclosure">
            <summary>Data processing</summary>
            {config.disclosure} Saved conversations and attached scenario context are included. Do not enter patient identifiers.
          </details>
        </div>

        {config.diagnostics_enabled && (
          <Card title="Development diagnostics">
            <p>{config.provider_name} · {config.model}</p>
            {config.cost_report_access && (
              <button type="button" onClick={() => void api(`/questions/costs?start=${start}&end=${end}`).then(setCosts).catch((e) => {
                const detail = describeError(e);
                setError(detail.message);
                setErrorCode(detail.code || "");
              })}>View model usage &amp; costs</button>
            )}
            {costs && <Table rows={costs.rows} />}
          </Card>
        )}
      </div>
    </div>
  );
}

function displayedTurns(thread: Row | null, localTurns: LocalTurn[]) {
  const saved = (thread?.turns || []) as Row[];
  const savedIds = new Set(saved.map((turn) => turn.turn_id));
  const entries = saved.map((turn, index) => ({
    turn,
    position: Number(turn.position) || index + 1,
    order: index,
  }));
  localTurns.forEach((turn, index) => {
    if (!savedIds.has(turn.turn_id)) {
      // A request can fail after the server accepted it but before the
      // response reaches the browser. If a later local send receives the same
      // server position, the earlier visible local turn must stay first.
      entries.push({ turn, position: turn.position, order: -localTurns.length + index });
    }
  });
  return entries
    .sort((a, b) => a.position - b.position || a.order - b.order)
    .map(({ turn }) => turn);
}

function TurnView({
  turn,
  latest,
  diagnostics,
  local,
  onRetry,
  onFreshAttempt,
  onDraft,
  busy,
}: {
  turn: Row;
  latest: boolean;
  diagnostics: boolean;
  local: boolean;
  onRetry: () => void;
  onFreshAttempt: () => void;
  onDraft?: (draft: Row) => void;
  busy: boolean;
}) {
  const failed = local && turn.status === "failed";
  const running = turn.status === "running" || (local && !failed);
  return (
    <div className="clarity-turn" data-latest-turn={latest ? "true" : undefined}>
      <article className="chat-message user clarity-user-bubble" aria-label="Your question">
        <span className="clarity-speaker">You</span>
        <p>{turn.question}</p>
        <div className="chat-context clarity-turn-context"><small>{turn.context.start} – {turn.context.end} · {turn.context.clinic_location || "All clinics"}</small></div>
      </article>
      {running && (
        <article className="chat-message assistant clarity-assistant-bubble clarity-pending" aria-label="Clarity reply pending">
          <span className="clarity-speaker">Clarity</span>
          <p role="status" aria-live="polite"><span className="clarity-pulse" aria-hidden="true" /> Reply is processing…</p>
          {turn.status === "running" && (
            <div className="clarity-turn-actions">
              <button type="button" disabled={busy} onClick={onRetry}>Check reply</button>
              <span className="fine">An interrupted reply can be retried after six minutes.</span>
            </div>
          )}
        </article>
      )}
      {failed && (
        <article className="chat-message assistant clarity-assistant-bubble clarity-failed" aria-label="Clarity reply failed">
          <span className="clarity-speaker">Clarity</span>
          <p role="alert">{turn.local_error || "The reply could not be completed."}</p>
          <button type="button" disabled={busy} onClick={onRetry}>Retry send</button>
        </article>
      )}
      {!running && !failed && (
        <Reply value={turn.response} diagnostics={diagnostics} onDraft={onDraft} onFreshAttempt={onFreshAttempt} turn={turn} busy={busy} />
      )}
    </div>
  );
}

function Reply({
  value,
  diagnostics,
  onDraft,
  onFreshAttempt,
  turn,
  busy,
}: {
  value: Row;
  diagnostics: boolean;
  onDraft?: (draft: Row) => void;
  onFreshAttempt: () => void;
  turn: Row;
  busy: boolean;
}) {
  if (!value) return null;
  const answerStatus = value.status === "answered";
  const label = responseLabel(value);
  return (
    <article className="chat-message assistant clarity-assistant-bubble" aria-label="Clarity reply">
      <div className="clarity-assistant-heading">
        <span className="clarity-speaker">Clarity</span>
        {label !== "Clarity" && <span className={`clarity-response-label clarity-response-${value.status}`}>{label}</span>}
      </div>
      <p className="answer-text">{value.answer}</p>
      {value.status === "unavailable" && (
        <div className="clarity-recovery">
          <p className="fine">This saved turn will remain unchanged. Start a fresh attempt when the model is available.</p>
          <button type="button" disabled={busy} onClick={onFreshAttempt}><RefreshCw size={15} /> Start a fresh attempt</button>
        </div>
      )}
      {answerStatus && (
        <>
          {value.tables?.map((table: Row, index: number) => (
            <section key={index}>
              <h3>{table.title}</h3>
              {table.chart !== "table" && table.rows?.length > 0 && table.keys?.length > 0 && (
                <Chart rows={table.rows} keys={table.keys} x={table.x} bar={table.chart === "bar"} currency={table.rows[0]?.currency} />
              )}
              <Table rows={table.rows || []} columns={table.columns} />
            </section>
          ))}
          {!!value.interpretation?.length && (
            <section className="inference">
              <h3>AI interpretation</h3>
              {value.interpretation.map((item: Row, index: number) => (
                <div key={index}>
                  <p>{item.text}</p>
                  <Evidence value={(value.facts || []).filter((fact: Row) => item.evidence?.includes(fact.id))} label="Supporting values" />
                </div>
              ))}
            </section>
          )}
          {!!value.recommendations?.length && (
            <section className="inference">
              <h3>Considerations, based on these results</h3>
              {value.recommendations.map((item: Row, index: number) => (
                <div key={index}>
                  <p>{item.text}</p>
                  <Evidence value={(value.facts || []).filter((fact: Row) => item.evidence?.includes(fact.id))} label="Supporting values" />
                </div>
              ))}
            </section>
          )}
          {value.narration_unavailable && <p className="fine">The calculations are available; AI interpretation was unavailable or could not be verified.</p>}
          {value.forecast && (
            <details>
              <summary>Forecast basis and validation</summary>
              <p>{value.forecast.basis}</p>
              <Table rows={[{ method: value.forecast.method, history_months: value.forecast.history_months, validation_mae: value.forecast.validation_mae, benchmark_mae: value.forecast.benchmark_mae }]} />
            </details>
          )}
          {value.draft && (
            <div className="baseline-review">
              <h3>Proposed plan · not applied</h3>
              <Evidence value={value.draft.changes} label="Review proposed changes" />
              <button className="primary" disabled={!onDraft} onClick={() => onDraft?.(value.draft)} type="button">Open as a new plan</button>
            </div>
          )}
          <div className="chat-evidence">
            {value.sources?.map((source: Row, index: number) => (
              <p key={index}>{source.kind === "saved_plan" ? `${source.name} · saved revision ${source.revision}` : `Recorded data · ${source.start} – ${source.end} · ${source.clinic_location || "All clinics"}`}</p>
            ))}
            {value.as_of && <small>Answered {value.as_of.slice(0, 16).replace("T", " ")} UTC. Saved answers retain the values used at the time.</small>}
          </div>
        </>
      )}
      {value.status === "refused" && turn.context && <p className="fine">No data was changed. Review the request or choose a supported financial measure.</p>}
      {diagnostics && <Evidence value={{ sql: value.sql, parameters: value.parameters, data_revision: value.data_revision }} label="Query diagnostics" />}
    </article>
  );
}
