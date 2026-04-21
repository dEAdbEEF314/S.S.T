import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchLLMLogs } from '@/lib/api';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Bot, User, Cpu, MessageSquare, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';

function ChatBubble({ role, content }: { role: string, content: any }) {
  const isBot = role === 'assistant' || role === 'system';
  const displayContent = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

  return (
    <div className={cn("flex gap-3 mb-6", isBot ? "flex-row" : "flex-row-reverse")}>
      <div className={cn(
        "w-9 h-9 rounded-full flex items-center justify-center shrink-0 shadow-md",
        isBot ? "bg-emerald-600 text-white" : "bg-blue-600 text-white"
      )}>
        {role === 'assistant' ? <Bot size={20} /> : role === 'system' ? <Cpu size={20} /> : <User size={20} />}
      </div>
      <div className={cn(
        "max-w-[85%] rounded-2xl px-5 py-3 text-[13px] shadow-sm border",
        isBot 
          ? "bg-slate-900 border-slate-800 text-slate-200 rounded-tl-none" 
          : "bg-blue-900/40 border-blue-800 text-blue-50 rounded-tr-none"
      )}>
        <div className="font-bold text-[10px] uppercase tracking-tighter opacity-40 mb-1">{role}</div>
        <div className="whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
          {displayContent}
        </div>
      </div>
    </div>
  );
}

export default function LLMLogsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: logs, isLoading } = useQuery({
    queryKey: ['llm-logs'],
    queryFn: fetchLLMLogs,
  });

  const selectedLog = logs?.find((l: any) => l.id === selectedId);

  // Transform the log content into messages for display
  // Supports both legacy single-request format and new chat-session format
  let messages: { role: string, content: any }[] = [];
  
  if (selectedLog) {
    if (selectedLog.content.session && Array.isArray(selectedLog.content.session)) {
      // New format: Multiple track sessions
      selectedLog.content.session.forEach((s: any) => {
        messages.push({ role: 'user', content: s.prompt || `Processing Track: ${s.track_id}` });
        messages.push({ role: 'assistant', content: s.response });
      });
    } else {
      // Legacy format: Single request/response
      messages = [
        ...(selectedLog.content.request || []).map((m: any) => ({ role: m.role, content: m.content })),
        { role: 'assistant', content: selectedLog.content.response }
      ];
    }
  }

  return (
    <div className="flex gap-6 h-[calc(100vh-10rem)]">
      {/* Sidebar: Log List */}
      <Card className="w-80 flex flex-col overflow-hidden border-slate-800 bg-slate-900/20">
        <CardHeader className="border-b border-slate-800 p-4 bg-slate-900/40">
          <CardTitle className="text-sm font-bold flex items-center gap-2 text-slate-200 uppercase tracking-widest">
            <MessageSquare size={16} className="text-emerald-500" /> Interactions
          </CardTitle>
        </CardHeader>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoading ? (
            <div className="p-4 text-center text-slate-500 text-xs animate-pulse">Loading logs...</div>
          ) : !logs || logs.length === 0 ? (
            <div className="p-8 text-center text-slate-600 text-xs italic">No logs found in archive.</div>
          ) : (
            logs.map((log: any) => (
              <button
                key={log.id}
                onClick={() => setSelectedId(log.id)}
                className={cn(
                  "w-full text-left p-4 rounded-xl transition-all border group",
                  selectedId === log.id 
                    ? "bg-emerald-600/10 border-emerald-500/30 shadow-inner" 
                    : "bg-transparent border-transparent hover:bg-slate-800/40 hover:border-slate-800"
                )}
              >
                <div className={cn(
                  "text-[10px] font-mono font-bold mb-1 transition-colors",
                  selectedId === log.id ? "text-emerald-400" : "text-slate-500 group-hover:text-slate-400"
                )}>
                  APP ID: {log.app_id}
                </div>
                <div className={cn(
                  "text-xs font-bold truncate transition-colors",
                  selectedId === log.id ? "text-white" : "text-slate-300 group-hover:text-white"
                )}>
                  {log.album_name}
                </div>
                <div className="flex items-center gap-1.5 mt-2 text-[10px] text-slate-500 font-medium">
                  <Clock size={10} />
                  {log.timestamp ? format(new Date(log.timestamp), 'yyyy/MM/dd HH:mm') : 'Unknown'}
                </div>
              </button>
            ))
          )}
        </div>
      </Card>

      {/* Main: Chat View */}
      <Card className="flex-1 flex flex-col overflow-hidden border-slate-800 bg-slate-950/80 shadow-2xl relative">
        {!selectedId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-4">
            <div className="w-16 h-16 rounded-3xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-700">
              <Bot size={32} />
            </div>
            <div className="text-center">
              <p className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-1">Select an Interaction</p>
              <p className="text-xs italic text-slate-600">Review how LLM consolidated your metadata</p>
            </div>
          </div>
        ) : (
          <>
            <CardHeader className="border-b border-slate-800 bg-slate-900/60 flex flex-row items-center justify-between p-5 backdrop-blur-md">
              <div className="flex flex-col gap-1">
                <CardTitle className="text-base font-bold text-white tracking-tight">{selectedLog?.album_name}</CardTitle>
                <div className="flex items-center gap-3">
                   <div className="text-[10px] text-emerald-400 font-mono font-bold uppercase tracking-widest">Metadata Consolidation</div>
                   <div className="h-1 w-1 rounded-full bg-slate-700" />
                   <div className="text-[10px] text-slate-500 font-medium uppercase tracking-widest">{selectedLog?.timestamp && format(new Date(selectedLog.timestamp), 'yyyy-MM-dd HH:mm:ss')}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="bg-slate-900 border-slate-700 text-slate-300 font-mono text-[10px] px-2 py-0.5 uppercase">
                  {selectedLog?.content.model}
                </Badge>
              </div>
            </CardHeader>
            <div className="flex-1 overflow-y-auto p-8 scroll-smooth space-y-2 bg-[radial-gradient(circle_at_50%_0%,rgba(16,185,129,0.03),transparent)]">
              {messages.map((msg: any, i: number) => (
                <ChatBubble key={i} role={msg.role} content={msg.content} />
              ))}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
