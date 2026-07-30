import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Send, PlusCircle, Database, MessageSquare, Edit2, Play, ChevronDown, Trash2, Cpu, Sparkles, Check } from 'lucide-react';

import './App.css';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';

const API_BASE = 'http://localhost:8000';
const SCHEMA_NAME = 'core_usage'; // Hardcoded for demo


function ChatChart({ spec, data }) {
  if (!spec || !data || data.length === 0) return null;

  // Hex-inspired chart palette
  const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];

  const renderChart = () => {
    switch (spec.type) {
      case 'bar':
        return (
          <BarChart data={data}>
            <XAxis dataKey={spec.x} stroke="#9ca3af" fontSize={12} />
            <YAxis stroke="#9ca3af" fontSize={12} />
            <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e5e7eb', color: '#111827' }} />
            <Legend />
            <Bar dataKey={spec.y} fill="#4f46e5" radius={[4, 4, 0, 0]} />
          </BarChart>
        );
      case 'line':
        return (
          <LineChart data={data}>
            <XAxis dataKey={spec.x} stroke="#9ca3af" fontSize={12} />
            <YAxis stroke="#9ca3af" fontSize={12} />
            <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e5e7eb', color: '#111827' }} />
            <Legend />
            <Line type="monotone" dataKey={spec.y} stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
          </LineChart>
        );
      case 'pie':
        return (
          <PieChart>
            <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e5e7eb', color: '#111827' }} />
            <Legend />
            <Pie data={data} dataKey={spec.y} nameKey={spec.x} cx="50%" cy="50%" outerRadius={120}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        );
      default:
        return null;
    }
  };

  return (
    <div className="chart-container">
      {spec.title && <h4 style={{ marginBottom: '1rem', color: '#111827', fontSize: '1.1rem' }}>{spec.title}</h4>}
      <div style={{ height: 350, width: '100%' }}>
        <ResponsiveContainer>
          {renderChart()}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DataTable({ data }) {
  if (!data || data.length === 0) return null;
  const columns = Object.keys(data[0]);
  
  return (
    <div className="data-table-container">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map(col => <th key={col}>{col}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={idx}>
              {columns.map(col => <td key={col}>{row[col]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SqlEditor({ initialSql, onRerun, disabled }) {
  const [isEditing, setIsEditing] = useState(false);
  const [sql, setSql] = useState(initialSql);

  // Update sql state if initialSql changes
  useEffect(() => {
    setSql(initialSql);
  }, [initialSql]);

  if (!isEditing) {
    return (
      <div className="sql-block-wrapper">
        <div className="sql-block">{sql}</div>
        {!disabled && (
          <button 
            className="edit-btn" 
            onClick={() => setIsEditing(true)}
            style={{ position: 'absolute', top: '0.75rem', right: '0.75rem', cursor: 'pointer' }}
            title="Edit & Rerun SQL"
          >
            <Edit2 size={16} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="sql-block-wrapper" style={{ margin: '1rem 0' }}>
      <textarea 
        value={sql}
        onChange={e => setSql(e.target.value)}
        style={{ width: '100%', minHeight: '120px', background: '#f8fafc', color: '#0f172a', fontFamily: 'var(--font-mono)', padding: '1rem', borderRadius: '6px', border: '2px solid #4f46e5', outline: 'none' }}
      />
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', justifyContent: 'flex-end' }}>
        <button onClick={() => setIsEditing(false)} style={{ background: 'transparent', border: '1px solid #d1d5db', color: '#4b5563', padding: '0.4rem 1rem', borderRadius: '6px', cursor: 'pointer', fontWeight: 500 }}>Cancel</button>
        <button onClick={() => { setIsEditing(false); onRerun(sql); }} style={{ background: '#4f46e5', border: 'none', color: 'white', padding: '0.4rem 1rem', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}>
          <Play size={14} /> Rerun
        </button>
      </div>
    </div>
  );
}

const AVAILABLE_MODELS = [
  { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite', badge: 'Primary', badgeBg: '#e0e7ff', badgeColor: '#3730a3', desc: '15 RPM | 250k TPM | 500 RPD (Fastest)' },
  { id: 'gemini-3-flash', name: 'Gemini 3 Flash', badge: 'Balanced', badgeBg: '#ecfdf5', badgeColor: '#065f46', desc: '5 RPM | 250k TPM | 20 RPD' },
  { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite', badge: 'Tertiary', badgeBg: '#fef3c7', badgeColor: '#92400e', desc: '10 RPM | 250k TPM | 20 RPD' },
  { id: 'qwen3.5-ollama', name: 'Qwen 3.5 (Local Ollama)', badge: 'Local 0-Cost', badgeBg: '#f3e8ff', badgeColor: '#6b21a8', desc: 'Local inference on http://localhost:11434' },
];

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activeMessageId, setActiveMessageId] = useState(null);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSessionsMenu, setShowSessionsMenu] = useState(false);
  const [emptyTables, setEmptyTables] = useState([]);
  const [showEmptyTables, setShowEmptyTables] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0]);
  const [showModelsMenu, setShowModelsMenu] = useState(false);

  
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchSessions();
    fetchEmptyTables();
    fetchSuggestedQuestions();
  }, []);

  const fetchEmptyTables = async () => {
    try {
      const res = await axios.get(`${API_BASE}/schema/empty_tables?schema_name=${SCHEMA_NAME}`);
      setEmptyTables(res.data.empty_tables || []);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchSuggestedQuestions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/suggested_questions?schema_name=${SCHEMA_NAME}`);
      if (res.data.status === 'success') {
        setSuggestedQuestions(res.data.questions || []);
      }
    } catch (e) {
      console.error("Error fetching suggested questions:", e);
    }
  };

  useEffect(() => {
    if (currentSessionId) {
      fetchMessages(currentSessionId);
    }
  }, [currentSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const fetchSessions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/sessions`);
      if (res.data && res.data.length > 0) {
        setSessions(res.data);
        if (!currentSessionId) {
          setCurrentSessionId(res.data[0].id);
        }
      } else {
        createSession();
      }
    } catch (error) {
      console.error("Error fetching sessions from API:", error);
      // Fallback local session if server starting
      const fallbackId = 'sess_' + Date.now();
      const fallbackSession = { id: fallbackId, title: "New Analytics Chat" };
      setSessions([fallbackSession]);
      setCurrentSessionId(fallbackId);
    }
  };

  const createSession = async () => {
    try {
      const res = await axios.post(`${API_BASE}/sessions`, { title: "New Analytics Chat" });
      const newSid = res.data.session_id;
      setCurrentSessionId(newSid);
      setMessages([]);
      setActiveMessageId(null);
      fetchSessions();
      setShowSessionsMenu(false);
    } catch (error) {
      console.error("Error creating session via API:", error);
      const fallbackId = 'sess_' + Date.now();
      const fallbackSession = { id: fallbackId, title: "New Analytics Chat" };
      setSessions(prev => [fallbackSession, ...prev]);
      setCurrentSessionId(fallbackId);
      setMessages([]);
      setActiveMessageId(null);
      setShowSessionsMenu(false);
    }
  };


  const deleteSession = async (sid, e) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this chat?')) return;
    try {
      await axios.delete(`${API_BASE}/sessions/${sid}`);
      if (currentSessionId === sid) {
        setCurrentSessionId(null);
        setMessages([]);
        setActiveMessageId(null);
      }
      fetchSessions();
    } catch (error) {
      console.error("Error deleting session:", error);
    }
  };

  const fetchMessages = async (sid) => {
    try {
      const res = await axios.get(`${API_BASE}/sessions/${sid}/messages`);
      const formatted = res.data.map(m => {
        let isArray = false;
        let parsedData = null;
        try {
          if (m.role === 'assistant' && m.content.startsWith('[')) {
             parsedData = JSON.parse(m.content);
             isArray = true;
          }
        } catch(e) {}
        return { ...m, isArray, parsedData };
      });
      setMessages(formatted);
      
      // Auto-select the last assistant message that has data
      const lastDataMsg = [...formatted].reverse().find(m => m.role === 'assistant' && (m.sql || m.parsedData));
      if (lastDataMsg) {
        setActiveMessageId(lastDataMsg.id);
      } else {
        setActiveMessageId(null);
      }
    } catch (error) {
      console.error("Error fetching messages:", error);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    let activeSid = currentSessionId;
    if (!activeSid) {
      try {
        const res = await axios.post(`${API_BASE}/sessions`, { title: "New Analytics Chat" });
        activeSid = res.data.session_id;
        setCurrentSessionId(activeSid);
        fetchSessions();
      } catch (err) {
        console.error("Error creating session on the fly:", err);
        activeSid = 'sess_' + Date.now();
        setCurrentSessionId(activeSid);
      }

    }

    const query = inputValue;
    setInputValue('');
    const userMsgId = 'tmp_' + Date.now();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: query }]);
    setIsLoading(true);

    try {
      const res = await axios.post(`${API_BASE}/query`, {
        session_id: activeSid,
        question: query,
        schema_name: SCHEMA_NAME,
        preferred_model: selectedModel.id
      });

      
      let parsedData = null;
      try {
        parsedData = JSON.parse(res.data.result);
      } catch(e) {}

      const newMsg = {
        id: res.data.message_id,
        role: 'assistant',
        content: res.data.nl_response,
        sql: res.data.sql,
        chart_spec: res.data.chart_spec,
        parsedData: parsedData,
        empty_tables: res.data.empty_tables,
        follow_ups: res.data.follow_ups
      };

      setMessages(prev => [...prev, newMsg]);
      setActiveMessageId(res.data.message_id);
    } catch (error) {
      console.error("Query error:", error);
      setMessages(prev => [...prev, { 
        id: 'err_' + Date.now(), 
        role: 'assistant', 
        content: error.response?.data?.detail || "An error occurred during query execution." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRerun = async (newSql, originalMsgId, question) => {
    if (!currentSessionId) return;
    setIsLoading(true);
    const userMsgId = 'tmp_rerun_' + Date.now();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: `[Rerun] ${newSql}` }]);

    try {
      const res = await axios.post(`${API_BASE}/query/rerun`, {
        session_id: currentSessionId,
        question: question || "Rerun SQL query",
        schema_name: SCHEMA_NAME,
        new_sql: newSql
      });
      
      let parsedData = null;
      try {
        parsedData = JSON.parse(res.data.result);
      } catch(e) {}

      const newMsg = {
        id: res.data.message_id,
        role: 'assistant',
        content: res.data.nl_response,
        sql: res.data.sql,
        chart_spec: res.data.chart_spec,
        parsedData: parsedData,
        empty_tables: res.data.empty_tables,
        follow_ups: res.data.follow_ups
      };

      setMessages(prev => [...prev, newMsg]);
      setActiveMessageId(res.data.message_id);
    } catch (error) {
      console.error("Rerun error:", error);
      setMessages(prev => [...prev, { 
        id: 'err_rerun_' + Date.now(), 
        role: 'assistant', 
        content: error.response?.data?.detail || "An error occurred during rerun execution." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Get active message data for left canvas
  const activeMessage = messages.find(m => m.id === activeMessageId);
  const currentSession = sessions.find(s => s.id === currentSessionId);

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="header-left" style={{ gap: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Database size={20} color="#4f46e5" />
            <span>Embrix Analytics</span>
          </div>

          {/* Empty Tables Header Badge */}
          {emptyTables.length > 0 && (
            <div style={{ position: 'relative' }}>
              <button 
                onClick={() => setShowEmptyTables(!showEmptyTables)}
                style={{ background: '#fef2f2', border: '1px solid #f87171', borderRadius: '6px', padding: '0.3rem 0.6rem', color: '#b91c1c', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600, fontSize: '0.8rem' }}
                title="View Empty Tables"
              >
                <span>⚠️</span>
                <span>{emptyTables.length} Empty Tables</span>
                <ChevronDown size={14} style={{ transform: showEmptyTables ? 'rotate(180deg)' : 'none', transition: 'transform 0.3s ease' }} />
              </button>
              
              {showEmptyTables && (
                <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: '0.5rem', background: '#fef2f2', border: '1px solid #f87171', borderRadius: '8px', boxShadow: 'var(--shadow-md)', width: '300px', zIndex: 60, overflow: 'hidden' }}>
                  <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #fca5a5', fontWeight: 600, color: '#b91c1c', fontSize: '0.85rem' }}>
                    Empty tables in {SCHEMA_NAME}:
                  </div>
                  <div style={{ padding: '1rem', color: '#991b1b', fontSize: '0.85rem', fontFamily: 'var(--font-mono)', maxHeight: '300px', overflowY: 'auto' }}>
                    {emptyTables.join(", ")}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Model Selector Dropdown */}
          <div className="sessions-dropdown-container">
            <button 
              className="sessions-dropdown-btn" 
              onClick={() => {
                setShowModelsMenu(!showModelsMenu);
                setShowSessionsMenu(false);
              }}
              style={{ background: 'var(--accent-bg)', borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' }}
              title="Select LLM Engine Model"
            >
              <Cpu size={16} />
              <span>{selectedModel.name}</span>
              <ChevronDown size={16} style={{ transform: showModelsMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }} />
            </button>
            
            {showModelsMenu && (
              <div className="sessions-menu" style={{ width: '310px' }}>
                <div style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Sparkles size={12} color="var(--accent-primary)" />
                  Select LLM Model Engine
                </div>
                {AVAILABLE_MODELS.map(m => (
                  <div 
                    key={m.id} 
                    className={`history-item ${selectedModel.id === m.id ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedModel(m);
                      setShowModelsMenu(false);
                    }}
                    style={{ padding: '0.6rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>{m.name}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                        <span style={{ fontSize: '0.65rem', padding: '2px 6px', borderRadius: '10px', background: m.badgeBg, color: m.badgeColor, fontWeight: 700 }}>
                          {m.badge}
                        </span>
                        {selectedModel.id === m.id && <Check size={14} color="var(--accent-primary)" />}
                      </div>
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                      {m.desc}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Sessions Dropdown */}
          <div className="sessions-dropdown-container">
            <button 
              className="sessions-dropdown-btn" 
              onClick={() => {
                setShowSessionsMenu(!showSessionsMenu);
                setShowModelsMenu(false);
              }}
            >
              <MessageSquare size={16} />
              {currentSession ? currentSession.title : "Select Session"}
              <ChevronDown size={16} style={{ transform: showSessionsMenu ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }} />
            </button>
            
            {showSessionsMenu && (
              <div className="sessions-menu">
                {sessions.map(s => (
                  <div 
                    key={s.id} 
                    className={`history-item ${currentSessionId === s.id ? 'active' : ''}`}
                    onClick={() => {
                      setCurrentSessionId(s.id);
                      setShowSessionsMenu(false);
                    }}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
                      <MessageSquare size={14} />
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {s.title}
                      </span>
                    </div>
                    <button 
                      onClick={(e) => deleteSession(s.id, e)}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '2px', display: 'flex' }}
                      title="Delete Chat"
                      onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                      onMouseLeave={(e) => e.currentTarget.style.color = '#9ca3af'}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <div className="history-item new-chat-item" onClick={createSession}>
                  <PlusCircle size={14} />
                  New Chat
                </div>
              </div>
            )}
          </div>
        </div>
      </header>


      {/* Split Workspace */}
      <div className="workspace">
        
        {/* Left Canvas (Data View) */}
        <div className="canvas-panel" style={{ position: 'relative' }}>
          
          {activeMessage ? (
            <div className="canvas-content">
              {activeMessage.sql && (
                <SqlEditor 
                  initialSql={activeMessage.sql} 
                  onRerun={(newSql) => handleRerun(newSql, activeMessage.id, activeMessage.content)}
                  disabled={isLoading}
                />
              )}
              
              {activeMessage.chart_spec && activeMessage.parsedData && (
                <ChatChart spec={activeMessage.chart_spec} data={activeMessage.parsedData} />
              )}
              
              {activeMessage.parsedData && activeMessage.parsedData.length > 0 && !activeMessage.chart_spec && (
                <DataTable data={activeMessage.parsedData} />
              )}
            </div>
          ) : (
            <div className="canvas-empty">
              <h2>Welcome to Embrix</h2>
              <p>Ask a question about the <strong>{SCHEMA_NAME}</strong> database schema in the chat to see results here.</p>
            </div>
          )}
        </div>

        {/* Right Panel (Chat) */}
        <div className="chat-panel">
          <div className="messages">
            {suggestedQuestions.length > 0 && messages.length === 0 && (
              <div style={{ marginBottom: '2rem' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#4f46e5', marginBottom: '0.75rem' }}>Suggested Questions:</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {suggestedQuestions.map((q, idx) => (
                    <button 
                      key={idx}
                      onClick={() => setInputValue(q)}
                      style={{
                        textAlign: 'left',
                        background: 'rgba(79, 70, 229, 0.1)',
                        border: '1px solid rgba(79, 70, 229, 0.3)',
                        padding: '0.6rem 1rem',
                        borderRadius: '6px',
                        color: '#4f46e5',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                        transition: 'background 0.2s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(79, 70, 229, 0.2)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(79, 70, 229, 0.1)'}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            
            {messages.map((msg, i) => {
              const isActive = msg.id === activeMessageId;
              const hasData = msg.sql || msg.parsedData;
              
              return (
                <div 
                  key={i} 
                  className={`message-wrapper ${msg.role} ${isActive ? 'active-msg' : ''}`}
                  onClick={() => {
                    if (msg.role === 'assistant' && hasData) {
                      setActiveMessageId(msg.id);
                    } else if (msg.role === 'user') {
                      // Find the next assistant message and select it
                      const nextMsg = messages.slice(i + 1).find(m => m.role === 'assistant' && (m.sql || m.parsedData));
                      if (nextMsg) setActiveMessageId(nextMsg.id);
                    }
                  }}
                >
                  <div className="message-label">{msg.role}</div>
                  <div className="message-bubble">
                    {msg.role === 'user' ? (
                      msg.content
                    ) : (
                      <div>
                        {/* Message Content (split by newlines to render thought duration nicely) */}
                        {msg.content ? msg.content.split('\n').map((line, idx) => (
                          <React.Fragment key={idx}>
                            {line.startsWith('--thought') ? (
                              <span style={{ fontSize: '0.8rem', color: '#9ca3af', fontStyle: 'italic' }}>{line}</span>
                            ) : line}
                            <br />
                          </React.Fragment>
                        )) : "Analyzing data..."}
                        
                        {/* Clickable Follow-ups */}
                        {msg.follow_ups && msg.follow_ups.length > 0 && (
                          <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#4f46e5' }}>Suggested Follow-ups:</div>
                            {msg.follow_ups.map((q, qIdx) => (
                              <button 
                                key={qIdx}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setInputValue(q);
                                }}
                                style={{
                                  textAlign: 'left',
                                  background: 'rgba(79, 70, 229, 0.1)',
                                  border: '1px solid rgba(79, 70, 229, 0.3)',
                                  padding: '0.6rem 1rem',
                                  borderRadius: '6px',
                                  color: '#4f46e5',
                                  cursor: 'pointer',
                                  fontSize: '0.85rem',
                                  transition: 'background 0.2s ease'
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(79, 70, 229, 0.2)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(79, 70, 229, 0.1)'}
                              >
                                {q}
                              </button>
                            ))}
                          </div>
                        )}
                        
                        {hasData && (
                          <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#4f46e5', fontWeight: 500 }}>
                            {isActive ? "Currently viewing data 👈" : "Click to view data"}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            
            {isLoading && (
              <div className="message-wrapper assistant">
                <div className="message-label">Assistant</div>
                <div className="message-bubble">
                  <div className="loading-dots">
                    <div className="dot"></div>
                    <div className="dot"></div>
                    <div className="dot"></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <form className="input-form" onSubmit={handleSend}>
              <input 
                type="text" 
                className="chat-input"
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                placeholder="Ask about data..."
                disabled={isLoading}
              />
              <button type="submit" className="send-btn" disabled={isLoading || !inputValue.trim()}>
                <Send size={16} />
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;
