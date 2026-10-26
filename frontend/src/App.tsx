import { useEffect, useState } from 'react';
import {
  ArrowUpRight, Bot, BriefcaseBusiness, Check, ChevronRight, CircleHelp,
  Command, FileSpreadsheet, FolderKanban, Gem, LayoutDashboard, LockKeyhole, Pencil, Trash2,
  MessageSquareText, Plus, Search, Send, Settings2, Sparkles, WandSparkles,
  Workflow, Zap
} from 'lucide-react';

type Tab = 'home' | 'studio' | 'work' | 'projects' | 'profile';
type Message = { role: 'user' | 'assistant'; text: string };
type Project = { id: number; workspace_id: number; title: string; description: string; status: string };
type Conversation = { id: number; project_id: number | null; title: string; created_at: string; updated_at: string };

const tools = [
  { id: 'content', icon: WandSparkles, title: 'Контент-лаборатория', text: 'Посты, реклама и контент-планы', color: 'violet' },
  { id: 'sales', icon: MessageSquareText, title: 'Продажи и клиенты', text: 'Ответы, офферы и скрипты', color: 'cyan' },
  { id: 'docs', icon: FileSpreadsheet, title: 'Документы и данные', text: 'Отчёты и анализ таблиц', color: 'blue' },
  { id: 'tasks', icon: Workflow, title: 'Умные процессы', text: 'Задачи и автоматизации', color: 'pink' },
];

const prompts = [
  'Составь план продвижения на неделю',
  'Напиши продающий пост для моего продукта',
  'Подготовь ответ сложному клиенту',
];

