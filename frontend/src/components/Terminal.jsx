import { useState, useEffect, useRef } from 'react';
import { ChevronRight, ChevronDown, Loader2 } from 'lucide-react';

const Terminal = () => {
  // Chat History: Array of session objects { id, command, logs: [], isExpanded: boolean }
  const [sessions, setSessions] = useState([]);
  
  // Input states
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [awaitingFeedback, setAwaitingFeedback] = useState(false);
  const [currentCommandId, setCurrentCommandId] = useState(null);

  const ws = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const terminalRef = useRef(null);

  const scrollToBottom = (force = false) => {
    if (force) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      return;
    }

    if (terminalRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      if (isNearBottom) {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  // Effect to auto-scroll when new logs are added
  useEffect(() => {
    const shouldForce = awaitingApproval || awaitingFeedback;
    scrollToBottom(shouldForce);
  }, [sessions, awaitingApproval, awaitingFeedback]);

  useEffect(() => {
    const focusInput = () => inputRef.current?.focus();
    focusInput();
    document.addEventListener('click', focusInput);
    return () => document.removeEventListener('click', focusInput);
  }, []);

  // Helper to add log to the LATEST session
  const addLog = (type, content) => {
    setSessions(prev => {
      if (prev.length === 0) return prev;
      const lastSession = prev[prev.length - 1];
      const updatedSession = {
        ...lastSession,
        logs: [...lastSession.logs, { type, content }]
      };
      return [...prev.slice(0, -1), updatedSession];
    });
  };

  const toggleSession = (index) => {
    setSessions(prev => prev.map((session, i) => 
      i === index ? { ...session, isExpanded: !session.isExpanded } : session
    ));
  };

  const generateClientId = () => {
    return 'client-' + Math.random().toString(36).substr(2, 9);
  };

  const connectWebSocket = (clientId) => {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(`ws://localhost:8000/ws/${clientId}`);

      // Set a connection timeout to prevent indefinite hanging
      const timeout = setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          socket.close();
          reject(new Error("Connection timed out. Server might be unreachable."));
        }
      }, 5000);

      socket.onopen = () => {
        clearTimeout(timeout);
        resolve(socket);
      };

      socket.onerror = (error) => {
        clearTimeout(timeout);
        console.error("WebSocket Error:", error);
        reject(new Error("WebSocket Connection Failed."));
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'event_log') {
            addLog('text', `${data.message}`);
          }
          else if (data.type === 'approval_request') {
            addLog('text', 'INCOMING TRANSMISSION <<<');
            if (data.meme_url) {
              addLog('image', data.meme_url);
            }
            addLog('text', `[Action Required] Approve this meme? (Y/N)`);

            setAwaitingApproval(true);
            setAwaitingFeedback(false);
            setCurrentCommandId(data.command_id);
            setIsProcessing(false);
            
            // Ensure the current session is expanded
            setSessions(prev => {
                const newSessions = [...prev];
                if (newSessions.length > 0) {
                    newSessions[newSessions.length - 1].isExpanded = true;
                }
                return newSessions;
            });
          }
        } catch (err) {
          console.error("WS Parse Error:", err);
        }
      };

      ws.current = socket;
    });
  };

  const sendApproval = (approved, feedback) => {
    if (!ws.current) return;
    const humanApproval = approved ? "true" : "false";

    const decision = {
      type: "decision",
      approved: humanApproval,
      feedback: feedback,
      command_id: currentCommandId
    };

    ws.current.send(JSON.stringify(decision));
    addLog('text', ` Decision Transmitted: ${approved ? 'APPROVED' : 'REJECTED'}`);
    if (!approved && feedback) {
      addLog('text', `Feedback: ${feedback}`);
    }

    setAwaitingApproval(false);
    setAwaitingFeedback(false);
    setCurrentCommandId(null);
    setIsProcessing(true);
  };

  const handleCommand = async (cmd) => {
    // Step 2: Feedback Submission
    if (awaitingFeedback) {
        setInput('');
        sendApproval(false, cmd); 
        return;
    }

    // Step 1: Approval Check
    if (awaitingApproval) {
      setInput('');
      const lowerCmd = cmd.toLowerCase().trim();
      
      if (lowerCmd === 'y' || lowerCmd === 'yes') {
        sendApproval(true, "Looks good!");
      } else if (lowerCmd === 'n' || lowerCmd === 'no') {
        addLog('warning', 'Decision: No');
        addLog('warning', 'Input Required: Provide reasoning for rejection.');
        setAwaitingApproval(false);
        setAwaitingFeedback(true); 
      } else {
        addLog('error', 'Invalid Protocol. Access Denied. Type Y or N.');
      }
      return;
    }

    // Initial Prompt Submission -> START NEW SESSION
    const newSessionId = Date.now();
    setSessions(prev => [
        ...prev, 
        { 
            id: newSessionId, 
            command: cmd, 
            logs: [], 
            isExpanded: true 
        }
    ]);
    
    setInput('');        
    setIsProcessing(true);

    const clientId = generateClientId();
    
    try {
      addLog('text', 'Initializing Sequence...');
      // 1. Establish WS Connection FIRST
      await connectWebSocket(clientId);

      // 2. Send API Request
      const response = await fetch('http://localhost:8000/generate-meme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: cmd, client_id: clientId }),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.meme_url) {
        addLog('text', 'SEQUENCE COMPLETE');
        addLog('image', data.meme_url);
        addLog('text', 'Meme Generated Successfully.');
      } else {
        addLog('text', 'SEQUENCE FAILED: No meme URL returned.');
      }
      
    } catch (err) {
      addLog('error', `${err instanceof Error ? err.message : 'Unknown error'}`);
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    } finally {
      setIsProcessing(false);
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      const cmd = input.trim();
      if (!cmd) return;
      handleCommand(cmd);
    }
  };

  let promptLabel = '$';
  if (awaitingApproval) promptLabel = 'Approve (Y/N) >';
  else if (awaitingFeedback) promptLabel = 'Feedback >';

  return (
    <div 
      ref={terminalRef}
      className="w-[90vw] h-[90vh] p-8 font-mono text-lg leading-relaxed text-terminal-green terminal-glow flex flex-col bg-transparent rounded-lg relative z-20 overflow-y-auto terminal-scrollbar"
    >
      
      {/* 1. Session History (Multiple Boxes) */}
      <div className="flex flex-col gap-6 pb-4">
        {sessions.map((session, index) => {
            // Determine visible logs based on expanded state
            const visibleLogs = session.isExpanded 
                ? session.logs 
                : session.logs.length > 0 ? [session.logs[session.logs.length - 1]] : [];

            return (
                <div key={session.id} className="flex flex-col gap-2">
                    {/* Session Header (Command) */}
                    <div className="mb-2 pb-2">
                        <span className="mr-3 text-terminal-green font-bold">$</span>
                        <span className="text-white opacity-90 font-bold">{session.command}</span>
                    </div>

                    {/* Log Box */}
                    {session.logs.length > 0 && (
                        <div className="rounded-lg bg-space-blue/40 border border-white/5 p-4 backdrop-blur-sm shadow-lg transition-all duration-300" style={{ boxShadow: '0 0 10px rgba(0, 0, 0, 0.3)' }}>
                            <div className="flex items-start">
                                <button 
                                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSession(index); }}
                                  className="mr-3 mt-1 hover:text-space-cyan transition-colors focus:outline-none cursor-pointer p-1 rounded hover:bg-space-cyan/10 flex-shrink-0"
                                >
                                    {session.isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                </button>
                                
                                <div className="flex-grow flex flex-col gap-2">
                                    {visibleLogs.map((item, idx) => (
                                      <div key={idx} className={`break-words ${item.type === 'text' ? 'text-gray-200' : ''} ${item.type === 'error' ? 'text-red-500 font-bold' : ''}`}>
                                         {item.type === 'text' && <span className="font-mono text-sm">{item.content}</span>}
                                         {item.type === 'error' && <span className="font-mono text-sm">❌ {item.content}</span>}
                                         
                                         {/* TYPE: IMAGE (Collapsible) */}
                                         {item.type === 'image' && <MemeImage src={item.content} />}
                                      </div>
                                    ))}
                                    
                                    {/* Processing Loader - Only for active session */}
                                    {isProcessing && index === sessions.length - 1 && (
                                      <div className="flex items-center text-terminal-green mt-2 animate-pulse">
                                        <Loader2 className="animate-spin mr-2" size={14} />
                                        <span className="font-mono text-sm">Processing...</span>
                                      </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        })}
        
        {/* Spacer for scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* 2. Input Section - Only visible when NOT processing */}
      {!isProcessing && (
        <div className="flex items-center mt-4 pt-2">
          <span className="mr-3 text-terminal-green font-bold whitespace-nowrap">
            {promptLabel}
          </span>
          <div className="relative inline-block min-w-[10px] flex-grow">
            <span className="whitespace-pre visible text-gray-200">
              {input}
              <span className="inline-block w-[10px] h-[1.2em] bg-terminal-green animate-blink align-text-bottom ml-[2px]">&nbsp;</span>
            </span>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              className="absolute inset-0 w-full h-full opacity-0 border-none outline-none bg-transparent text-transparent caret-transparent"
              autoFocus
            />
          </div>
        </div>
      )}
    </div>
  );
};

// Collapsible Image Component
const MemeImage = ({ src }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="my-2 border border-white/5 rounded-lg bg-space-blue/40 overflow-hidden w-max backdrop-blur-sm shadow-lg transition-all duration-300" style={{ boxShadow: '0 0 10px rgba(0, 0, 0, 0.3)' }}>
      <button 
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="w-full flex items-center px-4 py-2 text-left hover:bg-space-cyan/10 transition-colors focus:outline-none gap-2"
      >
        <span className="text-space-cyan">
          {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <span className="text-space-cyan font-bold text-sm tracking-wide">
          Meme
        </span>
      </button>
      
      {isOpen && (
        <div className="p-4 border-t border-white/5">
          <img 
            src={src} 
            alt="Generated Meme" 
            className="max-w-[400px] max-h-[60vh] block rounded mx-auto border border-white/10 shadow-xl" 
          />
        </div>
      )}
    </div>
  );
};

export default Terminal;

