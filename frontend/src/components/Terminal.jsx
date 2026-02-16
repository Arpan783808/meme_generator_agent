import React, { useState, useEffect, useRef } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

const Terminal = () => {
  // State for the fixed prompt (once submitted)
  const [fixedPrompt, setFixedPrompt] = useState(null);
  
  // State for the "Box 1" logs (system messages, images)
  const [logs, setLogs] = useState([]);
  const [isLogsExpanded, setIsLogsExpanded] = useState(false);
  
  // Input states
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [awaitingFeedback, setAwaitingFeedback] = useState(false); // New state for feedback step
  const [currentCommandId, setCurrentCommandId] = useState(null);
  
  const ws = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isLogsExpanded) {
        scrollToBottom();
    }
  }, [logs, awaitingApproval, awaitingFeedback, isLogsExpanded]); // Added awaitingFeedback dep

  useEffect(() => {
    // Focus input on mount and clicks
    const focusInput = () => inputRef.current?.focus();
    focusInput();
    document.addEventListener('click', focusInput);
    return () => document.removeEventListener('click', focusInput);
  }, []);

  const addLog = (type, content) => {
    setLogs(prev => [...prev, { type, content }]);
  };

  const generateClientId = () => {
    return 'client-' + Math.random().toString(36).substr(2, 9);
  };

  const connectWebSocket = (clientId) => {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(`ws://localhost:8000/ws/${clientId}`);
      
      socket.onopen = () => {
        addLog('text', `>>> Secure Channel Established [ID: ${clientId}]`);
        resolve(socket);
      };

      socket.onerror = (error) => {
        console.error("WebSocket Error:", error);
        // Don't reject here immediately as it might be a temporary network issue, 
        // but for initial connection failure we might want to know.
        // For simplicity, we just log it. The main flow relies on onopen.
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'event_log') {
            addLog('text', `[SYS] ${data.message}`);
          } 
          else if (data.type === 'approval_request') {
            addLog('text', '>>> INCOMING TRANSMISSION <<<');
            if (data.meme_url) {
              addLog('image', data.meme_url);
            }
            addLog('text', `[Action Required] Approve this meme? (Y/N)`); 
            
            setAwaitingApproval(true);
            setAwaitingFeedback(false); 
            setCurrentCommandId(data.command_id);
            setIsProcessing(false); 
            setIsLogsExpanded(true); 
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
    
    const decision = {
      type: "decision",
      approved: approved,
      feedback: feedback,
      command_id: currentCommandId
    };
    
    ws.current.send(JSON.stringify(decision));
    addLog('text', `>>> Decision Transmitted: ${approved ? 'APPROVED' : 'REJECTED'}`);
    if (!approved && feedback) {
        addLog('text', `Feedback: ${feedback}`);
    }
    
    setAwaitingApproval(false);
    setAwaitingFeedback(false);
    setCurrentCommandId(null);
    setIsProcessing(true); // Wait for final result
  };

  const handleCommand = async (cmd) => {
    // Step 2: Feedback Submission (Only if rejected in Step 1)
    if (awaitingFeedback) {
        setInput('');
        // Send rejection with user provided feedback
        sendApproval(false, cmd); 
        return;
    }

    // Step 1: Approval Check (Y/N)
    if (awaitingApproval) {
      setInput('');
      const lowerCmd = cmd.toLowerCase().trim();
      
      if (lowerCmd === 'y' || lowerCmd === 'yes') {
        // Approved Step
        sendApproval(true, "Looks good!");
      } else if (lowerCmd === 'n' || lowerCmd === 'no') {
        // Rejected Step -> Move to Feedback
        addLog('text', 'Decision: No');
        addLog('text', 'Please provide feedback/reason:');
        setAwaitingApproval(false);
        setAwaitingFeedback(true); // Enable feedback mode
      } else {
        // Invalid input for Y/N
        addLog('text', 'Invalid Input. Please type Y or N.');
      }
      return;
    }

    // Initial Prompt Submission
    setFixedPrompt(cmd); // Fix the prompt at top
    setInput('');        // Clear input
    setIsProcessing(true);
    setLogs([]);         // Clear previous logs
    setIsLogsExpanded(false); // Reset collapse state
    
    const clientId = generateClientId();
    
    try {
      addLog('text', '>>> Initializing Sequence...');
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
        addLog('text', '>>> SEQUENCE COMPLETE');
        addLog('image', data.meme_url);
        addLog('text', 'System ready. Reload to start new session.');
        setIsLogsExpanded(true); // Expand on completion
      } else {
        addLog('text', '>>> SEQUENCE FAILED: No meme URL returned.');
      }
      
    } catch (err) {
      addLog('text', `>>> ERROR: ${err.message}`);
      // Clean up socket if error
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    } finally {
      setIsProcessing(false);
      // We generally keep the socket open for feedback, but if the sequence finished without approval needed (e.g. error), verify cleanup logic.
      // For now, if currentCommandId is null and no awaiting approval, we can close? 
      // Actually, better to leave it open until user reloads or explicit close logic.
      // But the original code closed it here. Let's stick to closing it ONLY if we are done.
      // However, if we are awaiting approval, we MUST NOT close it.
      
      // The original code had:
      /*
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
      */
      // But wait, if we are `awaitingApproval`, the WS handles messages.
      // `handleCommand` finishes execution after the `fetch` returns?
      // NO. The `fetch` calls `generate_meme`, which waits for feedback.
      // So `fetch` will NOT return until the entire pipeline is done (including feedback).
      // So keeping `ws.current.close()` in `finally` block is CORRECT, 
      // because `await fetch` blocks until the backend function returns.
      // Backend returns AFTER feedback is resolved.
      
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

  // Determine which logs to show
  const visibleLogs = isLogsExpanded 
    ? logs 
    : logs.length > 0 ? [logs[logs.length - 1]] : [];

  // Determine prompt text
  let promptLabel = '$';
  if (awaitingApproval) promptLabel = 'Approve (Y/N) >';
  else if (awaitingFeedback) promptLabel = 'Feedback >';

  return (
    <div className="w-[90vw] h-[90vh] p-8 font-mono text-lg leading-relaxed text-terminal-green text-shadow-glow flex flex-col bg-transparent rounded-lg relative z-20 overflow-hidden">
      
      {/* 1. Fixed Prompt Section */}
      {fixedPrompt && (
        <div className="mb-4 pb-2">
          <span className="mr-3 text-terminal-green font-bold">$</span>
          <span className="text-white opacity-90">{fixedPrompt}</span>
        </div>
      )}

      {/* 2. Box 1: System Logs & Images (Scrollable & Collapsible) */}
      <div className={`overflow-y-auto pb-4 scrollbar-thin flex flex-col gap-2 ${fixedPrompt ? 'flex-grow' : ''}`}>
        
        {/* Toggle Button (Only show if there are logs) */}
        {logs.length > 0 && (fixedPrompt || awaitingApproval || awaitingFeedback) && (
            <div className="flex items-start relative">
                <button 
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsLogsExpanded(!isLogsExpanded); }}
                  className="mr-2 mt-1 hover:text-white transition-colors focus:outline-none cursor-pointer z-50 p-1 rounded hover:bg-white/10"
                >
                    {isLogsExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                </button>
                
                <div className="flex-grow flex flex-col gap-1">
                    {visibleLogs.map((item, index) => (
                      <div key={index} className={`break-words ${item.type === 'text' ? 'text-gray-300' : ''}`}>
                         {item.type === 'text' && <span>{item.content}</span>}
                         {item.type === 'image' && (
                           <div className="my-4 border border-terminal-green p-1 inline-block bg-black/50">
                             <img src={item.content} alt="Meme" className="max-w-full max-h-[60vh] block" />
                           </div>
                         )}
                      </div>
                    ))}
                </div>
            </div>
        )}
        
        {/* Spacer for scroll */}
        <div ref={messagesEndRef} />
      </div>
      
      {/* 3. Input Section (Only visible when needed) */}
      {(!fixedPrompt || awaitingApproval || awaitingFeedback) && (
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

export default Terminal;