declare global {
  interface Window {
    Telegram?: { WebApp?: { ready: () => void; expand: () => void; initData?: string; initDataUnsafe?: { user?: { id?: number; first_name?: string } }; colorScheme?: string } };
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('home');
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationBusy, setConversationBusy] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [editProjectTitle, setEditProjectTitle] = useState("");
  const [editProjectDescription, setEditProjectDescription] = useState("");
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');
    const [workspaces, setWorkspaces] = useState<{ id: number; name: string; description: string }[]>([]);
    const [projects, setProjects] = useState<Project[]>([]);
    const [newWorkspaceName, setNewWorkspaceName] = useState('');
    const [newWorkspaceDescription, setNewWorkspaceDescription] = useState('');
    const [newProjectTitle, setNewProjectTitle] = useState('');
    const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | null>(null);
    const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const firstName = window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Предприниматель';

  function contextStorageKey() {
    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    return 'bizora-ai-context-' + (userId ? String(userId) : 'anonymous');
  }

  function persistContext(projectId: number | null, selectedConversationId: number | null) {
    try {
      window.localStorage.setItem(contextStorageKey(), JSON.stringify({
        projectId, conversationId: selectedConversationId,
      }));
    } catch {
      // Storage can be unavailable in restricted WebViews; server history remains intact.
    }
  }

  async function loadConversation(conversation: Conversation | number) {
    const id = typeof conversation === 'number' ? conversation : conversation.id;
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    const response = await fetch(base + '/api/conversations/' + id + '/messages?limit=100', {
      headers: { 'X-Telegram-Init-Data': initData },
    });
    if (!response.ok) throw new Error('Не удалось загрузить сообщения диалога');
    const history = await response.json();
    setConversationId(id);
    persistContext(activeProjectId, id);
    setMessages((history.messages || []).map((item: { role: string; content: string }) => ({
      role: (item.role === 'user' ? 'user' : 'assistant') as Message['role'], text: item.content,
    })));
  }

  async function selectProject(projectId: number | null, preferredConversationId: number | null = null) {
    setActiveProjectId(projectId);
    setConversationId(null);
    setMessages([]);
    persistContext(projectId, null);
    const initData = window.Telegram?.WebApp?.initData || '';
    if (!initData) return;
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    try {
      const listUrl = projectId === null ? base + '/api/conversations?limit=50&unassigned=true' : base + '/api/projects/' + projectId + '/conversations?limit=50';
      const response = await fetch(listUrl, { headers: { 'X-Telegram-Init-Data': initData } });
      if (!response.ok) throw new Error('Не удалось загрузить историю проекта');
      const data = await response.json();
      const items: Conversation[] = data.conversations || [];
      setConversations(items);
      const selected = items.find(item => item.id === preferredConversationId) || items[0];
      if (selected) {
        await loadConversation(selected);
        persistContext(projectId, selected.id);
      } else {
        persistContext(projectId, null);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка загрузки контекста');
      if (projectId !== null) {
        setActiveProjectId(null); setConversationId(null); setConversations([]); setMessages([]);
        persistContext(null, null);
        void selectProject(null);
      }
    }
  }

  async function createConversation() {
    if (conversationBusy) return;
    setConversationBusy(true);
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    try {
      const response = await fetch(base + '/api/conversations', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
        body: JSON.stringify({ title: 'Новый диалог', ...(activeProjectId !== null ? { project_id: activeProjectId } : {}) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось создать диалог');
      const created: Conversation = data.conversation;
      setConversations(prev => [created, ...prev.filter(item => item.id !== created.id)]);
      setConversationId(created.id); persistContext(activeProjectId, created.id); setMessages([]); setTab('studio'); setNotice('Новый диалог создан');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка создания диалога');
    } finally { setConversationBusy(false); }
  }

  async function saveProjectEdit(projectId: number) {
    if (!editProjectTitle.trim() || workspaceBusy) return;
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    setWorkspaceBusy(true);
    try {
      const response = await fetch(base + '/api/projects/' + projectId, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
        body: JSON.stringify({ title: editProjectTitle, description: editProjectDescription }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось изменить проект');
      setEditingProjectId(null); setNotice('Проект обновлён'); await loadProjects();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка редактирования проекта');
    } finally { setWorkspaceBusy(false); }
  }

  async function deleteProject(project: Project) {
    if (workspaceBusy || !window.confirm('Удалить проект «' + project.title + '»? Для удаления в нём не должно быть диалогов.')) return;
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    setWorkspaceBusy(true);
    try {
      const response = await fetch(base + '/api/projects/' + project.id, { method: 'DELETE', headers: { 'X-Telegram-Init-Data': initData } });
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail || 'Не удалось удалить проект'); }
      if (activeProjectId === project.id) { setActiveProjectId(null); setConversationId(null); setConversations([]); setMessages([]); }
      setNotice('Проект удалён'); await loadProjects();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка удаления проекта');
    } finally { setWorkspaceBusy(false); }
  }

  async function loadProjects() {
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    const initData = window.Telegram?.WebApp?.initData || '';
    if (!initData) return;
    const headers = { 'X-Telegram-Init-Data': initData };
    const [workspaceResponse, projectResponse] = await Promise.all([
      fetch(base + '/api/workspaces', { headers }),
      fetch(base + '/api/projects', { headers }),
    ]);
    if (!workspaceResponse.ok || !projectResponse.ok) throw new Error('Не удалось загрузить проекты');
    const workspaceData = await workspaceResponse.json();
    const projectData = await projectResponse.json();
    setWorkspaces(workspaceData.workspaces || []);
    setProjects(projectData.projects || []);
    setActiveWorkspaceId((current) => current ?? workspaceData.workspaces?.[0]?.id ?? null);
  }

  async function createWorkspace(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newWorkspaceName.trim() || workspaceBusy) return;
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    setWorkspaceBusy(true);
    try {
      const response = await fetch(base + '/api/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
        body: JSON.stringify({ name: newWorkspaceName, description: newWorkspaceDescription }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось создать пространство');
      setNewWorkspaceName(''); setNewWorkspaceDescription('');
      setActiveWorkspaceId(data.workspace.id);
      setNotice('Рабочее пространство создано');
      await loadProjects();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка создания пространства');
    } finally { setWorkspaceBusy(false); }
  }

  async function createProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeWorkspaceId || !newProjectTitle.trim() || workspaceBusy) return;
    const initData = window.Telegram?.WebApp?.initData || '';
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    setWorkspaceBusy(true);
    try {
      const response = await fetch(base + '/api/workspaces/' + activeWorkspaceId + '/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
        body: JSON.stringify({ title: newProjectTitle }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось создать проект');
      setNewProjectTitle('');
      setNotice('Проект сохранён');
      await loadProjects();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Ошибка создания проекта');
    } finally { setWorkspaceBusy(false); }
  }
  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    fetch(base + '/api/health').then(r => {
      if (!r.ok) throw new Error('API unavailable');
      return r.json();
    }).then(() => setApiStatus('online')).catch(() => setApiStatus('offline'));
    const initData = window.Telegram?.WebApp?.initData || '';
    if (initData) {
      void loadProjects().catch(() => undefined);
      let savedContext: { projectId?: number | null; conversationId?: number | null } = {};
      try {
        const raw = window.localStorage.getItem(contextStorageKey());
        if (raw) savedContext = JSON.parse(raw);
      } catch {
        savedContext = {};
      }
      const savedProjectId = typeof savedContext.projectId === 'number' && savedContext.projectId > 0 ? savedContext.projectId : null;
      const savedConversationId = typeof savedContext.conversationId === 'number' && savedContext.conversationId > 0 ? savedContext.conversationId : null;
      void selectProject(savedProjectId, savedConversationId);
    }
  }, []);

  async function sendMessage(text = query) {
    const clean = text.trim();
    if (!clean || busy) return;
    setMessages(prev => [...prev, { role: 'user', text: clean }]);
    setQuery('');
    setTab('studio');
    setBusy(true);
    try {
      const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const initData = window.Telegram?.WebApp?.initData || '';
      if (!initData) {
        throw new Error('Открой BIZORA AI внутри Telegram, чтобы подтвердить аккаунт.');
      }
      const response = await fetch(base + '/api/chat/demo', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': initData,
        },
        body: JSON.stringify({
          message: clean,
          ...(conversationId ? { conversation_id: conversationId } : {}),
          ...(activeProjectId !== null ? { project_id: activeProjectId } : {}),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось выполнить запрос');
      if (typeof data.conversation_id === 'number') {
        setConversationId(data.conversation_id);
        persistContext(activeProjectId, data.conversation_id);
        setConversations(prev => {
          const existing = prev.find(item => item.id === data.conversation_id);
          const now = new Date().toISOString();
          const title = existing?.title && existing.title !== 'Новый диалог' ? existing.title : clean.slice(0, 80);
          return [{
            id: data.conversation_id, project_id: data.project_id ?? null, title,
            created_at: existing?.created_at || now, updated_at: now,
          }, ...prev.filter(item => item.id !== data.conversation_id)];
        });
      }
      setMessages(prev => [...prev, { role: 'assistant', text: data.reply }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось выполнить запрос';
      setMessages(prev => [...prev, { role: 'assistant', text: message }]);
    } finally {
      setBusy(false);
    }
  }

  function openTool(id: string) {
    const tool = tools.find(item => item.id === id);
    setNotice(tool ? tool.title + ' — модуль запланирован. Подключим его в следующих этапах, не будем имитировать готовую функцию.' : 'Этот модуль появится в следующем этапе.');
    window.setTimeout(() => setNotice(''), 3500);
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" /><div className="ambient ambient-two" />
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Command size={20} /></div><div><div className="brand-name">BIZORA<span> AI</span></div><div className="brand-caption">BUSINESS OPERATING SYSTEM</div></div></div>
        <button className="icon-button" aria-label="Настройки" onClick={() => setTab('profile')}><Settings2 size={19} /></button>
      </header>

      <main>
        {tab === 'home' && <>
          <section className="welcome">
            <div className="eyebrow"><span className="live-dot" /> YOUR AI WORKSPACE</div>
            <h1>Добро пожаловать,<br /><span>{firstName}.</span></h1>
            <p>Твой бизнес. Твои идеи. Один интеллектуальный центр.</p>
            <div className="hero-orb"><div className="orb-core"><Sparkles size={31} /></div><div className="orbit orbit-a" /><div className="orbit orbit-b" /><span className="orb-tag tag-a">THINK</span><span className="orb-tag tag-b">CREATE</span><span className="orb-tag tag-c">GROW</span></div>
            <button className="primary-button" onClick={() => setTab('studio')}><Sparkles size={17} /> Открыть AI Studio <ArrowUpRight size={17} /></button>
          </section>

          <section className="stats-grid">
            <div className="stat-card"><div className="stat-icon purple"><Zap size={17} /></div><div className="stat-label">AI-кредиты</div><div className="stat-value">Демо</div><div className="stat-foot">Лимиты подключим на backend</div></div>
            <div className="stat-card"><div className="stat-icon mint"><Gem size={17} /></div><div className="stat-label">Тариф</div><div className="stat-value">START</div><div className="stat-foot">Owner-доступ добавим сервером</div></div>
          </section>

          <section className="section-block"><div className="section-heading"><div><div className="eyebrow">WORK SMARTER</div><h2>Твой набор инструментов</h2></div><button className="text-button" onClick={() => setTab('work')}>Все <ChevronRight size={16} /></button></div>
            <div className="tool-grid">{tools.map(tool => { const Icon = tool.icon; return <button className="tool-card" key={tool.id} onClick={() => openTool(tool.id)}><div className={'tool-icon ' + tool.color}><Icon size={20} /></div><strong>{tool.title}</strong><span>{tool.text}</span><ArrowUpRight className="tool-arrow" size={16} /></button>; })}</div>
          </section>
          <section className="section-block"><div className="section-heading"><div><div className="eyebrow">QUICK START</div><h2>Начни с идеи</h2></div></div><div className="prompt-list">{prompts.map(prompt => <button key={prompt} className="prompt-row" onClick={() => sendMessage(prompt)}><span>{prompt}</span><ChevronRight size={17} /></button>)}</div></section>
          <div className="status-line"><span className={'status-dot ' + apiStatus} /> {apiStatus === 'online' ? 'Backend доступен' : apiStatus === 'offline' ? 'Backend ещё не подключён' : 'Проверяем соединение'} <span className="status-separator">·</span> MVP Preview</div>
        </>}

        {tab === 'studio' && <section className="studio-page"><div className="eyebrow"><Sparkles size={13} /> YOUR AI COPILOT</div><h1>AI <span>Studio</span></h1><p className="muted">Преврати задачу в готовый результат.</p>
          <label className="project-context-label">Контекст диалога
            <select value={activeProjectId ?? ''} onChange={e => { void selectProject(e.target.value ? Number(e.target.value) : null); }}>
              <option value="">Общий чат — без проекта</option>
              {projects.map(project => <option key={project.id} value={project.id}>{project.title}</option>)}
            </select>
          </label>
          <div className="conversation-toolbar"><strong>Диалоги {activeProjectId !== null ? 'проекта' : 'общие'}</strong><button className="new-conversation-button" onClick={() => void createConversation()} disabled={conversationBusy}><Plus size={15} /> Новый диалог</button></div>
          {conversations.length > 0 && <div className="conversation-list">{conversations.map(item => <button key={item.id} className={conversationId === item.id ? 'conversation-row selected' : 'conversation-row'} onClick={() => { void loadConversation(item).catch(error => setNotice(error instanceof Error ? error.message : 'Ошибка загрузки')); }}><MessageSquareText size={15} /><span>{item.title || 'Новый диалог'}</span>{conversationId === item.id && <Check size={14} />}</button>)}</div>}
          <div className="chat-window">{messages.length === 0 ? <div className="empty-chat"><div className="empty-orb"><Bot size={27} /></div><h3>Что создаём сегодня?</h3><p>Опиши задачу или выбери готовый сценарий.</p>{prompts.map(p => <button className="suggestion" key={p} onClick={() => sendMessage(p)}>{p}<ArrowUpRight size={15} /></button>)}</div> : messages.map((m, i) => <div className={'message ' + m.role} key={i}><div className="message-role">{m.role === 'user' ? 'ТЫ' : 'BIZORA AI'}</div><div>{m.text}</div></div>)}{busy && <div className="message assistant"><div className="message-role">BIZORA AI</div><div className="typing"><i /><i /><i /></div></div>}</div>
          <form className="composer" onSubmit={e => { e.preventDefault(); void sendMessage(); }}><textarea value={query} onChange={e => setQuery(e.target.value)} placeholder="Напиши, что нужно сделать..." rows={2} /><div className="composer-bottom"><span><LockKeyhole size={12} /> Приватный рабочий контекст</span><button className="send-button" type="submit" disabled={!query.trim() || busy} aria-label="Отправить"><Send size={17} /></button></div></form>
          <p className="small-note">Пока работает демонстрационный режим. Подключение реальной AI-модели — следующий этап.</p>
        </section>}

        {tab === 'work' && <section className="page-section"><div className="eyebrow">BUSINESS TOOLKIT</div><h1>Рабочие <span>инструменты</span></h1><p className="muted">Восемь направлений. Один рабочий центр.</p>{tools.map(t => { const Icon = t.icon; return <button className="wide-tool" key={t.id} onClick={() => openTool(t.id)}><div className={'tool-icon ' + t.color}><Icon size={20} /></div><div className="wide-tool-copy"><strong>{t.title}</strong><span>{t.text}</span></div><ChevronRight size={18} /></button>; })}<div className="coming-card"><CircleHelp size={18} /><div><strong>Новые модули в разработке</strong><p>CRM, исследования, документы и автоматизации добавим поэтапно.</p></div></div></section>}

        {tab === 'projects' && <section className="page-section"><div className="eyebrow">YOUR WORKSPACE</div><h1>Твои <span>проекты</span></h1><p className="muted">Создавай рабочие пространства и собирай проекты бизнеса в одном месте.</p>
          <form className="workspace-form" onSubmit={createWorkspace}>
            <strong>Новое рабочее пространство</strong>
            <input value={newWorkspaceName} onChange={e => setNewWorkspaceName(e.target.value)} placeholder="Например, Мой бизнес" maxLength={120} required />
            <input value={newWorkspaceDescription} onChange={e => setNewWorkspaceDescription(e.target.value)} placeholder="Описание (необязательно)" maxLength={2000} />
            <button className="primary-button" type="submit" disabled={workspaceBusy || !newWorkspaceName.trim()}><Plus size={16} /> Создать пространство</button>
          </form>
          {workspaces.length === 0 ? <div className="empty-projects"><div className="empty-orb"><FolderKanban size={25} /></div><h3>Пока нет пространств</h3><p>Создай первое пространство — оно будет сохранено в базе данных и доступно только твоему Telegram-аккаунту.</p></div> : <div className="workspace-list">{workspaces.map(workspace => <section className={activeWorkspaceId === workspace.id ? 'workspace-card selected' : 'workspace-card'} key={workspace.id}>
            <button className="workspace-heading" onClick={() => setActiveWorkspaceId(workspace.id)}><div className="tool-icon violet"><BriefcaseBusiness size={18} /></div><div className="wide-tool-copy"><strong>{workspace.name}</strong><span>{workspace.description || 'Рабочее пространство'} · {projects.filter(project => project.workspace_id === workspace.id).length} проектов</span></div><ChevronRight size={17} /></button>
            {activeWorkspaceId === workspace.id && <><form className="project-form" onSubmit={createProject}><input value={newProjectTitle} onChange={e => setNewProjectTitle(e.target.value)} placeholder="Название нового проекта" maxLength={160} required /><button type="submit" disabled={workspaceBusy || !newProjectTitle.trim()} aria-label="Создать проект"><Plus size={17} /></button></form><div className="project-list">{projects.filter(project => project.workspace_id === workspace.id).map(project => <div className="project-management-row" key={project.id}>
            {editingProjectId === project.id ? <form className="project-edit-form" onSubmit={e => { e.preventDefault(); void saveProjectEdit(project.id); }}><input value={editProjectTitle} onChange={e => setEditProjectTitle(e.target.value)} maxLength={160} required aria-label="Название проекта" /><input value={editProjectDescription} onChange={e => setEditProjectDescription(e.target.value)} maxLength={4000} placeholder="Описание" aria-label="Описание проекта" /><div><button type="submit" disabled={workspaceBusy || !editProjectTitle.trim()}><Check size={15} /> Сохранить</button><button type="button" onClick={() => setEditingProjectId(null)}>Отмена</button></div></form> : <><button className={activeProjectId === project.id ? 'project-row active-project-row' : 'project-row'} onClick={() => { void selectProject(project.id); setTab('studio'); }}><div className="project-mark"><FolderKanban size={16} /></div><div className="wide-tool-copy"><strong>{project.title}</strong><span>{project.description || 'Проект бизнеса'} · {project.status === 'active' ? 'Активный' : project.status}</span></div><span className="project-status" /></button><div className="project-actions"><button aria-label={'Редактировать ' + project.title} onClick={() => { setEditingProjectId(project.id); setEditProjectTitle(project.title); setEditProjectDescription(project.description); }}><Pencil size={14} /></button><button aria-label={'Удалить ' + project.title} onClick={() => void deleteProject(project)}><Trash2 size={14} /></button></div></>}
          </div>)}</div></>}
          </section>)}</div>}
        </section>}

        {tab === 'profile' && <section className="page-section"><div className="eyebrow">ACCOUNT & ACCESS</div><h1>Твой <span>профиль</span></h1><div className="profile-card"><div className="avatar">{firstName.slice(0, 1).toUpperCase()}</div><div><strong>{firstName}</strong><p>Telegram Mini App · Preview</p></div></div><div className="profile-row"><span><Gem size={17} /> Текущий тариф</span><strong>START</strong></div><div className="profile-row"><span><Zap size={17} /> AI-кредиты</span><strong>Демо</strong></div><div className="profile-row"><span><LockKeyhole size={17} /> Безопасность</span><strong>Серверный этап</strong></div><button className="wide-tool" onClick={() => setNotice('Настройки тарифа появятся после подключения серверной авторизации.')}><Gem size={19} /><div className="wide-tool-copy"><strong>Тарифы и доступ</strong><span>Управление подпиской и преимуществами</span></div><ChevronRight size={18} /></button></section>}
      </main>

      {notice && <div className="toast" role="status"><Check size={16} />{notice}</div>}
      <nav className="bottom-nav" aria-label="Основная навигация">
        {([{ id: 'home', label: 'Главная', icon: LayoutDashboard }, { id: 'studio', label: 'AI Studio', icon: Sparkles }, { id: 'work', label: 'Инструменты', icon: BriefcaseBusiness }, { id: 'projects', label: 'Проекты', icon: FolderKanban }, { id: 'profile', label: 'Профиль', icon: Search }] as const).map(item => { const Icon = item.icon; return <button key={item.id} className={tab === item.id ? 'nav-item active' : 'nav-item'} onClick={() => setTab(item.id)}><Icon size={19} /><span>{item.label}</span></button>; })}
      </nav>
    </div>
  );
}