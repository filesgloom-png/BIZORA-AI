import { useEffect, useState } from 'react';
import {
  ArrowUpRight, Bot, BriefcaseBusiness, Check, ChevronRight, CircleHelp,
  Command, FileSpreadsheet, FolderKanban, Gem, LayoutDashboard, LockKeyhole,
  MessageSquareText, Plus, Search, Send, Settings2, Sparkles, WandSparkles,
  Workflow, Zap
} from 'lucide-react';

type Tab = 'home' | 'studio' | 'work' | 'projects' | 'profile';
type Message = { role: 'user' | 'assistant'; text: string };

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
    Telegram?: { WebApp?: { ready: () => void; expand: () => void; initData?: string; initDataUnsafe?: { user?: { first_name?: string } }; colorScheme?: string } };
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('home');
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const firstName = window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Предприниматель';

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
      fetch(base + '/api/conversations?limit=1', {
        headers: { 'X-Telegram-Init-Data': initData },
      }).then(r => r.ok ? r.json() : Promise.reject(new Error('History unavailable')))
        .then(async data => {
          const latest = data.conversations?.[0];
          if (!latest || typeof latest.id !== 'number') return;
          const historyResponse = await fetch(base + '/api/conversations/' + latest.id + '/messages?limit=100', {
            headers: { 'X-Telegram-Init-Data': initData },
          });
          if (!historyResponse.ok) return;
          const history = await historyResponse.json();
          setConversationId(latest.id);
          setMessages((history.messages || []).map((item: { role: string; content: string }) => ({
            role: (item.role === 'user' ? 'user' : 'assistant') as Message['role'],
            text: item.content,
          })));
        }).catch(() => undefined);
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
        body: JSON.stringify({ message: clean, ...(conversationId ? { conversation_id: conversationId } : {}) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Не удалось выполнить запрос');
      if (typeof data.conversation_id === 'number') setConversationId(data.conversation_id);
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
          <div className="chat-window">{messages.length === 0 ? <div className="empty-chat"><div className="empty-orb"><Bot size={27} /></div><h3>Что создаём сегодня?</h3><p>Опиши задачу или выбери готовый сценарий.</p>{prompts.map(p => <button className="suggestion" key={p} onClick={() => sendMessage(p)}>{p}<ArrowUpRight size={15} /></button>)}</div> : messages.map((m, i) => <div className={'message ' + m.role} key={i}><div className="message-role">{m.role === 'user' ? 'ТЫ' : 'BIZORA AI'}</div><div>{m.text}</div></div>)}{busy && <div className="message assistant"><div className="message-role">BIZORA AI</div><div className="typing"><i /><i /><i /></div></div>}</div>
          <form className="composer" onSubmit={e => { e.preventDefault(); void sendMessage(); }}><textarea value={query} onChange={e => setQuery(e.target.value)} placeholder="Напиши, что нужно сделать..." rows={2} /><div className="composer-bottom"><span><LockKeyhole size={12} /> Приватный рабочий контекст</span><button className="send-button" type="submit" disabled={!query.trim() || busy} aria-label="Отправить"><Send size={17} /></button></div></form>
          <p className="small-note">Пока работает демонстрационный режим. Подключение реальной AI-модели — следующий этап.</p>
        </section>}

        {tab === 'work' && <section className="page-section"><div className="eyebrow">BUSINESS TOOLKIT</div><h1>Рабочие <span>инструменты</span></h1><p className="muted">Восемь направлений. Один рабочий центр.</p>{tools.map(t => { const Icon = t.icon; return <button className="wide-tool" key={t.id} onClick={() => openTool(t.id)}><div className={'tool-icon ' + t.color}><Icon size={20} /></div><div className="wide-tool-copy"><strong>{t.title}</strong><span>{t.text}</span></div><ChevronRight size={18} /></button>; })}<div className="coming-card"><CircleHelp size={18} /><div><strong>Новые модули в разработке</strong><p>CRM, исследования, документы и автоматизации добавим поэтапно.</p></div></div></section>}

        {tab === 'projects' && <section className="page-section"><div className="eyebrow">YOUR WORKSPACE</div><h1>Твои <span>проекты</span></h1><p className="muted">Здесь будут храниться рабочие пространства и результаты AI.</p><div className="empty-projects"><div className="empty-orb"><FolderKanban size={25} /></div><h3>Начни с первого проекта</h3><p>Храни идеи, задачи и материалы бизнеса вместе.</p><button className="primary-button" onClick={() => setNotice('Создание проектов подключим после backend и базы данных.')}><Plus size={16} /> Новый проект</button></div></section>}

        {tab === 'profile' && <section className="page-section"><div className="eyebrow">ACCOUNT & ACCESS</div><h1>Твой <span>профиль</span></h1><div className="profile-card"><div className="avatar">{firstName.slice(0, 1).toUpperCase()}</div><div><strong>{firstName}</strong><p>Telegram Mini App · Preview</p></div></div><div className="profile-row"><span><Gem size={17} /> Текущий тариф</span><strong>START</strong></div><div className="profile-row"><span><Zap size={17} /> AI-кредиты</span><strong>Демо</strong></div><div className="profile-row"><span><LockKeyhole size={17} /> Безопасность</span><strong>Серверный этап</strong></div><button className="wide-tool" onClick={() => setNotice('Настройки тарифа появятся после подключения серверной авторизации.')}><Gem size={19} /><div className="wide-tool-copy"><strong>Тарифы и доступ</strong><span>Управление подпиской и преимуществами</span></div><ChevronRight size={18} /></button></section>}
      </main>

      {notice && <div className="toast" role="status"><Check size={16} />{notice}</div>}
      <nav className="bottom-nav" aria-label="Основная навигация">
        {([{ id: 'home', label: 'Главная', icon: LayoutDashboard }, { id: 'studio', label: 'AI Studio', icon: Sparkles }, { id: 'work', label: 'Инструменты', icon: BriefcaseBusiness }, { id: 'projects', label: 'Проекты', icon: FolderKanban }, { id: 'profile', label: 'Профиль', icon: Search }] as const).map(item => { const Icon = item.icon; return <button key={item.id} className={tab === item.id ? 'nav-item active' : 'nav-item'} onClick={() => setTab(item.id)}><Icon size={19} /><span>{item.label}</span></button>; })}
      </nav>
    </div>
  );
}