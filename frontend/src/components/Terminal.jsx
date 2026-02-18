import { useState, useEffect, useRef } from 'react';
import { ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import ufoIcon from '../assets/ufo.jpeg';

const Terminal = () => {
  const [sessions, setSessions] = useState([]);
  const [input, setInput] = useState('');
  const [cursorLeft, setCursorLeft] = useState(0);
  const [isFocused, setIsFocused] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [awaitingFeedback, setAwaitingFeedback] = useState(false);
  const [currentCommandId, setCurrentCommandId] = useState(null);

  const ws = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const terminalRef = useRef(null);
  const measureRef = useRef(null);

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
    inputRef.current?.focus();
  }, []);

  const updateCursorPosition = () => {
    if (inputRef.current && measureRef.current) {
        const { selectionStart } = inputRef.current;
        const textBeforeCaret = input.slice(0, selectionStart);
        measureRef.current.textContent = textBeforeCaret;
        
        // The span puts text in, we measure its width.
        // We use a non-breaking space if text is empty to ensure height is correct, but for width 0 is fine.
        // However, spaces at the end of textContent might not render width correctly unless pre-wrap is used.
        // In the render below, we use 'whitespace-pre'.
        setCursorLeft(measureRef.current.offsetWidth);
    }
  };

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
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }
      
      const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
      const socket = new WebSocket(`${wsUrl}/ws/${clientId}`);

      const timeout = setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          socket.close();
          reject(new Error("Connection timed out. Server might be unreachable."));
        }
      }, 5000);

      socket.onopen = () => {
        clearTimeout(timeout);
        resolve();
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
    if (awaitingFeedback) {
        setInput('');
        setCursorLeft(0);
        sendApproval(false, cmd); 
        return;
    }

    if (awaitingApproval) {
      setInput('');
      setCursorLeft(0);
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
    setCursorLeft(0);        
    setIsProcessing(true);

    const clientId = generateClientId();
    
    try {
      addLog('text', 'Initializing Sequence...');
      await connectWebSocket(clientId);
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/generate-meme`, {
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

  const handleInputChange = (e) => {
      setInput(e.target.value);
      // We must update cursor after state update; doing it immediately relies on render
      // But updateCursorPosition relies on state 'input' which is async.
      // So we rely on useEffect or perform measuring based on event value.
      // Better: updateCursorPosition uses the inputRef value which is current? 
      // inputRef.current.value is what the user just typed.
      // So calling updateCursorPosition immediately is fine if we use the ref.
      // Actually, standard React pattern: set state, then effect. 
      // But for smooth cursor, let's call it via requestAnimationFrame or setTimeout(0)
      requestAnimationFrame(updateCursorPosition);
  };

  useEffect(() => {
      updateCursorPosition();
  }, [input]);

  let promptLabel = '$';
  if (awaitingApproval) promptLabel = 'Approve (Y/N) >';
  else if (awaitingFeedback) promptLabel = 'Feedback >';

  return (
    <div 
      ref={terminalRef}
      className="w-[90vw] h-[90vh] font-mono text-lg leading-relaxed text-terminal-green terminal-glow flex flex-col bg-transparent rounded-lg relative z-20 overflow-y-auto terminal-scrollbar"
    >
      
      {/* 0. TERMINAL HEADER */}
      <div className="w-full border-y border-terminal-green py-4 mb-8 pointer-events-none select-none flex justify-center items-center gap-6">
          <img 
            src={ufoIcon} 
            alt="MEMINI UFO" 
            className="h-32 object-contain drop-shadow-[0_0_15px_rgba(0,255,65,0.6)] opacity-90 mix-blend-screen"
          />
          <h1 className="text-7xl font-bold tracking-[0.3em] text-terminal-green terminal-glow uppercase drop-shadow-lg">
            MEMEVERSE
          </h1>
      </div>

      <div className="flex flex-col gap-6 pb-4 px-8">
        {sessions.map((session, index) => {
            const textLogs = session.logs.filter(l => l.type !== 'image');
            
            const rawImageLogs = session.logs.filter(l => l.type === 'image');
            const imageLogs = rawImageLogs.filter((log, index, self) =>
                index === self.findIndex((t) => t.content === log.content)
            );

            let visibleTextLogs = textLogs.length > 0 ? [textLogs[textLogs.length - 1]] : [];

            if (isProcessing && index === sessions.length - 1 && visibleTextLogs.length > 0) {
                visibleTextLogs = [];
            }

            return (
                <div key={session.id} className="flex flex-col gap-2">
                   
                    <div className="mb-2 pb-2">
                        <span className="mr-3 text-terminal-green font-semibold">$</span>
                        <span className="text-white opacity-90 font-medium">{session.command}</span>
                    </div>

                    {(visibleTextLogs.length > 0 || (isProcessing && index === sessions.length - 1) || imageLogs.length > 0) && (
                        <div className="flex flex-col gap-2">
                             {(visibleTextLogs.length > 0 || (isProcessing && index === sessions.length - 1)) && (
                                <div className="rounded-lg bg-space-blue/40 border border-white/5 p-4 backdrop-blur-sm shadow-lg transition-all duration-300" style={{ boxShadow: '0 0 10px rgba(0, 0, 0, 0.3)' }}>
                                    <div className="flex items-start">
                                        
                                        <div className="flex-grow flex flex-col gap-1 font-mono text-sm">
                                            {visibleTextLogs.map((item, idx) => (
                                              <div key={idx} className="break-words">
                                                 {item.type === 'text' && <span className="text-gray-300">{item.content}</span>}
                                                 {item.type === 'sys' && <span className="text-gray-500 italic">[SYS] {item.content}</span>}
                                                 {item.type === 'init' && <span className="text-blue-400">› {item.content}</span>}
                                                 {item.type === 'success' && <span className="text-terminal-green font-medium">✓ {item.content}</span>}
                                                 {item.type === 'warning' && <span className="text-yellow-400">⚠ {item.content}</span>}
                                                 {item.type === 'error' && <span className="text-red-500 font-semibold">❌ {item.content}</span>}
                                              </div>
                                            ))}
                                            
                                            {isProcessing && index === sessions.length - 1 && (
                                              <div className="flex items-center text-terminal-green animate-pulse">
                                                <Loader2 className="animate-spin mr-2" size={14} />
                                                <span className="font-mono text-sm">
                                                    {textLogs.length > 0 ? textLogs[textLogs.length - 1].content : 'Processing...'}
                                                </span>
                                              </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                             )}

                             {imageLogs.map((imgLog, imgIdx) => (
                                 <MemeImage key={imgIdx} src={imgLog.content} version={imgIdx + 1} />
                             ))}
                        </div>
                    )}
                </div>
            );
        })}
        
        <div ref={messagesEndRef} />
      </div>

      {!isProcessing && (
        <div 
          className="flex items-center mt-4 pt-2 cursor-text px-8 pb-8"
          onClick={() => inputRef.current?.focus()}
        >
          <span className="mr-3 text-terminal-green font-semibold whitespace-nowrap">
            {promptLabel}
          </span>
          <div className="relative inline-block flex-grow min-w-[10px] min-h-[1.5em]">
            
             <span className="whitespace-pre text-gray-200 break-all relative z-10 pointer-events-none">
              {input || '\u00A0'}
            </span>

            {/* The Ghost Measure (Hidden) */}
            <span 
                ref={measureRef}
                className="absolute top-0 left-0 whitespace-pre opacity-0 pointer-events-none -z-10"
                aria-hidden="true"
            ></span>

            {/* The Custom Cursor */}
            {isFocused && (
                <span 
                    className="absolute top-[3px] inline-block w-[10px] h-[1.2em] bg-terminal-green animate-blink align-text-bottom ml-[1px]"
                    style={{ left: cursorLeft }}
                ></span>
            )}

            {/* Hidden Input for Logic */}
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onSelect={updateCursorPosition}
              onClick={updateCursorPosition}
              onKeyUp={updateCursorPosition}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              className="absolute inset-0 w-full h-full opacity-0 cursor-text text-transparent bg-transparent border-none outline-none"
              autoFocus
              autoComplete="off"
            />
          </div>
        </div>
      )}
    </div>
  );
};

const MemeImage = ({ src, version = 1 }) => {
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
        <span className="text-space-cyan font-medium text-sm tracking-wide">
          Meme v{version}
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

