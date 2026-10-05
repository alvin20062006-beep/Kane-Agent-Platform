"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiRequestError, setApiAccessToken, type Agent, type Conversation, type Message, type SendBody, type Turn } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import { useTurn } from "@/lib/use-turn";
import { AppRail } from "../app-rail";
import { AgentDirectory } from "../agent-directory";
import { SidebarNav } from "../sidebar-nav";
import { ChatPanel } from "./chat-panel";
import { Composer, defaultLoopDraft, type LoopDraft } from "./composer";
import { AgentSettings } from "./agent-settings";
import { WorkInspector } from "./work-inspector";
import { BrandMark, ErrorNotice, IconButton, Loading, Modal, Status, turnTitle } from "./ui";

type Dialog = { kind: "conversation" | "task" } | { kind: "branch"; message: Message } | { kind: "cancel"; turn: Turn } | { kind: "rename" | "delete"; conversation: Conversation };

export function ConversationWorkspace({ connectorEndpoint }: { connectorEndpoint: string }) {
  const t = useT();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [managedAgentId, setManagedAgentId] = useState<string | null>(null);
  const [disconnectRequested, setDisconnectRequested] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedTurn, setSelectedTurn] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<unknown>(null);
  const [factsError, setFactsError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [factsLoading, setFactsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarMode, setSidebarMode] = useState<"agent" | "recent">("agent");
  const [agentDirectoryOpen, setAgentDirectoryOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [agentPanel, setAgentPanel] = useState<"settings" | "external" | "kanaloa" | null>(null);
  const [loopDrafts, setLoopDrafts] = useState<Record<string, LoopDraft>>({});
  const [name, setName] = useState("");
  const [newAgent, setNewAgent] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [authDismissed, setAuthDismissed] = useState(false);
  const [reply, setReply] = useState<Message | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [narrow, setNarrow] = useState(false);
  const draftKey = `${selectedId}:${selectedTurn ?? "initial"}`;
  const currentConversation = useRef(selectedId);
  currentConversation.current = selectedId;
  const { detail, messages, connection, error: streamError, refresh: refreshTurn } = useTurn(selectedId, selectedTurn);
  const displayAgents = agents.map(item => ({ ...item, display_name: item.display_name || (item.agent_id === "kanaloa" ? "Kanaloa" : item.agent_id) }));
  const agent = displayAgents.find(item => item.agent_id === (conversation?.bound_agent_id ?? selectedAgentId));
  const visibleConversations = sidebarMode === "recent"
    ? [...conversations].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    : selectedAgentId ? conversations.filter(item => item.bound_agent_id === selectedAgentId) : conversations;
  const selectedFact = detail?.turn_id === selectedTurn ? detail : null;
  const projectedTurns = turns.map(turn => selectedFact && turn.turn_id === selectedFact.turn_id ? selectedFact : turn);

  function openRename(agentId: string) {
    setDisconnectRequested(false);
    setManagedAgentId(agentId);
    setAgentPanel(agentId === "kanaloa" ? "kanaloa" : "settings");
  }

  const refreshList = useCallback(async (signal?: AbortSignal) => {
    try {
      const [items, registered] = await Promise.all([api.conversations(signal), api.agents(signal)]);
      if (signal?.aborted) return;
      setConversations(items); setAgents(registered); setListError(null);
      return items;
    } catch (error) { if (!signal?.aborted) setListError(error); }
    finally { if (!signal?.aborted) setListLoading(false); }
  }, []);

  const refreshFacts = useCallback(async (cid: string, signal?: AbortSignal) => {
    const [conv, items] = await Promise.all([api.conversation(cid, signal), api.turns(cid, signal)]);
    if (signal?.aborted || currentConversation.current !== cid) return;
    setConversation(conv); setTurns(items); setFactsError(null);
    setSelectedTurn(previous => previous && items.some(item => item.turn_id === previous) ? previous : conv.focus_turn_id);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams(window.location.search);
    if (window.innerWidth <= 700) { setSidebarOpen(false); setAgentDirectoryOpen(false); setInspectorOpen(false); }
    void refreshList(controller.signal).then(items => {
      if (controller.signal.aborted || !items) return;
      const requested = query.get("conversation");
      const requestedConversation = items.find(item => item.conversation_id === requested);
      if (requestedConversation) {
        setSelectedId(requestedConversation.conversation_id);
        setSelectedAgentId(requestedConversation.bound_agent_id);
        setSelectedTurn(query.get("turn"));
      } else if (items.length) {
        setSelectedId(items[0].conversation_id);
        setSelectedAgentId(items[0].bound_agent_id);
      }
    });
    return () => controller.abort();
  }, [refreshList]);

  useEffect(() => {
    if (!selectedAgentId && agents.length) {
      setSelectedAgentId(agents.find(item => item.status !== "unavailable")?.agent_id ?? agents[0].agent_id);
    }
  }, [agents, selectedAgentId]);

  useEffect(() => {
    if (selectedId) return;
    const controller = new AbortController();
    let refreshing = false;
    const interval = setInterval(async () => {
      if (refreshing) return;
      refreshing = true;
      try { await refreshList(controller.signal); }
      finally { refreshing = false; }
    }, 4000);
    return () => { controller.abort(); clearInterval(interval); };
  }, [selectedId, refreshList]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 700px)");
    const update = () => setNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!narrow || dialog || agentPanel) return;
    const drawer = document.getElementById(agentDirectoryOpen ? "agent-directory" : sidebarOpen ? "conversation-sidebar" : inspectorOpen && selectedId ? "work-inspector" : "");
    if (!drawer) return;
    const previous = document.activeElement as HTMLElement | null;
    const controls = () => Array.from(drawer.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')).filter(element => element.getClientRects().length);
    controls()[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0], last = items.at(-1);
      if (!drawer.contains(document.activeElement) || (!event.shiftKey && document.activeElement === last)) { event.preventDefault(); first?.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    };
    document.addEventListener("keydown", trap);
    return () => { document.removeEventListener("keydown", trap); if (previous?.isConnected) previous.focus(); };
  }, [narrow, agentDirectoryOpen, sidebarOpen, inspectorOpen, selectedId, dialog, agentPanel]);

  useEffect(() => {
    if (!selectedId) {
      setFactsError(null); setFactsLoading(false);
      window.history.replaceState(null, "", "/");
      return;
    }
    const controller = new AbortController();
    setFactsLoading(true); setConversation(null); setTurns([]); setReply(null); setActionError(null);
    void refreshFacts(selectedId, controller.signal).catch(error => { if (!controller.signal.aborted) setFactsError(error); }).finally(() => { if (!controller.signal.aborted) setFactsLoading(false); });
    let refreshing = false;
    const interval = setInterval(async () => {
      if (refreshing) return;
      refreshing = true;
      try { await refreshFacts(selectedId, controller.signal); await refreshList(controller.signal); }
      catch (error) { if (!controller.signal.aborted) setFactsError(error); }
      finally { refreshing = false; }
    }, 4000);
    return () => { controller.abort(); clearInterval(interval); };
  }, [selectedId, refreshFacts, refreshList]);

  useEffect(() => {
    if (!selectedId) return;
    const query = new URLSearchParams({ conversation: selectedId });
    if (selectedTurn) query.set("turn", selectedTurn);
    window.history.replaceState(null, "", `/?${query}`);
    setReply(null);
  }, [selectedId, selectedTurn]);

  useEffect(() => {
    const onEscape = (event: KeyboardEvent) => { if (event.key === "Escape" && window.innerWidth <= 700 && !dialog && !agentPanel) { setAgentDirectoryOpen(false); setSidebarOpen(false); setInspectorOpen(false); } };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [dialog, agentPanel]);

  function openDialog(next: Dialog) {
    setName(next.kind === "rename" ? next.conversation.title : "");
    setNewAgent(selectedAgentId && agents.some(item => item.agent_id === selectedAgentId && item.status !== "unavailable")
      ? selectedAgentId
      : agents.find(item => item.status !== "unavailable")?.agent_id ?? "");
    setActionError(null);
    setDialog(next);
  }
  function selectConversation(id: string) {
    setSidebarMode("agent");
    setSelectedId(id);
    setSelectedTurn(null);
    const target = conversations.find(item => item.conversation_id === id);
    if (target) setSelectedAgentId(target.bound_agent_id);
    if (window.innerWidth <= 700) { setAgentDirectoryOpen(false); setSidebarOpen(false); }
  }
  function selectAgent(agentId: string) {
    setSidebarMode("agent");
    setSelectedAgentId(agentId);
    const target = conversations.find(item => item.bound_agent_id === agentId);
    setSelectedTurn(null);
    setConversation(null);
    setTurns([]);
    setReply(null);
    if (target) setSelectedId(target.conversation_id);
    else {
      setSelectedId(null);
    }
    if (window.innerWidth <= 700) {
      setAgentDirectoryOpen(false);
      setSidebarOpen(true);
      setInspectorOpen(false);
    }
  }
  function refresh() { void refreshList(); if (selectedId) void refreshFacts(selectedId).catch(setFactsError); refreshTurn(); }

  async function action(work: () => Promise<void>) {
    if (busy) return false;
    setBusy(true); setActionError(null);
    const cid = selectedId;
    try { await work(); await refreshList(); if (cid && currentConversation.current === cid) await refreshFacts(cid); refreshTurn(); return true; }
    catch (error) { setActionError(error); if (cid && currentConversation.current === cid) await refreshFacts(cid).catch(setFactsError); refreshTurn(); return false; }
    finally { setBusy(false); }
  }

  async function submitDialog() {
    if (!dialog) return;
    const target = dialog;
    await action(async () => {
      if (target.kind === "conversation") {
        const created = await api.createConversation(name.trim() || t("newConversation"), newAgent);
        setSelectedAgentId(newAgent);
        selectConversation(created.conversation_id);
      } else if (target.kind === "rename") {
        await api.renameConversation(target.conversation.conversation_id, name.trim());
      } else if (target.kind === "delete") {
        await api.deleteConversation(target.conversation.conversation_id);
        setConversations(previous => previous.filter(item => item.conversation_id !== target.conversation.conversation_id));
        if (selectedId === target.conversation.conversation_id) {
          currentConversation.current = null;
          setSelectedId(null); setSelectedTurn(null); setConversation(null); setTurns([]); setReply(null);
        }
      } else if (target.kind === "task" && selectedId) {
        const turn = await api.newTask(selectedId, name.trim() || t("task"), selectedFact?.branch_id);
        setSelectedTurn(turn.turn_id);
      } else if (target.kind === "branch" && selectedId) {
        const branch = await api.branch(selectedId, target.message.message_id, name.trim() || t("branchTask"));
        await api.focus(selectedId, branch.initial_turn_id);
        setSelectedTurn(branch.initial_turn_id);
      } else if (target.kind === "cancel") await api.control(target.turn.turn_id, "cancel");
      setDialog(null);
    });
  }

  async function send(body: SendBody) {
    if (!selectedId) return false;
    return action(async () => { const result = await api.send(selectedId, body); setSelectedTurn(result.turn.turn_id); });
  }

  function control(kind: "cancel" | "resume" | "stop-loop") {
    if (!selectedFact) return;
    if (kind === "cancel") openDialog({ kind: "cancel", turn: selectedFact });
    else void action(async () => { await api.control(selectedFact.turn_id, kind); });
  }

  const isBackground = selectedTurn && conversation?.focus_turn_id && selectedTurn !== conversation.focus_turn_id;
  const connectionText = { loading: "syncing", live: "connected", settled: "saved", reconnecting: "reconnecting", disconnected: "disconnected" }[connection];
  const agentStatus = agent?.status === "ready" ? "agentReady" : agent?.status === "idle" ? "agentIdle" : agent?.status === "unavailable" ? "agentUnavailable" : agent?.status ?? "agentUnavailable";
  const modalTitle = dialog?.kind === "rename" ? t("renameConversation") : dialog?.kind === "delete" ? t("deleteConversation") : dialog?.kind === "conversation" ? t("newConversation") : dialog?.kind === "task" ? t("newTask") : dialog?.kind === "branch" ? t("createBranch") : t("cancelTitle");
  const needsApiToken = [listError, factsError, actionError, streamError].some(error => error instanceof ApiRequestError && error.status === 401);

  return <div className={`kane-app-frame workspace ${agentDirectoryOpen ? "agents-open" : ""} ${sidebarOpen ? "sidebar-open" : ""} ${inspectorOpen && selectedId ? "inspector-open" : ""}`}>
    {needsApiToken && !authDismissed && <Modal title={t("apiTokenTitle")} onClose={() => setAuthDismissed(true)}><form onSubmit={event => { event.preventDefault(); if (!apiToken.trim()) return; setApiAccessToken(apiToken); setApiToken(""); void refreshList(); if (selectedId) void refreshFacts(selectedId).catch(setFactsError); refreshTurn(); }}><label className="form-field">{t("apiTokenLabel")}<input type="password" autoComplete="off" value={apiToken} onChange={event => setApiToken(event.target.value)} required /></label><footer className="modal-actions"><button type="submit" className="button primary" disabled={!apiToken.trim()}>{t("apiTokenConnect")}</button></footer></form></Modal>}
    <a className="skip-link" href="#conversation-main">{t("conversations")}</a>
    <AppRail online={listLoading ? null : !listError} onChat={() => { setSidebarMode("agent"); setAgentDirectoryOpen(narrow); setSidebarOpen(false); setInspectorOpen(false); }} onRecents={() => { setSidebarMode("recent"); setAgentDirectoryOpen(false); setSidebarOpen(true); setInspectorOpen(false); }} onKanaloaSettings={() => setAgentPanel("kanaloa")} onSettings={() => setAgentPanel("settings")} />
    <aside id="agent-directory" className="workspace-agent-directory" role={narrow ? "dialog" : undefined} aria-modal={narrow && agentDirectoryOpen ? true : undefined} aria-label={t("agents")} inert={narrow && !agentDirectoryOpen}>
      <AgentDirectory agents={displayAgents} selectedId={selectedAgentId} loading={listLoading} error={listError} onSelect={selectAgent} onRename={openRename} onDisconnect={id => { openRename(id); setDisconnectRequested(true); }} onCreateBuiltin={() => { openDialog({ kind: "conversation" }); setNewAgent("kanaloa"); }} onAddExternal={() => { setManagedAgentId(null); setDisconnectRequested(false); setAgentPanel("external"); }} onRefresh={() => void refreshList()} onClose={() => setAgentDirectoryOpen(false)} />
    </aside>
    <aside id="conversation-sidebar" className="kane-sidebar-panel workspace-sidebar" role={narrow ? "dialog" : undefined} aria-modal={narrow && sidebarOpen ? true : undefined} aria-label={t("conversations")} inert={narrow && !sidebarOpen}>
      <SidebarNav mode={sidebarMode} conversations={visibleConversations} agents={displayAgents} selectedAgentId={selectedAgentId} selectedId={selectedId} loading={listLoading} error={listError} onSelect={selectConversation} onCreate={() => openDialog({ kind: "conversation" })} onRefresh={() => void refreshList()} onClose={() => setSidebarOpen(false)} onRename={conversation => openDialog({ kind: "rename", conversation })} onDelete={conversation => openDialog({ kind: "delete", conversation })} />
    </aside>
    <div className="workspace-body">
      <div className="workspace-content"><main id="conversation-main" className="conversation-main" tabIndex={-1}>
        <div className="workspace-selection">
          {needsApiToken && authDismissed && <button className="button secondary compact" onClick={() => setAuthDismissed(false)}>{t("apiTokenConnect")}</button>}
          <IconButton className="mobile-navigation" label={t("openConversations")} onClick={() => { setSidebarOpen(true); setAgentDirectoryOpen(false); }}>☰</IconButton>
          <label>{t("agent")}<select aria-label={t("selectAgent")} value={selectedAgentId ?? ""} disabled={listLoading || busy} onChange={event => selectAgent(event.target.value)}>{!selectedAgentId && <option value="">{t("emptyAgent")}</option>}{displayAgents.map(item => <option key={item.agent_id} value={item.agent_id}>{item.display_name} · {t(item.status === "ready" ? "agentReady" : item.status === "idle" ? "agentIdle" : "agentUnavailable")}</option>)}</select></label>
          {selectedId && <label>{t("currentTurn")}<select aria-label={t("currentTurn")} value={selectedTurn ?? ""} disabled={factsLoading || busy || !turns.length} onChange={event => setSelectedTurn(event.target.value || null)}>{!selectedTurn && <option value="">{t("noTurns")}</option>}{projectedTurns.map(turn => <option key={turn.turn_id} value={turn.turn_id}>{turnTitle(turn, t)} · {t(`status.${turn.status}`)}{turn.turn_id === conversation?.focus_turn_id ? ` · ${t("focus")}` : ""}</option>)}</select></label>}
          {selectedFact && <Status status={selectedFact.status} />}
        </div>
        {!selectedId ? <div className="workspace-welcome"><BrandMark /><span className="welcome-brand">Kane–Kanaloa</span><h1>{t("welcome")}</h1><p>{t("welcomeText")}</p>{listLoading ? <Loading /> : listError ? <ErrorNotice error={listError} onRetry={() => void refreshList()} /> : agents.some(item => item.status !== "unavailable") ? <button className="button primary" aria-label={t("start")} onClick={() => openDialog({ kind: "conversation" })}><span aria-hidden="true">＋</span>{t("start")}</button> : <p role="status">{t(agents.length ? "noAvailableAgents" : "noAgents")}</p>}</div> : <>
          <header className="conversation-header"><div className="conversation-heading"><h1>{agent?.agent_id === "kanaloa" ? "Kanaloa" : agent?.display_name || agent?.agent_id || t("loading")}</h1><div className="conversation-subtitle"><span className={`agent-availability ${agent?.status === "ready" ? "ready" : agent?.status === "unavailable" ? "unavailable" : "idle"}`}><span className="status-dot" />{t(agentStatus)}</span>{conversation?.title && <><span className="meta-separator">/</span><span className="current-task-name">{conversation.title}</span></>}{selectedFact && <><span className="meta-separator">/</span><span className="current-task-name">{turnTitle(selectedFact, t)}</span></>}</div></div><div className="conversation-header-actions"><span className={`stream-indicator connection-${connection}`} data-testid="stream-status" title={t(connectionText)}><span className="status-dot" />{t(connectionText)}</span><IconButton className="header-refresh" label={t("refresh")} onClick={refresh}>↻</IconButton><IconButton label={t("openWork")} aria-expanded={inspectorOpen} onClick={() => setInspectorOpen(value => !value)}>◧</IconButton></div></header>
          {selectedFact?.branch_id !== "main" && selectedFact && <div className="context-strip"><span aria-hidden="true">⑂</span><strong>{t("branchContext")}</strong><span>{selectedFact.branch_id.slice(-6)}</span><span className="context-description">{t("branchDetail")}</span></div>}
          {isBackground && <div className="context-strip background-context"><span>{t("inspecting")}</span><button className="text-button" disabled={busy} onClick={() => void action(async () => { if (selectedId && selectedTurn) await api.focus(selectedId, selectedTurn); })}>{t("focusTask")} →</button></div>}
          {Boolean(factsError) && <ErrorNotice error={factsError} onRetry={refresh} />}
          {Boolean(actionError) && !dialog && <ErrorNotice error={actionError} onRetry={refresh} action />}
          {factsLoading ? <Loading /> : <ChatPanel key={`chat:${draftKey}`} messages={messages} detail={selectedFact} turns={turns} agent={agent} connection={connection} error={streamError} busy={busy} onRefresh={refresh} onBranch={message => openDialog({ kind: "branch", message })} onReply={setReply} onPermission={(requestId, decision) => void action(async () => { if (selectedTurn) await api.permission(selectedTurn, requestId, decision); })} onResume={() => control("resume")} />}
          <Composer onNewTask={() => openDialog({ kind: "task" })} key={draftKey} agent={agent} turn={selectedFact} reply={reply} draft={drafts[draftKey] ?? ""} loopDraft={loopDrafts[draftKey] ?? defaultLoopDraft} onLoopChange={value => setLoopDrafts(previous => ({ ...previous, [draftKey]: value }))} onControl={control} onSettings={() => setAgentPanel(agent?.agent_id === "kanaloa" ? "kanaloa" : "settings")} onDraftChange={(value, expected) => setDrafts(previous => expected !== undefined && previous[draftKey] !== expected ? previous : { ...previous, [draftKey]: value })} busy={busy} disabled={!agent || agent.status === "unavailable" || factsLoading || Boolean(factsError)} onSend={send} onClearReply={() => setReply(null)} />
        </>}
      </main>
      {selectedId && <aside id="work-inspector" className="work-inspector" role={narrow ? "dialog" : undefined} aria-modal={narrow && inspectorOpen ? true : undefined} aria-label={t("workPanel")} inert={!inspectorOpen}><WorkInspector turns={projectedTurns} detail={selectedFact} agent={agent} focusId={conversation?.focus_turn_id ?? null} selectedId={selectedTurn} busy={busy} onFocus={turn => void action(async () => { if (selectedId) { await api.focus(selectedId, turn.turn_id); setSelectedTurn(turn.turn_id); } })} onInspect={turn => setSelectedTurn(turn.turn_id)} onNewTask={() => openDialog({ kind: "task" })} onControl={control} onClose={() => setInspectorOpen(false)} /></aside>}
      </div>
    </div>
    {((narrow && (agentDirectoryOpen || sidebarOpen)) || (inspectorOpen && selectedId)) && <button className="drawer-backdrop" aria-label={t("close")} onClick={() => { setAgentDirectoryOpen(false); setSidebarOpen(false); setInspectorOpen(false); }} />}
    {agentPanel && <AgentSettings connectorEndpoint={connectorEndpoint} key={`${agentPanel}:${managedAgentId}:${disconnectRequested}`} initialDisconnect={disconnectRequested} selectedAgentId={managedAgentId} onManage={openRename} mode={agentPanel} agents={agents} error={listError} onRefresh={() => void refreshList()} onClose={() => setAgentPanel(null)} onChoose={id => { setSelectedAgentId(id); setAgentPanel(null); openDialog({ kind: "conversation" }); setNewAgent(id); }} />}
    {dialog && (dialog.kind === "rename" || dialog.kind === "delete") && <Modal title={modalTitle} onClose={() => { if (!busy) setDialog(null); }}><form onSubmit={event => { event.preventDefault(); void submitDialog(); }}>{dialog.kind === "rename" ? <label className="form-field">{t("title")}<input autoFocus required maxLength={256} value={name} onChange={event => setName(event.target.value)} /></label> : <><strong>{dialog.conversation.title}</strong><p className="modal-description">{t("deleteConversationHint")}</p></>}{Boolean(actionError) && <ErrorNotice error={actionError} action />}<footer className="modal-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setDialog(null)}>{t("cancel")}</button><button type="submit" className={`button ${dialog.kind === "delete" ? "danger" : "primary"}`} disabled={busy || (dialog.kind === "rename" && !name.trim())}>{busy ? t("loading") : t(dialog.kind === "rename" ? "saveDisplayName" : "deleteConversation")}</button></footer></form></Modal>}
    {dialog && dialog.kind !== "rename" && dialog.kind !== "delete" && <Modal title={modalTitle} onClose={() => { if (!busy) setDialog(null); }}><form onSubmit={event => { event.preventDefault(); void submitDialog(); }}>
      {dialog.kind === "cancel" ? <p className="modal-description">{t("cancelHint")}</p> : <><label className="form-field">{t(dialog.kind === "conversation" ? "title" : dialog.kind === "task" ? "taskTitle" : "branchName")}<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder={t(dialog.kind === "conversation" ? "optionalTitle" : dialog.kind === "task" ? "taskPlaceholder" : "branchPlaceholder")} /></label>{dialog.kind === "conversation" && <label className="form-field">{t("agent")}<select aria-label={t("agent")} value={newAgent} onChange={event => setNewAgent(event.target.value)}>{agents.map(item => <option value={item.agent_id} key={item.agent_id} disabled={item.status === "unavailable"}>{item.agent_id === "kanaloa" ? "Kanaloa" : item.agent_id} · {item.status === "ready" ? t("agentReady") : item.status === "idle" ? t("agentIdle") : item.status}</option>)}</select></label>}{dialog.kind === "branch" && <><blockquote className="branch-preview">{dialog.message.content}</blockquote><p className="modal-description">{t("branchHint")}</p></>}{dialog.kind === "task" && <p className="modal-description">{t("newTaskHint")}{agent && !agent.supports_parallel_sessions && ` ${t("parallelUnavailable")}`}</p>}</>}
      {Boolean(actionError) && <ErrorNotice error={actionError} action />}
      <footer className="modal-actions"><button type="button" className="button secondary" onClick={() => setDialog(null)} disabled={busy}>{t(dialog.kind === "cancel" ? "keepWorking" : "cancel")}</button><button type="submit" className={`button ${dialog.kind === "cancel" ? "danger" : "primary"}`} disabled={busy || (dialog.kind === "conversation" && !newAgent)}>{busy ? t("loading") : t(dialog.kind === "conversation" ? "create" : dialog.kind === "task" ? "createTask" : dialog.kind === "branch" ? "createBranch" : "confirmCancel")}</button></footer>
    </form></Modal>}
  </div>;
}
